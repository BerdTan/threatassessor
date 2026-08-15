"""
TA Brain query engine — Stages 2 + 2.5: TACO outward surface + cache layer.

Handles infer / gaps / patterns query modes against ta_brain.json.
Infer queries route through CacheManager first:
  HIT  → served from cache, interaction logged as cache_hit
  MISS → KG pattern match, result written to cache, logged with variant/new label

Logs every query to ta_brain_interactions.jsonl (append-only) from day one
so Stage 7 (TACO processor) starts warm rather than cold.

Determinism contract: all pattern matching is rule-based (topology_sig lookup
+ arch_type filter). No LLM calls. explain mode (Stage 5) is the only mode
that may invoke an LLM — it is NOT implemented here.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chatbot.modules.ta_brain_cache import get_cache_manager, extract_shape_counts

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report"


def _brain_dir() -> Path:
    try:
        from chatbot.config import get_settings  # noqa: PLC0415
        rd = get_settings().system.report_dir
        base = Path(rd) if Path(rd).is_absolute() else ROOT / rd
    except Exception:
        base = ROOT / "report"
    return base / "brain"


BRAIN_PATH = _brain_dir() / "ta_brain.json"
INSTANCES_PATH = _brain_dir() / "ta_brain_instances.jsonl"
INTERACTIONS_PATH = _brain_dir() / "ta_brain_interactions.jsonl"

VALID_MODES = ("infer", "gaps", "patterns")


# ── Brain loader (cached per process, invalidated on pattern_version change) ──

_brain_cache: dict = {}
_brain_version: int = -1


def _load_brain() -> dict:
    global _brain_cache, _brain_version
    if not BRAIN_PATH.exists():
        return {}
    try:
        raw = json.loads(BRAIN_PATH.read_text())
        v = raw.get("pattern_version", 0)
        if v != _brain_version:
            _brain_cache = raw
            _brain_version = v
        return _brain_cache
    except Exception as exc:
        logger.warning("Could not load ta_brain.json: %s", exc)
        return {}


def _load_instances() -> list:
    if not INSTANCES_PATH.exists():
        return []
    instances = []
    for line in INSTANCES_PATH.read_text().strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            instances.append(json.loads(line))
        except Exception:
            pass
    return instances


# ── Interaction logger ────────────────────────────────────────────────────────

def _log_interaction(
    caller_type: str,
    query_mode: str,
    topology_signature: str,
    arch_type: str,
    patterns_fired: list,
    confidence_returned: float,
    had_match: bool,
    feedback: Optional[str] = None,
    cache_route: str = "kg",  # "cache_hit" | "variant" | "new" | "kg" (gaps/patterns)
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "caller_type": caller_type,
        "query_mode": query_mode,
        "topology_signature": topology_signature,
        "arch_type": arch_type,
        "patterns_fired": patterns_fired,
        "confidence_returned": round(confidence_returned, 4),
        "had_match": had_match,
        "feedback": feedback,
        "cache_route": cache_route,
    }
    try:
        with INTERACTIONS_PATH.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("Could not write interaction log: %s", exc)


# ── Core infer logic ──────────────────────────────────────────────────────────

def _find_instance(arch_name: str) -> Optional[dict]:
    """Look up a corpus instance by arch_id."""
    for inst in _load_instances():
        if inst.get("arch_id") == arch_name:
            return inst
    return None


def _run_infer(
    topology_signature: str,
    arch_type: str,
    brain: dict,
) -> dict:
    """
    Match topology_signature + arch_type against pattern layer.

    Priority order:
    1. Exact topology_signature match in evidence_arch_ids (strongest)
    2. arch_type cluster match (general — same arch_type family)

    Returns predictions + evidence trace. had_match is True if any pattern fires.
    """
    patterns = brain.get("patterns", [])
    fired: list = []

    # Pass 1: exact signature in evidence set
    for p in patterns:
        if topology_signature in [
            _find_instance(aid)["topology_signature"]
            for aid in p.get("evidence_arch_ids", [])
            if _find_instance(aid)
        ]:
            fired.append(p)

    # Pass 2: arch_type cluster (if pass 1 empty)
    if not fired:
        for p in patterns:
            if p["trigger"].get("arch_type") == arch_type:
                fired.append(p)

    if not fired:
        return {
            "had_match": False,
            "patterns_fired": [],
            "confidence": 0.0,
            "predictions": {},
            "evidence": {},
        }

    # Merge predictions from all fired patterns (highest confidence wins per field)
    best = max(fired, key=lambda p: p.get("corpus_confidence", 0))
    merged_techs: dict = {}
    merged_controls: dict = {}
    merged_rules: set = set()
    aivss_floors = []

    for p in fired:
        preds = p.get("predicts", {})
        for t, freq in preds.get("technique_frequencies", {}).items():
            merged_techs[t] = max(merged_techs.get(t, 0), freq)
        for c, freq in preds.get("control_frequencies", {}).items():
            merged_controls[c] = max(merged_controls.get(c, 0), freq)
        merged_rules.update(preds.get("detect_rules", []))
        if "aivss_floor" in preds:
            aivss_floors.append(preds["aivss_floor"])

    # Published confidence = min(corpus_confidence, benchmark_confidence)
    confidence = min(
        best.get("corpus_confidence", 0.0),
        best.get("benchmark_confidence", 1.0),
    )

    # Top techniques sorted by merged frequency
    tech_top = sorted(merged_techs.items(), key=lambda x: x[1], reverse=True)
    control_top = sorted(merged_controls.items(), key=lambda x: x[1], reverse=True)

    suspect_ids = [p["id"] for p in fired if p.get("suspect")]

    return {
        "had_match": True,
        "patterns_fired": [p["id"] for p in fired],
        "suspect_patterns": suspect_ids,
        "confidence": round(confidence, 4),
        "predictions": {
            "techniques": [t for t, _ in tech_top[:20]],
            "technique_top": [{"id": t, "frequency": f} for t, f in tech_top[:10]],
            "detect_rules": sorted(merged_rules),
            "aivss_floor": round(min(aivss_floors), 3) if aivss_floors else 0.0,
            "aivss_mean": round(best["predicts"].get("aivss_mean", 0.0), 3),
            "missing_controls": [c for c, _ in control_top[:15]],
            "control_priorities": [{"control": c, "frequency": f} for c, f in control_top[:10]],
        },
        "evidence": {
            "pattern_ids": [p["id"] for p in fired],
            "source_archs": list({aid for p in fired for aid in p.get("evidence_arch_ids", [])}),
        },
    }


# ── Public query function ─────────────────────────────────────────────────────

def query_brain(
    mode: str,
    arch_name: str = "",
    topology_signature: str = "",
    arch_type: str = "",
    caller_type: str = "rest",
    arch_type_filter: str = "",
) -> dict:
    """
    Main TACO query entry point. Logs every call to ta_brain_interactions.jsonl.

    Args:
        mode:               "infer" | "gaps" | "patterns"
        arch_name:          corpus arch_id — resolves topology_sig + arch_type from instance layer
        topology_signature: explicit sig (used when arch_name is absent)
        arch_type:          explicit arch_type hint (used with topology_signature)
        caller_type:        "mcp" | "rest" | "harness" — recorded in interaction log
        arch_type_filter:   filter patterns by arch_type (patterns mode only)

    Returns a response dict. Never raises — errors are returned as {"error": "..."}.
    """
    if mode not in VALID_MODES:
        return {"error": f"Unknown mode '{mode}'. Valid: {', '.join(VALID_MODES)}"}

    brain = _load_brain()
    if not brain:
        return {"error": "Brain not built. Run: python3 -m chatbot.modules.ta_brain_builder"}

    # Resolve topology_sig + arch_type from instance layer when arch_name given
    resolved_sig = topology_signature
    resolved_type = arch_type
    if arch_name:
        inst = _find_instance(arch_name)
        if inst:
            resolved_sig = inst["topology_signature"]
            resolved_type = inst.get("arch_type", arch_type)
        else:
            return {"error": f"Architecture '{arch_name}' not found in instance layer"}

    # ── infer mode ────────────────────────────────────────────────────────────
    if mode == "infer":
        if not resolved_sig and not resolved_type:
            return {"error": "infer mode requires arch_name or topology_signature+arch_type"}

        # Resolve shape_counts for cache variant labeling (best-effort)
        shape_counts: dict = {}
        if arch_name:
            gt_path = REPORT_DIR / arch_name / "ground_truth.json"
            if gt_path.exists():
                try:
                    meta = json.loads(gt_path.read_text()).get("metadata", {})
                    shape_counts = extract_shape_counts(meta.get("parsed_nodes", {}))
                except Exception:
                    pass

        cache = get_cache_manager()
        pattern_version = brain.get("pattern_version", 0)
        cache_result = cache.route(resolved_sig, resolved_type, "infer",
                                   pattern_version, shape_counts)

        if cache_result[0] == "hit":
            cached_response = cache_result[1]
            _log_interaction(
                caller_type=caller_type,
                query_mode="infer",
                topology_signature=resolved_sig,
                arch_type=resolved_type,
                patterns_fired=cached_response.get("patterns_fired", []),
                confidence_returned=cached_response.get("confidence", 0.0),
                had_match=cached_response.get("had_match", False),
                cache_route="cache_hit",
            )
            return {
                "mode": "infer",
                "arch_name": arch_name,
                "topology_signature": resolved_sig,
                "arch_type": resolved_type,
                "pattern_version": pattern_version,
                "cache_route": "cache_hit",
                **cached_response,
            }

        # Cache miss — run KG, write result to cache
        miss_label = cache_result[2]  # "variant" or "new"
        result = _run_infer(resolved_sig, resolved_type, brain)

        cache.write(resolved_sig, resolved_type, "infer",
                    shape_counts, result, pattern_version)

        _log_interaction(
            caller_type=caller_type,
            query_mode="infer",
            topology_signature=resolved_sig,
            arch_type=resolved_type,
            patterns_fired=result["patterns_fired"],
            confidence_returned=result["confidence"],
            had_match=result["had_match"],
            cache_route=miss_label,
        )

        return {
            "mode": "infer",
            "arch_name": arch_name,
            "topology_signature": resolved_sig,
            "arch_type": resolved_type,
            "pattern_version": pattern_version,
            "cache_route": miss_label,
            **result,
        }

    # ── gaps mode ─────────────────────────────────────────────────────────────
    if mode == "gaps":
        gaps = brain.get("gaps", [])

        _log_interaction(
            caller_type=caller_type,
            query_mode="gaps",
            topology_signature=resolved_sig,
            arch_type=resolved_type,
            patterns_fired=[],
            confidence_returned=0.0,
            had_match=bool(gaps),
        )

        return {
            "mode": "gaps",
            "pattern_version": brain.get("pattern_version", 0),
            "gap_count": len(gaps),
            "gaps": gaps,
        }

    # ── patterns mode ─────────────────────────────────────────────────────────
    if mode == "patterns":
        patterns = brain.get("patterns", [])
        if arch_type_filter:
            patterns = [p for p in patterns if p["trigger"].get("arch_type") == arch_type_filter]

        _log_interaction(
            caller_type=caller_type,
            query_mode="patterns",
            topology_signature=resolved_sig,
            arch_type=arch_type_filter or resolved_type,
            patterns_fired=[p["id"] for p in patterns],
            confidence_returned=0.0,
            had_match=bool(patterns),
        )

        return {
            "mode": "patterns",
            "pattern_version": brain.get("pattern_version", 0),
            "pattern_count": len(patterns),
            "patterns": patterns,
        }

    return {"error": "Unreachable"}
