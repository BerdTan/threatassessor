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
from chatbot.modules.agent_passport import AgentPassport, mint_passport, validate_token as _validate_passport

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
    passport: Optional[AgentPassport] = None,
    passport_token: Optional[str] = None,
) -> None:
    store = get_job_store()
    _tmpdir: Optional[str] = None

    # 0. Validate agent passport (defense-in-depth — token was just minted)
    _passport_valid = True
    _passport_reason = "ok"
    if passport_token:
        _passport_valid, _passport_reason, _ = _validate_passport(passport_token)
        if not _passport_valid:
            logger.warning(
                "TAclaw: passport validation failed for job %s: %s", job.job_id, _passport_reason
            )
    else:
        logger.warning("TAclaw: job %s has no passport token", job.job_id)
        _passport_valid = False
        _passport_reason = "missing_token"

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

        # 4b. Pre-flight authority check (mirrors artifact.py pattern)
        from chatbot.harness.governance import get_governance_adapter as _get_gov
        _gov = _get_gov()
        _preflight_sig = _gov.check_preflight(merged)
        if _preflight_sig.preflight.get("blocked", False):
            store.update(
                job.job_id,
                status="failed",
                error=_preflight_sig.preflight.get("reason", "Pre-flight authority check failed"),
                progress=0,
            )
            return

        # 5. Smart routing — decide mode before harness runs
        from chatbot.harness.smart_router import select_mode as _select_mode
        from chatbot.config import get_settings
        settings = get_settings()
        report_dir = Path(settings.system.report_dir) / arch_name

        routing = _select_mode(arch_name)
        routing_mode = routing.mode

        # brain_fast: skip pipeline if existing report files are present; else fall back
        if routing_mode == "brain_fast" and not (report_dir / "ground_truth.json").exists():
            routing_mode = "api_only"
            logger.info("TAclaw: brain_fast → api_only (no existing report for %s)", arch_name)

        store.update(job.job_id, progress=55, message=f"Running TA pipeline [{routing_mode}]")

        if routing_mode == "brain_fast":
            # Serve from existing report files — no new pipeline run
            gate = "PASS"
            pipeline_result = None
            logger.info("TAclaw: brain_fast path for %s (skipping full pipeline)", arch_name)
        else:
            mmd_tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".mmd", delete=False, encoding="utf-8"
            )
            mmd_tmp.write(mmd_text)
            mmd_tmp.close()
            mmd_path = Path(mmd_tmp.name)

            try:
                from chatbot.harness.controller import ThreatAssessorHarness, PipelineRequest, BlockedPipelineError

                _routed_model = routing.model_id
                _agent_models = (
                    {a: _routed_model for a in
                     ["architect", "tester", "red_team", "purple_team", "blackhat", "moe_orchestrator"]}
                    if _routed_model else None
                )
                if _routed_model:
                    logger.warning(
                        "TAclaw smart_router: %s → mode=%s model=%s (%s)",
                        arch_name, routing_mode, routing.model_alias, _routed_model,
                    )

                def _run_pipeline():
                    harness = ThreatAssessorHarness()
                    req = PipelineRequest(
                        architecture_path=str(mmd_path),
                        report_dir=str(report_dir),
                        ssp_profile=ssp_profile,
                        architecture_name=arch_name,
                        enable_moe=routing_mode == "full_moe",
                        enable_scrum_master=routing_mode == "full_moe",
                        agent_models=_agent_models,
                        metadata={
                            "routing_mode": routing_mode,
                            "agent_passport_status": "valid" if _passport_valid else _passport_reason,
                            "agent_passport_id": passport.passport_id() if passport else "",
                            "_preflight_blocked": False,
                            "_source_trust": getattr(merged, "source_trust", "unverified"),
                            "_preflight_signals": _preflight_sig.preflight,
                        },
                    )
                    return harness.run_typed(req)

                store.update(job.job_id, progress=60, message=f"TA pipeline running [{routing_mode}]")
                pipeline_result = await asyncio.get_event_loop().run_in_executor(None, _run_pipeline)
                gate = "PASS"
            except Exception as exc:
                if "BlockedPipelineError" in type(exc).__name__ or "blocked" in str(exc).lower():
                    gate = "BLOCK"
                    pipeline_result = None
                    logger.warning("TAclaw: pipeline blocked for %s: %s", arch_name, exc)
                else:
                    store.update(job.job_id, status="failed", error=f"Pipeline failed: {exc}", progress=0)
                    return
            finally:
                mmd_path.unlink(missing_ok=True)

        store.update(job.job_id, progress=83, message="Scoring TATB rubric")

        # 6a. Fetch TATB scores for this arch (non-fatal)
        tatb_scores: dict | None = None
        try:
            import importlib.util as _ilu
            import json as _json
            _skill_path = Path(__file__).parent.parent.parent.parent / ".claude/skills/tatb-score/scripts/tatb-score.py"
            if _skill_path.exists() and (report_dir / "ground_truth.json").exists():
                _spec = _ilu.spec_from_file_location("tatb_score_skill", _skill_path)
                _mod = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                _gt = _json.loads((report_dir / "ground_truth.json").read_text())
                _gov = _json.loads((report_dir / "governance_signals.json").read_text()) if (report_dir / "governance_signals.json").exists() else None
                _moe = _json.loads((report_dir / "07_moe_orchestrator.json").read_text()) if (report_dir / "07_moe_orchestrator.json").exists() else None
                _sm  = _json.loads((report_dir / "08_scrum_master.json").read_text()) if (report_dir / "08_scrum_master.json").exists() else None
                _tech_ids: set = set()
                for _ap in _gt.get("expected_attack_paths", []):
                    _tech_ids.update(_ap.get("techniques", []))
                _mitre_mits, _mit_names = _mod.fetch_mitre(list(_tech_ids))
                _t = _mod.score_threat(_gt)
                _ttp = _mod.score_ttp(_gt, _moe, _mitre_mits, _mit_names)
                _r = _mod.score_risk(_gt, _gov)
                _p = _mod.score_plan(_gt, _sm)
                _valid = [s["score"] for s in [_t, _ttp, _r, _p] if isinstance(s, dict) and s.get("score") is not None]
                tatb_scores = {"architectures": [{"name": arch_name, "overall": round(sum(_valid) / len(_valid)) if _valid else None, "threat": _t.get("score"), "ttp": _ttp.get("score"), "risk": _r.get("score"), "plan": _p.get("score")}]}
        except Exception as exc:
            logger.warning("TAclaw: tatb scoring failed (non-fatal): %s", exc)

        # 6b-pre. If passport was invalid, stamp identity.agent_passport_invalid into
        # governance_signals.json before build_export() reads it — so the DETECT-AGT-001
        # rule can fire from the export bundle's governance section.
        if not _passport_valid:
            _gov_path = report_dir / "governance_signals.json"
            if _gov_path.exists():
                try:
                    import json as _json_gov
                    _gov_data = _json_gov.loads(_gov_path.read_text())
                    _gov_data.setdefault("identity", {})["agent_passport_invalid"] = True
                    _gov_data["identity"]["agent_passport_reason"] = _passport_reason
                    _gov_path.write_text(_json_gov.dumps(_gov_data, indent=2))
                except Exception:
                    pass

        store.update(job.job_id, progress=85, message="Building export bundle")

        # 6b. Build export bundle
        export_data: dict = {}
        try:
            from chatbot.modules.ta_exporter import build_export
            export_data = build_export(arch_name, report_dir, tatb_scores=tatb_scores)
        except Exception as exc:
            logger.warning("TAclaw: export bundle failed: %s", exc)
            export_data = {"gate": {"result": gate}}

        # 6c. Inject agent passport provenance into export bundle
        if passport:
            export_data.setdefault("provenance", {})["agent_passport"] = passport.to_provenance()

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

            # 8a. Build brain_quality from Brier scores for matched pattern
            _patterns = brain_insight.get("patterns_fired", [])
            if _patterns:
                try:
                    from chatbot.modules.ta_brain_benchmarks import BENCHMARKS_PATH
                    import json as _json2
                    if BENCHMARKS_PATH.exists():
                        _bscores = _json2.loads(BENCHMARKS_PATH.read_text()).get("brier_scores", {})
                        _pat_id = _patterns[0]
                        if _pat_id in _bscores:
                            _bs = _bscores[_pat_id]
                            export_data["brain_quality"] = {
                                "pattern_id": _pat_id,
                                "arch_type": _bs.get("arch_type", ""),
                                "brier_combined": _bs.get("brier_combined"),
                                "brier_technique": _bs.get("brier_technique"),
                                "brier_control": _bs.get("brier_control"),
                                "benchmark_confidence": _bs.get("benchmark_confidence_brier"),
                                "samples_used": _bs.get("samples_used", 0),
                            }
                except Exception:
                    pass

        except Exception as exc:
            logger.warning("TAclaw: brain ingest/infer failed (non-fatal): %s", exc)

        store.update(
            job.job_id,
            status="completed",
            progress=100,
            message=f"TAclaw complete — gate={gate}, mode={routing_mode}, arch='{arch_name}'",
            result={
                "arch_name": arch_name,
                "gate": gate,
                "routing_mode": routing_mode,
                "passport_id": passport.passport_id() if passport else None,
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

    # Mint agent passport at job creation — gives every TAclaw run a signed identity token
    _passport, _passport_token = mint_passport(
        caller="taclaw",
        target=arch_name,
        job_id=job.job_id,
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
            passport=_passport,
            passport_token=_passport_token,
        )
    )

    return {
        "job_id": job.job_id,
        "status": "queued",
        "arch_name": arch_name,
        "target": body.target,
        "target_type": body.target_type,
        "passport_id": _passport.passport_id(),
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
