"""
TAwatch API routes.

GET /api/v1/tawatch/status           — corpus stats + load state
GET /api/v1/tawatch/heatmap          — 65-domain × N-incident coverage matrix
GET /api/v1/tawatch/incidents        — paginated incident list with DETECT domain tags
GET /api/v1/tawatch/domain/{domain}  — incidents matching a DETECT domain
GET /api/v1/tawatch/coverage         — per-domain coverage stats (CISO view)
GET /api/v1/tawatch/match            — architecture → matched real incidents
GET /api/v1/tawatch/sector/{sector}  — real-world attack profile for a sector
GET /api/v1/tawatch/model/{model}    — real-world operation profile for a model family
POST /api/v1/tawatch/reload          — reload incident corpus from disk
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from chatbot.api.dependencies import verify_api_key
from chatbot.modules.tawatch import get_tawatch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tawatch", tags=["tawatch"])


@router.get("/status")
async def tawatch_status(_: str = Depends(verify_api_key)):
    tw = get_tawatch()
    return tw.status()


@router.get("/heatmap")
async def tawatch_heatmap(
    sector: Optional[str] = Query(None),
    actor:  Optional[str] = Query(None),
    model:  Optional[str] = Query(None),
    _: str = Depends(verify_api_key),
):
    tw = get_tawatch()
    if not tw.corpus_loaded:
        raise HTTPException(
            status_code=503,
            detail="TAwatch corpus not loaded. Add incidents to report/brain/tawatch_incidents.jsonl.",
        )
    return tw.build_heatmap(sector_filter=sector, actor_filter=actor, model_filter=model)


@router.get("/incidents")
async def tawatch_incidents(
    sector: Optional[str] = Query(None),
    actor:  Optional[str] = Query(None),
    model:  Optional[str] = Query(None),
    page:   int = Query(1, ge=1),
    limit:  int = Query(25, ge=1, le=100),
    _: str = Depends(verify_api_key),
):
    tw = get_tawatch()
    hm = tw.build_heatmap(sector_filter=sector, actor_filter=actor, model_filter=model)
    incidents = hm["incidents"]
    start = (page - 1) * limit
    page_items = incidents[start : start + limit]
    # attach domain tags to each incident
    tagged = []
    for inc in page_items:
        inc_id = inc["id"]
        domains = tw._coverage.get(inc_id, {})
        tagged.append({**inc, "detect_domains": domains})
    return {
        "total":    len(incidents),
        "page":     page,
        "limit":    limit,
        "items":    tagged,
    }


@router.get("/domain/{domain}")
async def tawatch_domain_incidents(
    domain: str,
    min_confidence: str = Query("low", regex="^(low|medium|high)$"),
    _: str = Depends(verify_api_key),
):
    tw = get_tawatch()
    incidents = tw.get_domain_incidents(domain.upper(), min_confidence=min_confidence)
    return {
        "domain":         domain.upper(),
        "incident_count": len(incidents),
        "incidents":      incidents,
    }


@router.get("/coverage")
async def tawatch_coverage(_: str = Depends(verify_api_key)):
    tw = get_tawatch()
    return {
        "total_incidents": tw.incident_count,
        "domains":         tw.coverage_summary(),
    }


@router.get("/match")
async def tawatch_match_architecture(
    sector:     Optional[str] = Query(None),
    model:      Optional[str] = Query(None),
    is_agentic: bool          = Query(False),
    _: str = Depends(verify_api_key),
):
    tw = get_tawatch()
    matches = tw.match_architecture(sector=sector, model_family=model, is_agentic=is_agentic)
    return {
        "query":   {"sector": sector, "model": model, "is_agentic": is_agentic},
        "matches": matches,
    }


@router.get("/sector/{sector}")
async def tawatch_sector_profile(sector: str, _: str = Depends(verify_api_key)):
    tw = get_tawatch()
    return tw.sector_risk_profile(sector)


@router.get("/model/{model_family}")
async def tawatch_model_profile(model_family: str, _: str = Depends(verify_api_key)):
    tw = get_tawatch()
    return tw.model_risk_profile(model_family)


@router.post("/reload")
async def tawatch_reload(_: str = Depends(verify_api_key)):
    tw = get_tawatch()
    tw.reload()
    return {"reloaded": True, "incident_count": tw.incident_count}
