"""
routing.py — Smart pipeline routing suggestion endpoint.

Reads boxing_results.json + model_routing.yaml for a known architecture
and returns the recommended pipeline mode + rationale.

Useful for:
  - Dashboard routing hint before kicking off analysis
  - CI/CD gate: block full MoE if brain_fast is sufficient
  - Debugging routing decisions
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional

from chatbot.api.dependencies import verify_api_key

router = APIRouter(prefix="/api/v1", tags=["routing"])


class RoutingSuggestion(BaseModel):
    arch_name: str
    mode: str
    rationale: str
    has_boxing_data: bool
    aivss_override: bool
    brain_vs_gold_delta: Optional[float] = None
    corpus_hits: Optional[int] = None
    ref_technique_count: Optional[int] = None
    arch_type: str = ""
    policy_version: Optional[str] = None


@router.get(
    "/routing/suggest/{arch_name}",
    response_model=RoutingSuggestion,
    summary="Suggest pipeline mode for a known architecture",
    description=(
        "Returns the recommended pipeline mode (brain_fast / api_only / full_moe) "
        "based on cached boxing results and model_routing.yaml thresholds. "
        "Returns 404 if the architecture directory does not exist."
    ),
)
async def suggest_routing(
    arch_name: str,
    aivss_composite: Optional[float] = None,
    api_key: str = Depends(verify_api_key),
) -> RoutingSuggestion:
    # Path traversal guard
    safe = Path(arch_name).name
    if safe != arch_name or ".." in arch_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid arch_name",
        )

    # Verify arch exists
    try:
        from chatbot.config import get_settings
        report_dir = Path(get_settings().system.report_dir)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not load settings")

    if not (report_dir / arch_name).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Architecture '{arch_name}' not found in report directory",
        )

    from chatbot.harness.smart_router import select_mode, _load_policy
    decision = select_mode(arch_name, aivss_composite=aivss_composite)

    policy = _load_policy()
    policy_version = policy.get("version")

    return RoutingSuggestion(
        arch_name=arch_name,
        mode=decision.mode,
        rationale=decision.rationale,
        has_boxing_data=decision.has_boxing_data,
        aivss_override=decision.aivss_override,
        brain_vs_gold_delta=decision.brain_vs_gold_delta,
        corpus_hits=decision.corpus_hits,
        ref_technique_count=decision.ref_technique_count,
        arch_type=decision.arch_type,
        policy_version=policy_version,
    )
