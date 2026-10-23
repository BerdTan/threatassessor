"""
TA Perspective — kill chain simulation routes.

POST /api/v1/perspective/run/{arch}
    SSE stream of PerspectiveStep events for the selected scenario.
    Body: { scenario_id: str, actor_override?: str }

GET /api/v1/perspective/scenarios/{arch}
    Returns ScenarioManifest instantly (no SSE). Used by the picker on sub-tab open.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from chatbot.api.dependencies import verify_api_key
from chatbot.api.routes.reports import resolve_arch_dir
from chatbot.modules.director_caster import DirectorCaster
from chatbot.modules.perspective_runner import PerspectiveRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["perspective"])


# ── Request / response models ─────────────────────────────────────────────────

class PerspectiveRunRequest(BaseModel):
    scenario_id: str
    actor_override: Optional[str] = None   # G-number e.g. "G0007" to force an actor


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_ground_truth(arch: str) -> dict:
    report_dir = resolve_arch_dir(arch)
    if not report_dir.exists():
        raise HTTPException(status_code=404, detail=f"Architecture '{arch}' not found")
    gt_path = report_dir / "ground_truth.json"
    if not gt_path.exists():
        raise HTTPException(
            status_code=404,
            detail="ground_truth.json not found — run analysis first",
        )
    try:
        return json.loads(gt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read ground_truth.json: {exc}")


async def _perspective_stream(
    ground_truth: dict,
    scenario_id: str,
    actor_override: Optional[str],
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted PerspectiveStep events."""
    try:
        dc = DirectorCaster(ground_truth)
        manifest = dc.build_manifest()

        entry = manifest.get(scenario_id)
        if entry is None:
            yield f"data: {json.dumps({'error': f'scenario {scenario_id!r} not found'})}\n\n"
            return

        bounds = dc.build_bounds(scenario_id)
        pacing = dc.build_pacing(bounds)

        # Actor override: swap top actor in bounds
        if actor_override:
            from chatbot.modules.group_campaign_matcher import get_matcher
            matcher = get_matcher()
            grp = matcher.get_group(actor_override)
            if grp:
                bounds.actor = {
                    "group_id": grp.group_id,
                    "name": grp.name,
                    "aliases": grp.aliases,
                    "overlap_pct": 0.0,
                    "matched_techniques": sorted(grp.techniques),
                    "tools": grp.tools[:5],
                }

        # Emit manifest entry as first event (frontend actor banner)
        yield f"data: {json.dumps({'event': 'manifest', 'scenario': entry.to_dict()})}\n\n"

        runner = PerspectiveRunner(ground_truth)
        for step in runner.run(bounds, pacing):
            yield f"data: {json.dumps({'event': 'step', **step.to_dict()})}\n\n"

        # Final summary
        result = runner.run_all(bounds, pacing)
        yield f"data: {json.dumps({'event': 'done', 'summary': result.summary})}\n\n"

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Perspective stream error for %s/%s", scenario_id, actor_override)
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/perspective/run/{architecture_name}",
    dependencies=[Depends(verify_api_key)],
    summary="Stream kill chain simulation for a scenario",
)
async def perspective_run(
    architecture_name: str,
    body: PerspectiveRunRequest,
):
    """
    SSE stream of PerspectiveStep events.

    Emits three event types:
    - ``manifest`` — scenario metadata (actor banner, risk score)
    - ``step``     — one per node along the path
    - ``done``     — final summary with block_rate
    """
    ground_truth = _load_ground_truth(architecture_name)
    return StreamingResponse(
        _perspective_stream(ground_truth, body.scenario_id, body.actor_override),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/perspective/scenarios/{architecture_name}",
    dependencies=[Depends(verify_api_key)],
    summary="Get scenario manifest for the kill chain picker",
)
async def perspective_scenarios(architecture_name: str):
    """
    Return the ScenarioManifest instantly (no SSE).
    Used by the dashboard scenario picker on sub-tab open.
    """
    ground_truth = _load_ground_truth(architecture_name)
    dc = DirectorCaster(ground_truth)
    manifest = dc.build_manifest()
    result = manifest.to_dict()
    # Include graph data for canvas rendering (avoids a second round-trip)
    meta = ground_truth.get("metadata", {})
    result["nodes"] = meta.get("parsed_nodes", {})
    result["edges"] = meta.get("parsed_edges", [])
    return result
