"""
smart_router.py — Pipeline mode selection from boxing data + routing thresholds.

Called before harness entry to select the cheapest mode that meets quality thresholds.

Routing tiers (cheapest → most expensive):
  brain_fast  — ta_brain_query only; skip harness entirely (~50ms, 0 tokens)
  api_only    — deterministic engine + report; no critics (~30s, ~8k tokens)
  full_moe    — full pipeline with critics + SM (~2min, ~40k tokens)

Decision logic (policies/model_routing.yaml drives thresholds):
  1. AIVSS composite >= override threshold  →  full_moe (security hard override)
  2. No boxing data for arch               →  no_boxing_data_default (api_only)
  3. brain_vs_gold_delta >= brain_fast.min AND corpus_hits >= brain_fast.min  →  brain_fast
  4. brain_vs_gold_delta >= api_only.min  AND corpus_hits >= api_only.min     →  api_only
  5. Default                              →  full_moe
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from chatbot.config import get_settings

_log = logging.getLogger(__name__)

_POLICY_PATH = Path(__file__).resolve().parents[2] / "policies" / "model_routing.yaml"


@dataclass
class RoutingDecision:
    mode: str          # "brain_fast" | "api_only" | "full_moe"
    rationale: str
    brain_vs_gold_delta: Optional[float] = None
    corpus_hits: Optional[int] = None
    ref_technique_count: Optional[int] = None
    arch_type: str = ""
    aivss_override: bool = False
    has_boxing_data: bool = False
    model_alias: str = ""      # e.g. "minimax", "hetzner" — alias in tested_models
    model_id: str = ""         # full model string for llm_client, e.g. "openrouter/minimax/..."


def _select_model(mode: str, arch_type: str, policy: dict) -> tuple[str, str]:
    """Return (alias, model_id) for the given mode + arch_type from policy.

    Falls back to 'default' entry if arch_type not listed, then to hetzner if
    the policy section is missing entirely. brain_fast skips harness — no model needed.
    """
    if mode == "brain_fast":
        return "", ""

    sel = policy.get("model_selection", {})
    mode_sel = sel.get(mode) or sel.get("api_only") or {}
    entry = mode_sel.get(arch_type) or mode_sel.get("default") or {}

    alias = entry.get("primary", "hetzner")
    fallback_alias = entry.get("fallback", "gemini_flash")

    models = policy.get("tested_models", {})
    model_entry = models.get(alias, {})

    # Skip excluded/unavailable models — try fallback
    if model_entry.get("status") not in ("confirmed", "partial") or not model_entry.get("model_id"):
        alias = fallback_alias
        model_entry = models.get(alias, {})

    model_id = model_entry.get("model_id", "")
    return alias, model_id


def _load_policy() -> dict:
    try:
        return yaml.safe_load(_POLICY_PATH.read_text()) or {}
    except Exception as exc:
        _log.warning("smart_router: could not load model_routing.yaml: %s", exc)
        return {}


def _load_boxing_signals(arch_name: str) -> Optional[dict]:
    """
    Load routing_signals from report/<arch>/boxing_results.json, if present.

    Falls back to reconstructing signals from verdict.quality_vs_cost for
    results produced before routing_signals was added (corpus_hits=0 in that case).
    """
    try:
        report_dir = Path(get_settings().system.report_dir)
        boxing_path = report_dir / arch_name / "boxing_results.json"
        if not boxing_path.exists():
            return None
        data = json.loads(boxing_path.read_text())

        signals = data.get("routing_signals") or {}
        if signals.get("brain_vs_gold_delta") is not None:
            return signals

        # Fallback: reconstruct from verdict.quality_vs_cost (old format)
        qvsc = data.get("verdict", {}).get("quality_vs_cost", {})
        delta = qvsc.get("brain_vs_gold_delta")
        if delta is None:
            return None
        return {
            "brain_vs_gold_delta": delta,
            "corpus_hits": 0,          # unknown in old format — treated conservatively
            "ref_technique_count": data.get("ref_technique_count", 0),
            "arch_type": "",
            "brain_latency_speedup": qvsc.get("brain_latency_speedup"),
        }
    except Exception as exc:
        _log.warning("smart_router: could not load boxing signals for %s: %s", arch_name, exc)
        return None


def select_mode(
    arch_name: str,
    aivss_composite: Optional[float] = None,
) -> RoutingDecision:
    """
    Select pipeline mode for arch_name.

    Args:
        arch_name:       Architecture identifier (matches report/<arch>/ directory).
        aivss_composite: Live AIVSS composite score if already computed; used for
                         the security hard override. Pass None when unknown.

    Returns:
        RoutingDecision with chosen mode and rationale.
    """
    policy = _load_policy()
    overrides = policy.get("overrides", {})
    tiers = policy.get("tiers", {})

    aivss_threshold = float(overrides.get("aivss_composite_full_moe_threshold", 7.0))
    default_no_data = overrides.get("no_boxing_data_default", "api_only")

    # ── Hard override: AIVSS risk ─────────────────────────────────────────────
    if aivss_composite is not None and aivss_composite >= aivss_threshold:
        _alias, _mid = _select_model("full_moe", "", policy)
        return RoutingDecision(
            mode="full_moe",
            rationale=f"AIVSS composite {aivss_composite:.1f} >= {aivss_threshold} security override",
            aivss_override=True,
            has_boxing_data=False,
            model_alias=_alias,
            model_id=_mid,
        )

    # ── Load boxing signals ───────────────────────────────────────────────────
    signals = _load_boxing_signals(arch_name)
    if signals is None:
        _alias, _mid = _select_model(default_no_data, "", policy)
        return RoutingDecision(
            mode=default_no_data,
            rationale="no boxing data for this arch — using default",
            has_boxing_data=False,
            model_alias=_alias,
            model_id=_mid,
        )

    delta = float(signals.get("brain_vs_gold_delta", -999))
    corpus_hits = int(signals.get("corpus_hits", 0))
    ref_count = int(signals.get("ref_technique_count", 0))
    arch_type = signals.get("arch_type", "")
    d5 = signals.get("d5_critical_recall")  # None = no attack_paths scored yet

    base = dict(
        brain_vs_gold_delta=delta,
        corpus_hits=corpus_hits,
        ref_technique_count=ref_count,
        arch_type=arch_type,
        has_boxing_data=True,
    )

    # ── D5 gate (checked before tier logic) ──────────────────────────────────
    # If brain misses too many high-criticality techniques, downgrade to api_only.
    d5_min = float(overrides.get("d5_critical_recall_min", 0.85))
    d5_blocked = d5 is not None and d5 < d5_min

    # ── brain_fast tier ───────────────────────────────────────────────────────
    bf = tiers.get("brain_fast", {})
    bf_delta_min = float(bf.get("brain_vs_gold_delta_min", -0.15))
    bf_hits_min = int(bf.get("corpus_hits_min", 3))

    if delta >= bf_delta_min and corpus_hits >= bf_hits_min:
        if d5_blocked:
            _alias, _mid = _select_model("api_only", arch_type, policy)
            return RoutingDecision(
                mode="api_only",
                rationale=(
                    f"brain_fast threshold met but D5 critical recall={d5:.3f} < {d5_min} — "
                    "downgraded to api_only (brain missing high-criticality techniques)"
                ),
                model_alias=_alias, model_id=_mid,
                **base,
            )
        return RoutingDecision(
            mode="brain_fast",
            rationale=(
                f"brain_vs_gold_delta={delta:+.3f} >= {bf_delta_min} "
                f"AND corpus_hits={corpus_hits} >= {bf_hits_min}"
            ),
            model_alias="", model_id="",
            **base,
        )

    # ── api_only tier ─────────────────────────────────────────────────────────
    ao = tiers.get("api_only", {})
    ao_delta_min = float(ao.get("brain_vs_gold_delta_min", -0.30))
    ao_hits_min = int(ao.get("corpus_hits_min", 1))

    if delta >= ao_delta_min and corpus_hits >= ao_hits_min:
        _alias, _mid = _select_model("api_only", arch_type, policy)
        return RoutingDecision(
            mode="api_only",
            rationale=(
                f"brain_vs_gold_delta={delta:+.3f} >= {ao_delta_min} "
                f"AND corpus_hits={corpus_hits} >= {ao_hits_min} (brain below brain_fast threshold)"
            ),
            model_alias=_alias, model_id=_mid,
            **base,
        )

    # ── full_moe fallback ─────────────────────────────────────────────────────
    _alias, _mid = _select_model("full_moe", arch_type, policy)
    return RoutingDecision(
        mode="full_moe",
        rationale=(
            f"brain_vs_gold_delta={delta:+.3f} or corpus_hits={corpus_hits} "
            "below api_only threshold"
        ),
        model_alias=_alias, model_id=_mid,
        **base,
    )
