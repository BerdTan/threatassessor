"""
Async job endpoints for long-running pipeline operations.

POST /api/v1/jobs/expert-review  — queue a FULL_MOE run, return job_id
GET  /api/v1/jobs/{job_id}/status — poll status/progress/result
"""

import asyncio
import logging
import tempfile
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from chatbot.api.dependencies import verify_api_key
from chatbot.api.rate_limit import limiter
from chatbot.api.job_store import get_job_store
from chatbot.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["jobs"])

VALID_CRITIC_MODES = {"partial_parallel", "sequential", "parallel", "auto"}


class ExpertReviewRequest(BaseModel):
    arch_name:    str
    critic_mode:  str = "partial_parallel"
    run_blackhat: bool = True
    critic_model: str | None = None  # broadcast model override for all critics


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/expert-review
# ---------------------------------------------------------------------------

@router.post("/jobs/expert-review", dependencies=[Depends(verify_api_key)])
@limiter.limit("3/minute")
async def submit_expert_review(request: Request, body: ExpertReviewRequest):
    """Queue a FULL_MOE expert review for an existing architecture.

    Returns immediately with a job_id. Poll GET /api/v1/jobs/{job_id}/status
    to track progress and retrieve the result when status == 'completed'.
    """
    if body.critic_mode not in VALID_CRITIC_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid critic_mode '{body.critic_mode}'. "
                   f"Valid values: {sorted(VALID_CRITIC_MODES)}",
        )

    safe_name = Path(body.arch_name).name
    if safe_name != body.arch_name or ".." in body.arch_name:
        raise HTTPException(status_code=400, detail="Invalid arch_name")

    report_dir = Path(get_settings().system.report_dir) / body.arch_name
    if not report_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Architecture '{body.arch_name}' not found — run analysis first",
        )

    # Locate the architecture MMD (before.mmd or {arch_name}.mmd)
    mmd_path = report_dir / "before.mmd"
    if not mmd_path.exists():
        mmd_path = report_dir / f"{body.arch_name}.mmd"
    if not mmd_path.exists():
        # Try tests/data/architectures/
        from chatbot.modules.mitre import get_mitre_helper as _  # noqa: trigger import
        candidates = list(Path(".").rglob(f"**/architectures/{body.arch_name}.mmd"))
        if candidates:
            mmd_path = candidates[0]
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No MMD file found for '{body.arch_name}'",
            )

    store = get_job_store()
    job = store.create()

    asyncio.create_task(_run_expert_review(
        job_id=job.job_id,
        arch_name=body.arch_name,
        mmd_path=str(mmd_path),
        report_dir=str(report_dir),
        critic_mode=body.critic_mode,
        critic_model=body.critic_model,
    ))

    return {
        "job_id":  job.job_id,
        "status":  "queued",
        "arch_name": body.arch_name,
        "critic_mode": body.critic_mode,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}/status
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/status", dependencies=[Depends(verify_api_key)])
async def get_job_status(job_id: str):
    """Poll the status of a queued or running job.

    Returns:
        status:   queued | running | completed | failed | blocked
        progress: 0-100
        message:  current stage description
        result:   present when status == 'completed'
        error:    present when status == 'failed' or 'blocked'
    """
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found (may have expired after 1 hour)",
        )

    payload: dict = {
        "job_id":   job.job_id,
        "status":   job.status,
        "progress": job.progress,
        "message":  job.message,
    }
    if job.result is not None:
        payload["result"] = job.result
    if job.error is not None:
        payload["error"] = job.error

    return payload


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

async def _run_expert_review(
    job_id: str,
    arch_name: str,
    mmd_path: str,
    report_dir: str,
    critic_mode: str,
    critic_model: str | None = None,
) -> None:
    store = get_job_store()
    store.update(job_id, status="running", progress=5, message="Starting expert review")

    # Read SSP profile from existing ground_truth if present
    ssp_profile = "low_risk_cloud"
    gt_path = Path(report_dir) / "ground_truth.json"
    if gt_path.exists():
        try:
            import json
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
            ssp_profile = (
                gt.get("ssp_profile")
                or gt.get("metadata", {}).get("ssp_profile")
                or ssp_profile
            )
        except Exception:
            pass

    def _progress_cb(stage: str, pct: int, msg: str) -> None:
        store.update(job_id, progress=max(5, min(95, pct)), message=f"{stage}: {msg}")

    try:
        from chatbot.harness.controller import (
            AsyncThreatAssessorHarness,
            PipelineRequest,
            ScenarioConfig,
            BlockedPipelineError,
        )

        # Broadcast a single model to all critics when override is set
        _critic_names = ["architect", "tester", "red_team", "purple_team", "blackhat", "scrum_master"]
        _agent_models = {c: critic_model for c in _critic_names} if critic_model else None

        request = PipelineRequest(
            architecture_path=mmd_path,
            report_dir=report_dir,
            ssp_profile=ssp_profile,
            enable_ssp=True,
            enable_moe=True,
            enable_scrum_master=True,
            critic_mode=critic_mode,
            architecture_name=arch_name,
            agent_models=_agent_models,
        )

        harness = AsyncThreatAssessorHarness(scenario=ScenarioConfig.FULL_MOE)
        response = await harness.run(request, progress_callback=_progress_cb)

        result = {
            "success":           response.success,
            "run_id":            response.run_id,
            "architecture_name": response.architecture_name,
            "confidence":        response.confidence,
            "errors":            response.errors,
            "governance_summary": response.governance_summary,
            "detect_summary":    response.detect_summary,
        }
        store.update(
            job_id,
            status="completed",
            progress=100,
            message="Expert review complete",
            result=result,
        )

    except BlockedPipelineError as e:
        store.update(
            job_id,
            status="blocked",
            progress=0,
            message=f"Pipeline blocked: {e.reason}",
            error=e.reason,
        )
    except Exception as e:
        logger.exception("Expert review job %s failed", job_id)
        store.update(
            job_id,
            status="failed",
            progress=0,
            message="Expert review failed",
            error=str(e),
        )


# ---------------------------------------------------------------------------
# GET /api/v1/mcp/access-signals  — live MCPAccessLogger state
# ---------------------------------------------------------------------------

@router.get("/mcp/access-signals", dependencies=[Depends(verify_api_key)])
async def get_mcp_access_signals():
    """Return the current MCP session access pattern signals.

    Used by the dashboard MCP tab to power the DETECT-020/021/022 status cards
    and the tool-usage heatmap. No parameters — always returns the live state
    of the module-level MCPAccessLogger singleton.
    """
    from mcp_server.access_logger import get_access_logger
    return get_access_logger().get_signals()


# ---------------------------------------------------------------------------
# GET /api/v1/mcp/jobs  — snapshot of all live + recent jobs
# ---------------------------------------------------------------------------

@router.get("/mcp/jobs", dependencies=[Depends(verify_api_key)])
async def list_mcp_jobs():
    """Return all non-expired jobs from the job store.

    Used by the dashboard MCP tab Jobs sub-pane. Jobs expire after 1 hour;
    this endpoint returns whatever is still in the in-memory store.
    """
    import time as _time
    store = get_job_store()
    store._evict()
    with store._lock:
        jobs = list(store._jobs.values())

    now = _time.time()
    return {
        "jobs": [
            {
                "job_id":     j.job_id,
                "status":     j.status,
                "progress":   j.progress,
                "message":    j.message,
                "error":      j.error,
                "created_at": j.created_at,
                "updated_at": j.updated_at,
                "elapsed_s":  round(now - j.created_at, 1),
                # result summary only — not full payload
                "arch_name":  (j.result or {}).get("architecture_name", ""),
            }
            for j in sorted(jobs, key=lambda x: x.created_at, reverse=True)
        ],
        "total": len(jobs),
    }
