"""
TA Boxing API — async job wrapper around run_boxing_match().

POST /api/v1/boxing/run        — submit a match, returns job_id
GET  /api/v1/boxing/jobs/{id}  — poll status / result
GET  /api/v1/boxing/results    — list completed boxing_results.json files
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from chatbot.api.dependencies import verify_api_key
from chatbot.api.job_store import Job, get_job_store
from chatbot.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["boxing"])


class BoxingRequest(BaseModel):
    arch_name: str
    mmd_path: str                              # absolute path to .mmd file
    ssp_profile: str = "low_risk_cloud"
    arch_type: str = ""                        # hint for brain inference
    models: Optional[List[str]] = None         # LLM_PROVIDER keys; None = single default bot


async def _run_boxing_job(job: Job, req: BoxingRequest) -> None:
    store = get_job_store()
    try:
        store.update(job.job_id, status="running", progress=10, message="Starting boxing match")

        from chatbot.modules.ta_boxing import run_boxing_match

        def _run():
            return run_boxing_match(
                arch_name=req.arch_name,
                mmd_path=req.mmd_path,
                ssp_profile=req.ssp_profile,
                arch_type=req.arch_type,
                models=req.models or None,
            )

        store.update(job.job_id, progress=20, message="Bot contender running (~30s)")
        models_label = f" [{', '.join(req.models)}]" if req.models else ""
        store.update(job.job_id, progress=20, message=f"Bot contender{models_label} running (~30s each)…")
        result = await asyncio.get_event_loop().run_in_executor(None, _run)

        winner = result.get("verdict", {}).get("winner", "unknown")
        store.update(
            job.job_id,
            status="completed",
            progress=100,
            message=f"Boxing complete — winner: {winner}",
            result=result,
        )
    except Exception as exc:
        logger.exception("Boxing job %s failed", job.job_id)
        store.update(job.job_id, status="failed", error=str(exc), progress=0)


@router.post("/boxing/run", dependencies=[Depends(verify_api_key)])
async def boxing_run(body: BoxingRequest):
    """Submit a boxing match. Poll GET /api/v1/boxing/jobs/{job_id} for result."""
    mmd = Path(body.mmd_path)
    if not mmd.exists():
        raise HTTPException(status_code=400, detail=f"mmd_path not found: {body.mmd_path}")

    store = get_job_store()
    job = store.create()
    store.update(job.job_id, message=f"Boxing queued for {body.arch_name}")
    asyncio.create_task(_run_boxing_job(job, body))

    return {
        "job_id": job.job_id,
        "status": "queued",
        "arch_name": body.arch_name,
        "poll_url": f"/api/v1/boxing/jobs/{job.job_id}",
    }


@router.get("/boxing/jobs/{job_id}", dependencies=[Depends(verify_api_key)])
async def boxing_job_status(job_id: str):
    """Poll boxing job status. status ∈ {queued, running, completed, failed}."""
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "result": job.result if job.status == "completed" else None,
    }


class PromoteRequest(BaseModel):
    arch_name: str


async def _run_promote_job(job: Job, arch_name: str) -> None:
    store = get_job_store()
    try:
        store.update(job.job_id, status="running", progress=20, message=f"Promoting {arch_name} → brain")
        from chatbot.modules.ta_boxing import promote_boxing_to_brain

        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: promote_boxing_to_brain(arch_name)
        )
        gap = result.get("gap_closed", 0)
        store.update(
            job.job_id,
            status="completed",
            progress=100,
            message=f"Promote complete — D1 gap closed: {gap:+.1%}",
            result=result,
        )
    except Exception as exc:
        logger.exception("Promote job %s failed", job.job_id)
        store.update(job.job_id, status="failed", error=str(exc), progress=0)


@router.post("/boxing/promote", dependencies=[Depends(verify_api_key)])
async def boxing_promote(body: PromoteRequest):
    """
    Promote a completed boxing bot run into the brain as a real corpus instance,
    rebuild the brain, and return a confidence gap report.
    """
    store = get_job_store()
    job = store.create()
    store.update(job.job_id, message=f"Promote queued for {body.arch_name}")
    asyncio.create_task(_run_promote_job(job, body.arch_name))
    return {
        "job_id": job.job_id,
        "status": "queued",
        "arch_name": body.arch_name,
        "poll_url": f"/api/v1/boxing/jobs/{job.job_id}",
    }


@router.get("/boxing/results", dependencies=[Depends(verify_api_key)])
async def boxing_results_list():
    """List all saved boxing_results.json files in the report directory."""
    report_dir = Path(get_settings().system.report_dir)
    results = []
    for p in sorted(report_dir.glob("*/boxing_results.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            import json
            data = json.loads(p.read_text())
            results.append({
                "arch_name": data.get("arch_name"),
                "run_at": data.get("run_at"),
                "winner": data.get("verdict", {}).get("winner"),
                "scores": data.get("verdict", {}).get("scores", {}),
                "full_result": data,
            })
        except Exception:
            pass
    return {"results": results, "total": len(results)}
