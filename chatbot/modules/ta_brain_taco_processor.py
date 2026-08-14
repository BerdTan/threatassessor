"""
TACO processor — Stage 7: closes the brain←→TACO feedback loop.

Single coordinated pass over all available signals:
  1. Feedback summary (Stage 3 interaction log) — full scan, idempotent
  2. Confidence decay (Stage 4) — applied from fresh base, not accumulated
  3. Confirmation → benchmark_confidence boost (new in Stage 7)
  4. Demand-weighted gap enrichment (Stage 5)
  5. Calibration priority heatmap (new in Stage 7) — cache hit frequency
     × thin benchmark_confidence → flags patterns needing more calibration data
  6. Processor state update — tracks last_run_ts, total interactions processed

Idempotency fix: Stage 4's run_confidence_decay accumulates from stored counts +
new counts, causing double-counting on repeated runs. Stage 7 resets stored
feedback counts to 0 before applying the full log scan, so the result is always
consistent with the complete interaction history regardless of how many times
the processor has run.

Determinism contract: no LLM calls. All math is pure.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chatbot.modules.ta_brain_confidence import (
    CONF_CEIL,
    CONF_FLOOR,
    run_confidence_decay,
)
from chatbot.modules.ta_brain_feedback import get_feedback_summary
from chatbot.modules.ta_brain_gaps import compute_gap_demand_weights, detect_gaps_v2

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report"
BRAIN_PATH = REPORT_DIR / "ta_brain.json"
BENCHMARKS_PATH = REPORT_DIR / "ta_brain_benchmarks.json"
INSTANCES_PATH = REPORT_DIR / "ta_brain_instances.jsonl"
INTERACTIONS_PATH = REPORT_DIR / "ta_brain_interactions.jsonl"
CACHE_PATH = REPORT_DIR / "ta_brain_cache.json"
STATE_PATH = REPORT_DIR / "ta_brain_processor_state.json"

# Confirmation → benchmark_confidence boost weight
CONFIRM_BOOST_WEIGHT = 0.1  # each confirmation adds up to this to benchmark_confidence

# Calibration priority: flag patterns with high cache demand + low benchmark_confidence
CALIB_PRIORITY_HIT_THRESHOLD = 3     # cache hits above this
CALIB_PRIORITY_CONF_THRESHOLD = 0.7  # benchmark_confidence below this


# ── Processor state ───────────────────────────────────────────────────────────

def load_processor_state(state_path: Path = STATE_PATH) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except Exception:
            pass
    return {"last_run_ts": None, "total_interactions_processed": 0, "runs": 0}


def save_processor_state(state: dict, state_path: Path = STATE_PATH) -> None:
    try:
        state_path.write_text(json.dumps(state, indent=2))
    except Exception as exc:
        logger.warning("Could not save processor state: %s", exc)


# ── Idempotent confidence reset ───────────────────────────────────────────────

def reset_pattern_feedback_counts(patterns: list) -> list:
    """
    Zero out stored feedback counts and restore corpus_confidence to its
    distiller-computed base before applying a full log scan.

    Without the corpus_confidence restore, repeated runs accumulate decay on
    top of already-decayed values — producing confidence drift that diverges
    from the true feedback history.
    """
    reset = []
    for p in patterns:
        pr = dict(p)
        pr["feedback_confirmed_count"] = 0
        pr["feedback_wrong_count"] = 0
        pr["suspect"] = False
        # Restore to distiller base so decay is computed from scratch each run
        base = pr.get("corpus_confidence_base")
        if base is not None:
            pr["corpus_confidence"] = base
        reset.append(pr)
    return reset


# ── Confirmation → benchmark boost ───────────────────────────────────────────

def apply_confirmation_boost(
    pattern: dict,
    total_confirmed: int,
    benchmarks: dict,
) -> float:
    """
    Lift benchmark_confidence slightly for patterns with confirmed predictions.
    Formula: boost = min(CONFIRM_BOOST_WEIGHT, confirmed / (confirmed + 1))
    Cap: cannot exceed corpus_confidence.

    Returns updated benchmark_confidence.
    """
    if total_confirmed == 0:
        return pattern.get("benchmark_confidence", 1.0)

    # Find calibration entry for this pattern
    pid = pattern["id"]
    brier_entry = benchmarks.get("brier_scores", {}).get(pid, {})
    samples = brier_entry.get("samples_used", 0)

    current_bc = pattern.get("benchmark_confidence", 1.0)

    # Boost proportional to confirmation count, diminishing returns
    boost = CONFIRM_BOOST_WEIGHT * (1.0 - 1.0 / (total_confirmed + 1))
    new_bc = round(min(
        CONF_CEIL,
        min(pattern.get("corpus_confidence", 1.0), current_bc + boost),
    ), 4)
    return new_bc


# ── Calibration priority heatmap ──────────────────────────────────────────────

def compute_calibration_priority(
    patterns: list,
    benchmarks: dict,
    cache_path: Path = CACHE_PATH,
) -> list:
    """
    Identify patterns that are heavily queried but have thin benchmark_confidence.
    These are the highest-value calibration targets.

    Returns list of {pattern_id, arch_type, hit_count, benchmark_confidence,
                     priority_score, reason}.
    """
    # Load cache stats
    cache_hits: dict = {}
    if cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text())
            for key, entry in raw.get("entries", {}).items():
                arch_type = entry.get("arch_type", "")
                hit_count = entry.get("hit_count", 0)
                cache_hits[arch_type] = cache_hits.get(arch_type, 0) + hit_count
        except Exception:
            pass

    priorities = []
    for p in patterns:
        pid = p["id"]
        arch_type = p.get("trigger", {}).get("arch_type", "")
        bc = p.get("benchmark_confidence", 1.0)
        hit_count = cache_hits.get(arch_type, 0)
        samples = benchmarks.get("brier_scores", {}).get(pid, {}).get("samples_used", 0)

        is_high_demand = hit_count >= CALIB_PRIORITY_HIT_THRESHOLD
        is_thin_calibration = bc < CALIB_PRIORITY_CONF_THRESHOLD or samples == 0

        if is_high_demand and is_thin_calibration:
            reasons = []
            if samples == 0:
                reasons.append("no Brier calibration samples")
            if bc < CALIB_PRIORITY_CONF_THRESHOLD:
                reasons.append(f"benchmark_confidence={bc:.2f} < {CALIB_PRIORITY_CONF_THRESHOLD}")

            priority_score = round(
                (hit_count / max(hit_count, 1)) * (1.0 - bc), 4
            )
            priorities.append({
                "pattern_id": pid,
                "arch_type": arch_type,
                "hit_count": hit_count,
                "benchmark_confidence": bc,
                "calibration_samples": samples,
                "priority_score": priority_score,
                "reason": "; ".join(reasons),
            })

    return sorted(priorities, key=lambda x: x["priority_score"], reverse=True)


# ── Main processor ────────────────────────────────────────────────────────────

def run_taco_processor(
    brain_path: Path = BRAIN_PATH,
    benchmarks_path: Path = BENCHMARKS_PATH,
    instances_path: Path = INSTANCES_PATH,
    interactions_path: Path = INTERACTIONS_PATH,
    cache_path: Path = CACHE_PATH,
    state_path: Path = STATE_PATH,
) -> dict:
    """
    Single coordinated TACO processor pass. Idempotent — can be run repeatedly.

    Applies all feedback signals to brain + benchmarks in the correct order.
    Returns a summary of what changed.
    """
    if not brain_path.exists():
        raise ValueError(f"Brain not found: {brain_path}")

    brain = json.loads(brain_path.read_text())
    benchmarks: dict = {}
    if benchmarks_path.exists():
        try:
            benchmarks = json.loads(benchmarks_path.read_text())
        except Exception:
            pass

    state = load_processor_state(state_path)

    # ── Step 1: Full feedback summary ─────────────────────────────────────────
    feedback_summary = get_feedback_summary(interactions_path)
    by_sig = feedback_summary.get("by_pattern_sig", {})

    # Aggregate confirmed counts by arch_type (for boost step)
    confirmed_by_type: dict = {}
    for key, counts in by_sig.items():
        parts = key.split(":", 2)
        if len(parts) == 3 and parts[2] == "infer":
            arch_type = parts[1]
            confirmed_by_type[arch_type] = (
                confirmed_by_type.get(arch_type, 0) + counts.get("confirmed", 0)
            )

    # ── Step 2: Idempotent confidence decay ───────────────────────────────────
    # Reset stored counts first → apply full log scan from base
    brain_reset = dict(brain)
    brain_reset["patterns"] = reset_pattern_feedback_counts(brain["patterns"])
    brain_decayed = run_confidence_decay(brain_reset, feedback_summary)

    # ── Step 3: Confirmation → benchmark_confidence boost ─────────────────────
    updated_patterns = []
    for p in brain_decayed["patterns"]:
        arch_type = p.get("trigger", {}).get("arch_type", "")
        total_confirmed = confirmed_by_type.get(arch_type, 0)
        new_bc = apply_confirmation_boost(p, total_confirmed, benchmarks)
        p = dict(p)
        p["benchmark_confidence"] = new_bc
        updated_patterns.append(p)
    brain_decayed["patterns"] = updated_patterns

    # ── Step 4: Demand-weighted gap enrichment ─────────────────────────────────
    # Load instances for gap detection
    instances: list = []
    if instances_path.exists():
        for line in instances_path.read_text().strip().splitlines():
            line = line.strip()
            if line:
                try:
                    instances.append(json.loads(line))
                except Exception:
                    pass

    demand_weights = compute_gap_demand_weights(interactions_path)
    forced_existing = [g for g in brain_decayed.get("gaps", []) if g.get("forced_gap")]
    fresh_gaps = detect_gaps_v2(instances, brain_decayed["patterns"], demand_weights)

    # Re-ID to avoid collisions
    all_gaps = fresh_gaps + forced_existing
    for i, g in enumerate(all_gaps, start=1):
        g["id"] = f"GAP-{i:03d}"
    all_gaps.sort(key=lambda g: (not g.get("forced_gap", False), -g["priority"]))
    brain_decayed["gaps"] = all_gaps

    # ── Step 5: Calibration priority heatmap ──────────────────────────────────
    calib_priority = compute_calibration_priority(
        brain_decayed["patterns"], benchmarks, cache_path
    )
    benchmarks["calibration_priority"] = calib_priority
    benchmarks["processor_run_ts"] = datetime.now(timezone.utc).isoformat()

    # ── Step 6: Write everything ───────────────────────────────────────────────
    brain_decayed["taco_processor_ts"] = datetime.now(timezone.utc).isoformat()
    brain_path.write_text(json.dumps(brain_decayed, indent=2))
    if benchmarks_path.exists() or calib_priority:
        benchmarks_path.write_text(json.dumps(benchmarks, indent=2))

    # ── Step 7: Update state ───────────────────────────────────────────────────
    state["last_run_ts"] = brain_decayed["taco_processor_ts"]
    state["total_interactions_processed"] = (
        feedback_summary.get("total_queries", 0)
        + feedback_summary.get("total_feedback", 0)
    )
    state["runs"] = state.get("runs", 0) + 1
    save_processor_state(state, state_path)

    # Summary
    suspect_count = sum(1 for p in brain_decayed["patterns"] if p.get("suspect"))
    avg_bc = round(
        sum(p.get("benchmark_confidence", 1.0) for p in brain_decayed["patterns"])
        / max(len(brain_decayed["patterns"]), 1),
        4,
    )

    return {
        "patterns": len(brain_decayed["patterns"]),
        "suspect_patterns": suspect_count,
        "avg_benchmark_confidence": avg_bc,
        "gaps_total": len(all_gaps),
        "gaps_forced": len(forced_existing),
        "calibration_priority_count": len(calib_priority),
        "total_queries_in_log": feedback_summary.get("total_queries", 0),
        "total_feedback_in_log": feedback_summary.get("total_feedback", 0),
        "demand_arch_types": len(demand_weights),
        "run_ts": brain_decayed["taco_processor_ts"],
        "processor_runs_total": state["runs"],
    }
