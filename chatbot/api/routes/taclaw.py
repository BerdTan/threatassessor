"""
TAclaw — autonomous security assessment agent.

POST /api/v1/taclaw/run  — submit a target (directory or git URL), returns job_id
GET  /api/v1/taclaw/jobs/{job_id} — poll status/progress/result

TAclaw autonomously:
  1. Crawls the target for architecture artifacts (Terraform, CloudFormation, OpenAPI, prose)
  2. Runs each through the appropriate adapter → ArchitectureGraph
  3. Merges graphs into one composite architecture
  4. Runs the full TA pipeline (analyze + governance + export)
  5. Optionally cross-references GitHub Code Scanning alerts via POST /api/v1/enrich
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from chatbot.adapters.base import ArchitectureGraph
from chatbot.adapters.crawler import CrawledArtifact, RepoCrawler, clone_repo
from chatbot.api.dependencies import verify_api_key
from chatbot.api.job_store import Job, get_job_store
from chatbot.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["taclaw"])


# ── request / response models ─────────────────────────────────────────────────

class TAClawRequest(BaseModel):
    target_type: Literal["directory", "git_url"] = "directory"
    target: str                                      # local path or git URL
    arch_name: Optional[str] = None                  # defaults to target basename
    ssp_profile: str = "low_risk_cloud"
    enrich_from_github: bool = False                 # cross-ref GitHub Code Scanning alerts
    github_repo: Optional[str] = None               # "owner/repo" for enrich_from_github


class TAClawJobStatus(BaseModel):
    job_id: str
    status: str                  # queued | running | completed | failed
    progress: int
    message: str
    artifacts_found: Optional[int] = None
    graphs_merged: Optional[int] = None
    gate: Optional[str] = None   # "PASS" | "BLOCK"
    arch_name: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# ── job executor ──────────────────────────────────────────────────────────────

async def _run_taclaw_job(
    job: Job,
    target_type: str,
    target: str,
    arch_name: str,
    ssp_profile: str,
    enrich_from_github: bool,
    github_repo: Optional[str],
) -> None:
    store = get_job_store()
    _tmpdir: Optional[str] = None

    try:
        store.update(job.job_id, status="running", progress=5, message="Preparing target")

        # 1. Resolve target directory
        if target_type == "git_url":
            _tmpdir = tempfile.mkdtemp(prefix="taclaw_")
            root = Path(_tmpdir)
            store.update(job.job_id, progress=10, message=f"Cloning {target}")
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, clone_repo, target, root
                )
            except RuntimeError as exc:
                store.update(job.job_id, status="failed", error=str(exc), progress=0)
                return
        else:
            root = Path(target)
            if not root.exists() or not root.is_dir():
                store.update(
                    job.job_id,
                    status="failed",
                    error=f"Directory not found: {target}",
                    progress=0,
                )
                return

        # 2. Crawl for artifacts
        store.update(job.job_id, progress=20, message="Crawling for artifacts")
        crawler = RepoCrawler()
        try:
            artifacts: List[CrawledArtifact] = await asyncio.get_event_loop().run_in_executor(
                None, crawler.crawl, root
            )
        except Exception as exc:
            store.update(job.job_id, status="failed", error=f"Crawl failed: {exc}", progress=0)
            return

        if not artifacts:
            store.update(
                job.job_id,
                status="failed",
                error="No architecture artifacts found. Check that the target contains .tf, .yaml, .mmd, or .md files.",
                progress=0,
                result={"artifacts_found": 0},
            )
            return

        store.update(
            job.job_id,
            progress=35,
            message=f"Found {len(artifacts)} artifact(s) — extracting architecture graphs",
        )

        # 3. Extract graphs
        graphs: List[ArchitectureGraph] = []
        for art in artifacts:
            try:
                graph = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda a=art: a.adapter.extract(a.content, str(a.path)),
                )
                if graph.nodes:
                    graphs.append(graph)
            except Exception as exc:
                logger.warning("TAclaw: failed to extract %s: %s", art.path, exc)

        if not graphs:
            store.update(
                job.job_id,
                status="failed",
                error="All adapters produced empty graphs. Files may not contain architecture information.",
                progress=0,
                result={"artifacts_found": len(artifacts)},
            )
            return

        store.update(job.job_id, progress=50, message=f"Merging {len(graphs)} graph(s)")

        # 4. Merge graphs
        merged: ArchitectureGraph = await asyncio.get_event_loop().run_in_executor(
            None, crawler.merge_graphs, graphs
        )

        mmd_text = merged.to_mmd()

        # 5. Run TA pipeline
        store.update(job.job_id, progress=55, message="Running TA analysis pipeline")

        mmd_tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".mmd", delete=False, encoding="utf-8"
        )
        mmd_tmp.write(mmd_text)
        mmd_tmp.close()
        mmd_path = Path(mmd_tmp.name)

        try:
            from chatbot.harness.controller import ThreatAssessorHarness, PipelineRequest, BlockedPipelineError
            from chatbot.config import get_settings

            settings = get_settings()
            report_dir = Path(settings.system.report_dir) / arch_name

            def _run_pipeline():
                harness = ThreatAssessorHarness()
                req = PipelineRequest(
                    architecture_path=str(mmd_path),
                    report_dir=str(report_dir),
                    ssp_profile=ssp_profile,
                    architecture_name=arch_name,
                )
                return harness.run_typed(req)

            store.update(job.job_id, progress=60, message="TA pipeline running (~30s)")
            pipeline_result = await asyncio.get_event_loop().run_in_executor(None, _run_pipeline)
            gate = "PASS"
        except Exception as exc:
            # BlockedPipelineError is a BLOCK gate, not a failure
            if "BlockedPipelineError" in type(exc).__name__ or "blocked" in str(exc).lower():
                gate = "BLOCK"
                pipeline_result = None
                logger.warning("TAclaw: pipeline blocked for %s: %s", arch_name, exc)
            else:
                store.update(job.job_id, status="failed", error=f"Pipeline failed: {exc}", progress=0)
                return
        finally:
            mmd_path.unlink(missing_ok=True)

        store.update(job.job_id, progress=85, message="Building export bundle")

        # 6. Build export bundle
        export_data: dict = {}
        try:
            from chatbot.modules.ta_exporter import build_export
            export_data = build_export(arch_name, report_dir)
        except Exception as exc:
            logger.warning("TAclaw: export bundle failed: %s", exc)
            export_data = {"gate": {"result": gate}}

        # Override gate from pipeline if we got a BLOCK exception
        if gate == "BLOCK":
            export_data.setdefault("gate", {})["result"] = "BLOCK"

        # 7. Auto brain-ingest (incremental — skips if arch already in corpus)
        store.update(job.job_id, progress=90, message="Ingesting into TA Brain")
        brain_insight: dict = {}
        try:
            from chatbot.modules.ta_brain_builder import build_brain
            from chatbot.modules.ta_brain_query import query_brain

            root_report_dir = Path(get_settings().system.report_dir)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: build_brain(report_dir=root_report_dir, incremental=True),
            )

            # 8. Infer from newly-learned patterns
            brain_insight = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: query_brain(mode="infer", arch_name=arch_name, caller_type="taclaw"),
            )
        except Exception as exc:
            logger.warning("TAclaw: brain ingest/infer failed (non-fatal): %s", exc)

        store.update(
            job.job_id,
            status="completed",
            progress=100,
            message=f"TAclaw complete — gate={gate}, arch='{arch_name}'",
            result={
                "arch_name": arch_name,
                "gate": gate,
                "artifacts_found": len(artifacts),
                "graphs_merged": len(graphs),
                "composite_nodes": len(merged.nodes),
                "composite_edges": len(merged.edges),
                "source_formats": merged.adapter_metadata.get("source_formats", []),
                "export": export_data,
                "adapter_metadata": merged.adapter_metadata,
                "brain_insight": brain_insight,
            },
        )

    except Exception as exc:
        logger.exception("TAclaw job %s unexpected failure", job.job_id)
        store.update(job.job_id, status="failed", error=str(exc), progress=0)
    finally:
        if _tmpdir:
            import shutil
            shutil.rmtree(_tmpdir, ignore_errors=True)


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/taclaw/run", dependencies=[Depends(verify_api_key)])
async def taclaw_run(body: TAClawRequest):
    """
    Submit a TAclaw autonomous security assessment job.

    Crawls the target (local directory or git URL), extracts architecture graphs,
    merges them, runs the full TA pipeline, and returns a job_id to poll.

    Poll GET /api/v1/taclaw/jobs/{job_id} for status and result.
    """
    if body.target_type == "git_url":
        if not body.target.startswith(("https://", "git@", "http://")):
            raise HTTPException(status_code=400, detail="git_url must start with https://, http://, or git@")
    else:
        root = Path(body.target)
        if not root.exists():
            raise HTTPException(status_code=400, detail=f"Directory not found: {body.target}")
        if not root.is_dir():
            raise HTTPException(status_code=400, detail=f"Target must be a directory: {body.target}")

    arch_name = body.arch_name or Path(body.target).stem.replace(" ", "_") or "taclaw_assessment"
    # Sanitize
    arch_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in arch_name)[:64]

    store = get_job_store()
    job = store.create()
    store.update(
        job.job_id,
        message=f"TAclaw queued for {body.target_type}: {body.target[:60]}",
    )

    asyncio.create_task(
        _run_taclaw_job(
            job=job,
            target_type=body.target_type,
            target=body.target,
            arch_name=arch_name,
            ssp_profile=body.ssp_profile,
            enrich_from_github=body.enrich_from_github,
            github_repo=body.github_repo,
        )
    )

    return {
        "job_id": job.job_id,
        "status": "queued",
        "arch_name": arch_name,
        "target": body.target,
        "target_type": body.target_type,
        "poll_url": f"/api/v1/taclaw/jobs/{job.job_id}",
    }


@router.get("/taclaw/jobs", dependencies=[Depends(verify_api_key)])
async def taclaw_jobs_list():
    """List all active TAclaw jobs (queued, running, completed, failed) within TTL window."""
    store = get_job_store()
    jobs = store.list_all()
    def _brain_summary(result: dict) -> dict:
        bi = result.get("brain_insight", {})
        if not bi or not bi.get("had_match"):
            return {}
        preds = bi.get("predictions", {})
        return {
            "had_match": True,
            "confidence": bi.get("confidence", 0.0),
            "top_techniques": [t["id"] for t in preds.get("technique_top", [])[:3]],
            "detect_rules": preds.get("detect_rules", [])[:3],
            "aivss_floor": preds.get("aivss_floor"),
        }

    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "status": j.status,
                "progress": j.progress,
                "message": j.message,
                "error": j.error,
                "arch_name": (j.result or {}).get("arch_name") if j.result else None,
                "artifacts_found": (j.result or {}).get("artifacts_found") if j.result else None,
                "graphs_merged": (j.result or {}).get("graphs_merged") if j.result else None,
                "composite_nodes": (j.result or {}).get("composite_nodes") if j.result else None,
                "gate": (j.result or {}).get("gate") if j.result else None,
                "source_formats": (j.result or {}).get("source_formats", []) if j.result else [],
                "brain_insight": _brain_summary(j.result or {}) if j.result else {},
                "created_at": j.created_at,
                "updated_at": j.updated_at,
            }
            for j in sorted(jobs, key=lambda x: x.created_at, reverse=True)
        ],
        "total": len(jobs),
    }


@router.get("/taclaw/jobs/{job_id}", dependencies=[Depends(verify_api_key)])
async def taclaw_job_status(job_id: str) -> TAClawJobStatus:
    """Poll TAclaw job status. status ∈ {queued, running, completed, failed}."""
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    result = job.result or {}
    return TAClawJobStatus(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        artifacts_found=result.get("artifacts_found"),
        graphs_merged=result.get("graphs_merged"),
        gate=result.get("gate"),
        arch_name=result.get("arch_name"),
        result=result if job.status == "completed" else None,
        error=job.error,
    )
