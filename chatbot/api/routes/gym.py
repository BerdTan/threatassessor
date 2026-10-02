"""
TAgym — Autonomous TAclaw simulation loop controller.

Orchestrates a continuous assessment flywheel: target queue → TAclaw job
→ aggregate stats → optional brain ingest.  Single session at a time
(replaces any prior session on /gym/start).
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from chatbot.api.dependencies import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["gym"])


# ── session state ─────────────────────────────────────────────────────────────

@dataclass
class GymIteration:
    iteration: int
    target: str
    job_id: str
    status: str           # running | completed | failed | blocked
    arch_name: str = ""
    gate: str = ""
    mitigations: int = 0
    artifacts_found: int = 0
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class GymSession:
    session_id: str
    status: str           # idle | running | stopping | stopped
    targets: List[str]
    target_type: str
    ssp_profile: str
    max_iterations: int
    # rolling counters
    current_iteration: int = 0
    connections: int = 0
    tm_produced: int = 0
    mitigations_total: int = 0
    gate_pass: int = 0
    gate_block: int = 0
    brier_snapshots: List[float] = field(default_factory=list)
    iterations: List[GymIteration] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    _task: Optional[asyncio.Task] = field(default=None, repr=False, compare=False)


_session: Optional[GymSession] = None


def _get_session() -> Optional[GymSession]:
    return _session


# ── helpers ───────────────────────────────────────────────────────────────────

def _current_brier() -> Optional[float]:
    try:
        from chatbot.modules.ta_brain_benchmarks import BENCHMARKS_PATH
        import json
        if not BENCHMARKS_PATH.exists():
            return None
        data = json.loads(BENCHMARKS_PATH.read_text())
        scores = data.get("brier_scores", {})
        if not scores:
            return None
        vals = [v.get("brier_combined", 0.5) for v in scores.values() if "brier_combined" in v]
        return round(sum(vals) / len(vals), 4) if vals else None
    except Exception:
        return None


def _count_mitigations(result: dict) -> int:
    try:
        gt = result.get("ground_truth", {})
        controls = gt.get("controls", [])
        if isinstance(controls, list):
            return len(controls)
        mitigations = gt.get("mitigations", [])
        if isinstance(mitigations, list):
            return len(mitigations)
        return 0
    except Exception:
        return 0


# ── gym loop ──────────────────────────────────────────────────────────────────

async def _gym_loop(sess: GymSession) -> None:
    from chatbot.api.job_store import get_job_store
    from chatbot.api.routes.taclaw import _run_taclaw_job
    from chatbot.modules.agent_passport import mint_passport

    store = get_job_store()
    target_cycle = sess.targets
    n = len(target_cycle)

    while sess.status == "running" and sess.current_iteration < sess.max_iterations:
        idx = sess.current_iteration % n
        target = target_cycle[idx]
        arch_name = Path(target).stem.replace(" ", "_") if sess.target_type == "directory" else f"gym_{sess.current_iteration}"
        arch_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in arch_name)[:64]

        job = store.create()
        passport, passport_token = mint_passport(caller="tagym", target=arch_name, job_id=job.job_id)

        it = GymIteration(
            iteration=sess.current_iteration,
            target=target,
            job_id=job.job_id,
            status="running",
            arch_name=arch_name,
        )
        sess.iterations.append(it)
        sess.connections += 1
        sess.current_iteration += 1
        sess.updated_at = time.time()

        try:
            await _run_taclaw_job(
                job=job,
                target_type=sess.target_type,
                target=target,
                arch_name=arch_name,
                ssp_profile=sess.ssp_profile,
                enrich_from_github=False,
                github_repo=None,
                passport=passport,
                passport_token=passport_token,
            )
        except Exception as exc:
            logger.warning("TAgym iteration %d failed: %s", sess.current_iteration - 1, exc)

        # Harvest result
        updated_job = store.get(job.job_id)
        if updated_job:
            result = updated_job.result or {}
            it.status = updated_job.status
            it.completed_at = time.time()
            it.gate = result.get("gate", "")
            it.mitigations = _count_mitigations(result)
            it.artifacts_found = result.get("artifacts_found", 0)

            if updated_job.status == "completed":
                sess.tm_produced += 1
                sess.mitigations_total += it.mitigations
                if it.gate == "PASS":
                    sess.gate_pass += 1
                elif it.gate == "BLOCK":
                    sess.gate_block += 1
        else:
            it.status = "failed"
            it.completed_at = time.time()

        # Brier snapshot after each iteration
        b = _current_brier()
        if b is not None:
            sess.brier_snapshots.append(b)

        sess.updated_at = time.time()

    if sess.status == "running":
        sess.status = "stopped"
    sess.updated_at = time.time()
    logger.info("TAgym session %s finished — %d iterations", sess.session_id, sess.current_iteration)


# ── request models ────────────────────────────────────────────────────────────

class GymStartRequest(BaseModel):
    targets: List[str]
    target_type: Literal["directory", "git_url"] = "directory"
    ssp_profile: str = "low_risk_cloud"
    max_iterations: int = 10


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/gym/start", dependencies=[Depends(verify_api_key)])
async def gym_start(body: GymStartRequest):
    """Start (or restart) the TAgym autonomous assessment loop."""
    global _session

    if not body.targets:
        raise HTTPException(status_code=400, detail="targets list must not be empty")
    if body.max_iterations < 1 or body.max_iterations > 200:
        raise HTTPException(status_code=400, detail="max_iterations must be between 1 and 200")
    if body.target_type == "directory":
        for t in body.targets:
            if not Path(t).exists():
                raise HTTPException(status_code=400, detail=f"Directory not found: {t}")

    # Cancel any running session
    if _session and _session._task and not _session._task.done():
        _session.status = "stopping"
        _session._task.cancel()
        try:
            await asyncio.wait_for(_session._task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    sess = GymSession(
        session_id=str(uuid.uuid4()),
        status="running",
        targets=body.targets,
        target_type=body.target_type,
        ssp_profile=body.ssp_profile,
        max_iterations=body.max_iterations,
    )
    _session = sess
    sess._task = asyncio.create_task(_gym_loop(sess))

    return {
        "session_id": sess.session_id,
        "status": "running",
        "targets": body.targets,
        "max_iterations": body.max_iterations,
    }


@router.get("/gym/status", dependencies=[Depends(verify_api_key)])
async def gym_status():
    """Return current TAgym session stats."""
    sess = _get_session()
    if sess is None:
        return {"status": "idle", "session_id": None}

    return {
        "session_id": sess.session_id,
        "status": sess.status,
        "targets": sess.targets,
        "target_type": sess.target_type,
        "ssp_profile": sess.ssp_profile,
        "max_iterations": sess.max_iterations,
        "current_iteration": sess.current_iteration,
        "connections": sess.connections,
        "tm_produced": sess.tm_produced,
        "mitigations_total": sess.mitigations_total,
        "gate_pass": sess.gate_pass,
        "gate_block": sess.gate_block,
        "brier_snapshots": sess.brier_snapshots,
        "iterations": [
            {
                "iteration": it.iteration,
                "target": it.target,
                "job_id": it.job_id,
                "status": it.status,
                "arch_name": it.arch_name,
                "gate": it.gate,
                "mitigations": it.mitigations,
                "artifacts_found": it.artifacts_found,
                "started_at": it.started_at,
                "completed_at": it.completed_at,
            }
            for it in sess.iterations
        ],
        "started_at": sess.started_at,
        "updated_at": sess.updated_at,
    }


@router.post("/gym/stop", dependencies=[Depends(verify_api_key)])
async def gym_stop():
    """Stop the running TAgym session."""
    sess = _get_session()
    if sess is None or sess.status in ("idle", "stopped"):
        return {"status": "already_stopped"}

    sess.status = "stopping"
    if sess._task and not sess._task.done():
        sess._task.cancel()
        try:
            await asyncio.wait_for(sess._task, timeout=3.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    sess.status = "stopped"
    sess.updated_at = time.time()
    return {"status": "stopped", "session_id": sess.session_id}
