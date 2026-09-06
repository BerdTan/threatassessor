"""
routing.py — Smart pipeline routing suggestion + quick-assess endpoints.

/routing/suggest/{arch_name}  — recommended pipeline mode from boxing data
/routing/quick-assess/{arch_name} — pattern-based threat estimate (~50ms, no LLM)
    Returns brain inference output labeled as "pattern-based estimate".
    Not a replacement for full MoE — use as a fast pre-screen or sanity check.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

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


# ── Quick-assess response model ───────────────────────────────────────────────

class TechniqueEstimate(BaseModel):
    id: str
    frequency: float


class QuickAssessQuality(BaseModel):
    """Boxing dimensions scored against the arch graph (no gold reference)."""
    d2_accuracy: float        # synthetic per-node applicability
    d3_mitigations: float     # ATT&CK M-mitigation linkage
    d4_actionability: float   # AIVSS floor present + controls available
    composite: float          # weighted average (same weights as boxing)
    corpus_hits: int          # unique source arch IDs that fired patterns
    confidence: float         # brain pattern confidence


class QuickAssessResponse(BaseModel):
    arch_name: str
    estimate_type: str = "pattern-based"  # always — not a MoE replacement
    had_match: bool
    latency_ms: float
    techniques: List[str]
    technique_top: List[TechniqueEstimate]
    controls: List[str]
    detect_rules: List[str]
    aivss_floor: Optional[float]
    patterns_fired: List[str]
    suspect_patterns: List[str]
    quality: Optional[QuickAssessQuality]
    routing_mode: str          # what select_mode() recommends for this arch
    warning: Optional[str] = None


@router.get(
    "/routing/quick-assess/{arch_name}",
    response_model=QuickAssessResponse,
    summary="Pattern-based threat estimate (brain inference, ~50ms)",
    description=(
        "Runs TA Brain inference for a known architecture and returns predicted "
        "techniques, controls, and DETECT rules. Output is labeled as a "
        "'pattern-based estimate' — not a replacement for full MoE analysis. "
        "Quality scores (D2/D3/D4) are computed against the stored architecture graph. "
        "Returns 404 if the architecture has no prior analysis."
    ),
)
async def quick_assess(
    arch_name: str,
    api_key: str = Depends(verify_api_key),
) -> QuickAssessResponse:
    # Path traversal guard
    safe = Path(arch_name).name
    if safe != arch_name or ".." in arch_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid arch_name")

    try:
        from chatbot.config import get_settings
        report_dir = Path(get_settings().system.report_dir)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not load settings")

    arch_dir = report_dir / arch_name
    if not arch_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Architecture '{arch_name}' not found — run full analysis first",
        )

    # ── Brain inference ───────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        from chatbot.modules.ta_brain_query import query_brain
        infer = query_brain(mode="infer", arch_name=arch_name, caller_type="quick_assess")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Brain inference failed: {exc}")
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    # ── Routing mode (informational) ──────────────────────────────────────────
    try:
        from chatbot.harness.smart_router import select_mode
        routing_mode = select_mode(arch_name).mode
    except Exception:
        routing_mode = "unknown"

    if not infer.get("had_match"):
        return QuickAssessResponse(
            arch_name=arch_name,
            had_match=False,
            latency_ms=latency_ms,
            techniques=[],
            technique_top=[],
            controls=[],
            detect_rules=[],
            aivss_floor=None,
            patterns_fired=[],
            suspect_patterns=[],
            quality=None,
            routing_mode=routing_mode,
            warning="No brain patterns matched this architecture — run full MoE to build pattern coverage.",
        )

    preds: Dict[str, Any] = infer.get("predictions", {})
    techniques: List[str] = preds.get("techniques", [])
    controls: List[str] = preds.get("controls", [])
    detect_rules: List[str] = preds.get("detect_rules", [])
    aivss_floor: Optional[float] = preds.get("aivss_floor")
    tech_top_raw: List[Dict] = preds.get("technique_top", [])

    evidence: Dict[str, Any] = infer.get("evidence", {})
    corpus_hits = len(set(evidence.get("source_archs", [])))

    # ── Quality scores (D2/D3/D4 only — no gold reference for D1) ────────────
    quality: Optional[QuickAssessQuality] = None
    try:
        from chatbot.modules.ta_boxing import BoxingReferee, _extract_nodes_from_mmd
        referee = BoxingReferee()

        mmd_path = arch_dir / "architecture.mmd"
        nodes = _extract_nodes_from_mmd(str(mmd_path)) if mmd_path.exists() else {}

        d2 = referee.score_d2_synthetic(techniques, nodes) if nodes else 0.0
        d3 = referee.score_d3(techniques)
        d4 = referee.score_d4_brain(infer)
        comp = referee.composite(d1=0.0, d2=d2, d3=d3, d4=d4)

        quality = QuickAssessQuality(
            d2_accuracy=d2,
            d3_mitigations=d3,
            d4_actionability=d4,
            composite=comp,
            corpus_hits=corpus_hits,
            confidence=infer.get("confidence", 0.0),
        )
    except Exception:
        pass  # quality scoring is best-effort; don't block the response

    warn = None
    if infer.get("suspect_patterns"):
        warn = f"Suspect patterns fired: {infer['suspect_patterns']} — treat output with extra caution."

    return QuickAssessResponse(
        arch_name=arch_name,
        had_match=True,
        latency_ms=latency_ms,
        techniques=techniques,
        technique_top=[TechniqueEstimate(id=t["id"], frequency=t["frequency"]) for t in tech_top_raw],
        controls=controls,
        detect_rules=list(detect_rules),
        aivss_floor=aivss_floor,
        patterns_fired=infer.get("patterns_fired", []),
        suspect_patterns=infer.get("suspect_patterns", []),
        quality=quality,
        routing_mode=routing_mode,
        warning=warn,
    )
