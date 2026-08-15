"""
TA Brain meta layer — Stage 5: demand-weighted gap detection.

Extends Stage 1 gap detection with live interaction log signals:

  query_miss_demand  — topology_sigs queried repeatedly with had_match=False
  variant_demand     — cache_route=="variant" misses (known topology, uncovered variant)

Gap types produced:
  coverage_thin    — arch_type with < MIN_INSTANCES training instances (Stage 1 behavior)
  query_miss       — arch_type with significant miss-query demand even if well-sampled
  variant          — arch_type has well-sampled patterns but variant queries keep missing

Priority formula (Stage 5):
  priority = (thinness * max(danger, 0.3) + demand_weight * DEMAND_ALPHA) / NORM

Where demand_weight = (miss_count + 0.5 * variant_count) / max(total_queries, 1)
DEMAND_ALPHA weights demand vs thinness. Forced gaps bypass priority sorting.

Determinism contract: pure functions, no LLM calls.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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


INTERACTIONS_PATH = _brain_dir() / "ta_brain_interactions.jsonl"
INSTANCES_PATH = _brain_dir() / "ta_brain_instances.jsonl"

MIN_INSTANCES = 3          # below this → coverage_thin gap
DEMAND_THRESHOLD = 0.25    # miss_rate above this for well-sampled types → query_miss gap
DEMAND_ALPHA = 0.4         # weight of demand signal vs thinness in priority
HIGH_FREQ_THRESHOLD = 5    # cache hit_count above this with benchmark_confidence=1.0 → flag


# ── Demand weight computation ─────────────────────────────────────────────────

def compute_gap_demand_weights(
    interactions_path: Optional[Path] = None,
) -> dict:
    """
    Read interaction log and compute per-arch_type demand signals.

    Returns:
        {arch_type: {miss_count, variant_count, confirm_count, total_queries, demand_weight}}

    Only `infer` mode queries contribute. Feedback entries are skipped.
    """
    path = interactions_path or INTERACTIONS_PATH
    weights: dict = {}

    if not path.exists():
        return weights

    for line in path.read_text().strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if entry.get("type") == "feedback":
            continue
        if entry.get("query_mode") != "infer":
            continue

        arch_type = entry.get("arch_type", "")
        if not arch_type:
            continue

        if arch_type not in weights:
            weights[arch_type] = {
                "miss_count": 0,
                "variant_count": 0,
                "confirm_count": 0,
                "total_queries": 0,
            }

        weights[arch_type]["total_queries"] += 1

        had_match = entry.get("had_match", False)
        cache_route = entry.get("cache_route", "kg")

        if not had_match:
            weights[arch_type]["miss_count"] += 1
        elif cache_route == "variant":
            weights[arch_type]["variant_count"] += 1
        else:
            weights[arch_type]["confirm_count"] += 1

    # Compute demand_weight per arch_type
    for arch_type, d in weights.items():
        total = max(d["total_queries"], 1)
        d["demand_weight"] = round(
            (d["miss_count"] + 0.5 * d["variant_count"]) / total, 4
        )

    return weights


# ── Demand-weighted gap detection ─────────────────────────────────────────────

def detect_gaps_v2(
    instances: list,
    patterns: list,
    demand_weights: Optional[dict] = None,
) -> list:
    """
    Stage 5 gap detector. Returns gaps sorted by demand-weighted priority.

    Produces three gap types:
      coverage_thin  — arch_type with < MIN_INSTANCES training instances
      query_miss     — well-sampled but miss_rate > DEMAND_THRESHOLD
      variant        — well-sampled, variant queries clustering

    Forced gaps (from benchmark divergence, Stage 6) are left unchanged.
    """
    if demand_weights is None:
        demand_weights = {}

    real_instances = [i for i in instances if i.get("source") == "real"]
    total_real = len(real_instances)

    from collections import Counter  # noqa: PLC0415
    by_type = Counter(i["arch_type"] for i in real_instances)
    pattern_by_type = {p["trigger"]["arch_type"]: p for p in patterns}

    gaps: list = []
    gap_id = 1

    seen_types: set = set()

    # Pass 1: coverage_thin gaps (existing behavior, demand-enriched)
    for arch_type, count in sorted(by_type.items(), key=lambda x: x[1]):
        seen_types.add(arch_type)
        if count >= MIN_INSTANCES:
            continue

        thinness = round(1.0 - (count / max(total_real, 1)), 3)
        pat = pattern_by_type.get(arch_type)
        danger = pat["predicts"]["aivss_mean"] if pat else 0.5

        dw = demand_weights.get(arch_type, {})
        demand_weight = dw.get("demand_weight", 0.0)
        miss_count = dw.get("miss_count", 0)
        variant_count = dw.get("variant_count", 0)
        total_queries = dw.get("total_queries", 0)

        priority = round(
            (thinness * max(danger, 0.3) + demand_weight * DEMAND_ALPHA)
            / (1.0 + DEMAND_ALPHA),
            3,
        )

        gaps.append({
            "id": f"GAP-{gap_id:03d}",
            "region": f"arch_type:{arch_type}",
            "type": "coverage_thin",
            "confidence_floor": pat["corpus_confidence"] if pat else 0.0,
            "generation_prompt": (
                f"Generate a realistic {arch_type} architecture diagram in Mermaid format. "
                f"Include at least {(pat['trigger']['node_count_min'] + 2) if pat else 5} nodes. "
                f"Do NOT replicate existing corpus entries. "
                f"Focus on underrepresented topology variants."
            ),
            "priority": priority,
            "forced_gap": False,
            "demand_weight": demand_weight,
            "miss_count": miss_count,
            "variant_count": variant_count,
            "total_queries": total_queries,
        })
        gap_id += 1

    # Pass 2: demand-only gaps for well-sampled types with high miss rate
    all_queried_types = set(demand_weights.keys())
    for arch_type in sorted(all_queried_types - seen_types):
        # arch_type queried but not in corpus (genuinely new)
        dw = demand_weights[arch_type]
        if dw["demand_weight"] <= DEMAND_THRESHOLD:
            continue

        gaps.append({
            "id": f"GAP-{gap_id:03d}",
            "region": f"arch_type:{arch_type}",
            "type": "query_miss",
            "confidence_floor": 0.0,
            "generation_prompt": (
                f"Generate a realistic {arch_type} architecture diagram in Mermaid format. "
                f"This type has been queried {dw['total_queries']} times with "
                f"{dw['miss_count']} misses — no pattern exists for it yet."
            ),
            "priority": round(dw["demand_weight"] * DEMAND_ALPHA, 3),
            "forced_gap": False,
            "demand_weight": dw["demand_weight"],
            "miss_count": dw["miss_count"],
            "variant_count": dw["variant_count"],
            "total_queries": dw["total_queries"],
        })
        gap_id += 1

    # Pass 3: variant gaps for well-sampled types with high variant miss rate
    for arch_type in sorted(all_queried_types & seen_types):
        count = by_type.get(arch_type, 0)
        if count < MIN_INSTANCES:
            continue  # already covered in Pass 1

        dw = demand_weights[arch_type]
        total = max(dw["total_queries"], 1)
        variant_rate = dw["variant_count"] / total
        miss_rate = dw["miss_count"] / total

        if variant_rate <= DEMAND_THRESHOLD and miss_rate <= DEMAND_THRESHOLD:
            continue

        pat = pattern_by_type.get(arch_type)
        gap_type = "variant" if variant_rate > miss_rate else "query_miss"

        gaps.append({
            "id": f"GAP-{gap_id:03d}",
            "region": f"arch_type:{arch_type}",
            "type": gap_type,
            "confidence_floor": pat["corpus_confidence"] if pat else 0.0,
            "generation_prompt": (
                f"Generate a {arch_type} architecture variant in Mermaid format. "
                f"This type has {count} corpus instances but queries return "
                f"{dw['variant_count']} variant misses and {dw['miss_count']} full misses. "
                f"Focus on topology variations not yet in the corpus."
            ),
            "priority": round(dw["demand_weight"] * DEMAND_ALPHA, 3),
            "forced_gap": False,
            "demand_weight": dw["demand_weight"],
            "miss_count": dw["miss_count"],
            "variant_count": dw["variant_count"],
            "total_queries": dw["total_queries"],
        })
        gap_id += 1

    # Forced gaps always sort to top regardless of computed priority
    gaps.sort(key=lambda g: (not g.get("forced_gap", False), -g["priority"]))

    return gaps


# ── Persistence: enrich existing brain gaps ───────────────────────────────────

def enrich_brain_gaps(
    brain_path: Optional[Path] = None,
    instances_path: Optional[Path] = None,
    interactions_path: Optional[Path] = None,
) -> dict:
    """
    Recompute gaps for an existing brain using current demand weights.
    Preserves forced_gap=True entries from benchmark calibration (Stage 6).
    Writes updated brain.json.

    Returns summary dict.
    """
    bp = brain_path or (REPORT_DIR / "ta_brain.json")
    ip = instances_path or INSTANCES_PATH
    xp = interactions_path or INTERACTIONS_PATH

    if not bp.exists():
        raise ValueError(f"Brain not found: {bp}")

    brain = json.loads(bp.read_text())
    patterns = brain.get("patterns", [])

    # Load instances
    instances = []
    if ip.exists():
        for line in ip.read_text().strip().splitlines():
            line = line.strip()
            if line:
                try:
                    instances.append(json.loads(line))
                except Exception:
                    pass

    # Preserve any forced gaps (Stage 6 — can't be regenerated here)
    forced = [g for g in brain.get("gaps", []) if g.get("forced_gap")]

    demand_weights = compute_gap_demand_weights(xp)
    fresh_gaps = detect_gaps_v2(instances, patterns, demand_weights)

    # Re-ID to avoid collisions with forced gaps
    all_gaps = fresh_gaps + forced
    for i, g in enumerate(all_gaps, start=1):
        g["id"] = f"GAP-{i:03d}"

    all_gaps.sort(key=lambda g: (not g.get("forced_gap", False), -g["priority"]))

    brain["gaps"] = all_gaps
    brain["gaps_enriched_ts"] = datetime.now(timezone.utc).isoformat()
    bp.write_text(json.dumps(brain, indent=2))

    return {
        "gaps_total": len(all_gaps),
        "gaps_coverage_thin": sum(1 for g in all_gaps if g.get("type") == "coverage_thin"),
        "gaps_query_miss": sum(1 for g in all_gaps if g.get("type") == "query_miss"),
        "gaps_variant": sum(1 for g in all_gaps if g.get("type") == "variant"),
        "gaps_forced": len(forced),
        "arch_types_with_demand": len(demand_weights),
        "enriched_ts": brain["gaps_enriched_ts"],
    }
