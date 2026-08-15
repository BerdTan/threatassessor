"""
TA Brain confidence decay — Stage 4.

Reads the interaction log feedback summary and adjusts corpus_confidence
for each pattern in ta_brain.json. Pure math — no LLM calls.

Decay model:
  confirmed   → corpus_confidence += DELTA_POSITIVE / sqrt(evidence_count)
  wrong       → corpus_confidence -= DELTA_NEGATIVE  (fixed, evidence-independent)
  Bounds      → corpus_confidence clamped to [CONF_FLOOR, 1.0]

Suspect flag: pattern marked suspect=True when
  feedback_wrong_count >= SUSPECT_MIN_WRONG
  AND wrong_rate = wrong / (confirmed + wrong) > SUSPECT_WRONG_RATE

Suspect patterns still serve predictions. Published confidence
= min(corpus_confidence, benchmark_confidence) — a suspect pattern
that has decayed will already show lower published confidence to callers.

Design invariant: build_brain (distiller) recomputes corpus_confidence
from scratch on a full rebuild, so decay adjustments are ephemeral
corrections between rebuilds, not permanent state.
"""

import json
import logging
import math
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


BRAIN_PATH = _brain_dir() / "ta_brain.json"

# Decay constants
DELTA_POSITIVE_BASE = 0.05   # per confirmation, scaled by 1/sqrt(evidence_count)
DELTA_NEGATIVE = 0.10        # per wrong feedback, fixed
CONF_FLOOR = 0.05            # patterns never go fully silent
CONF_CEIL = 1.0

# Suspect thresholds
SUSPECT_MIN_WRONG = 3
SUSPECT_WRONG_RATE = 0.5     # wrong / (confirmed + wrong) > this → suspect


# ── Pure functions ────────────────────────────────────────────────────────────

def delta_positive(evidence_count: int) -> float:
    """Evidence-scaled confidence boost per confirmed feedback."""
    return round(DELTA_POSITIVE_BASE / max(math.sqrt(evidence_count), 1.0), 6)


def apply_feedback_to_pattern(
    pattern: dict,
    confirmed_count: int,
    wrong_count: int,
) -> dict:
    """
    Pure function — returns a copy of the pattern with updated confidence fields.

    Adds/updates:
      corpus_confidence       — clamped to [CONF_FLOOR, CONF_CEIL]
      feedback_confirmed_count
      feedback_wrong_count
      suspect                 — True when wrong_count ≥ SUSPECT_MIN_WRONG
                                AND wrong_rate > SUSPECT_WRONG_RATE
    """
    p = dict(pattern)
    evidence = p.get("evidence_count", 1)
    prior_conf = p.get("corpus_confidence", 1.0)

    # Accumulate from stored counts + new increments
    total_confirmed = p.get("feedback_confirmed_count", 0) + confirmed_count
    total_wrong = p.get("feedback_wrong_count", 0) + wrong_count

    # Apply deltas
    new_conf = prior_conf
    if confirmed_count > 0:
        new_conf += confirmed_count * delta_positive(evidence)
    if wrong_count > 0:
        new_conf -= wrong_count * DELTA_NEGATIVE

    new_conf = round(max(CONF_FLOOR, min(CONF_CEIL, new_conf)), 6)

    # Suspect check
    total_votes = total_confirmed + total_wrong
    wrong_rate = total_wrong / total_votes if total_votes > 0 else 0.0
    suspect = total_wrong >= SUSPECT_MIN_WRONG and wrong_rate > SUSPECT_WRONG_RATE

    p["corpus_confidence"] = new_conf
    p["feedback_confirmed_count"] = total_confirmed
    p["feedback_wrong_count"] = total_wrong
    p["suspect"] = suspect

    return p


def run_confidence_decay(brain: dict, feedback_summary: dict) -> dict:
    """
    Pure function — returns updated brain dict with decayed pattern confidence.

    Aggregates all feedback entries by arch_type (many topology_sigs → one pattern),
    then applies apply_feedback_to_pattern to each affected pattern.

    Adds brain-level metadata: feedback_decay_ts, feedback_total_confirmed,
    feedback_total_wrong.
    """
    patterns = brain.get("patterns", [])
    by_sig = feedback_summary.get("by_pattern_sig", {})

    # Aggregate feedback by arch_type (patterns cover all sigs of same arch_type)
    # Key format: "{topology_sig}:{arch_type}:{mode}"
    confirmed_by_type: dict = {}
    wrong_by_type: dict = {}

    for key, counts in by_sig.items():
        parts = key.split(":", 2)
        if len(parts) < 3:
            continue
        _, arch_type, mode = parts
        if mode != "infer":          # only infer mode feeds pattern confidence
            continue
        confirmed_by_type[arch_type] = (
            confirmed_by_type.get(arch_type, 0) + counts.get("confirmed", 0)
        )
        wrong_by_type[arch_type] = (
            wrong_by_type.get(arch_type, 0) + counts.get("wrong", 0)
        )

    updated_patterns = []
    total_confirmed = 0
    total_wrong = 0
    patterns_updated = 0

    for p in patterns:
        arch_type = p.get("trigger", {}).get("arch_type", "")
        c = confirmed_by_type.get(arch_type, 0)
        w = wrong_by_type.get(arch_type, 0)

        if c > 0 or w > 0:
            updated = apply_feedback_to_pattern(p, c, w)
            updated_patterns.append(updated)
            total_confirmed += c
            total_wrong += w
            patterns_updated += 1
        else:
            # No feedback for this arch_type — preserve existing fields
            if "feedback_confirmed_count" not in p:
                p = dict(p)
                p["feedback_confirmed_count"] = 0
                p["feedback_wrong_count"] = 0
                p["suspect"] = False
            updated_patterns.append(p)

    updated_brain = dict(brain)
    updated_brain["patterns"] = updated_patterns
    updated_brain["feedback_decay_ts"] = datetime.now(timezone.utc).isoformat()
    updated_brain["feedback_total_confirmed"] = total_confirmed
    updated_brain["feedback_total_wrong"] = total_wrong
    updated_brain["patterns_updated_this_decay"] = patterns_updated

    return updated_brain


# ── Persistence ───────────────────────────────────────────────────────────────

def save_confidence_decay(
    brain_path: Path = BRAIN_PATH,
    interactions_path: Optional[Path] = None,
) -> dict:
    """
    Read brain + feedback summary → run decay → write updated brain.

    Returns a summary dict of what changed. Raises ValueError if brain not found.
    """
    from chatbot.modules.ta_brain_feedback import get_feedback_summary  # noqa: PLC0415

    if not brain_path.exists():
        raise ValueError(f"Brain not found: {brain_path}")

    brain = json.loads(brain_path.read_text())
    feedback_summary = get_feedback_summary(interactions_path)

    updated_brain = run_confidence_decay(brain, feedback_summary)

    # Compute per-pattern deltas for the summary
    old_by_id = {p["id"]: p.get("corpus_confidence", 1.0) for p in brain.get("patterns", [])}
    new_by_id = {p["id"]: p.get("corpus_confidence", 1.0)
                 for p in updated_brain.get("patterns", [])}
    deltas = {
        pid: round(new_by_id[pid] - old_by_id[pid], 6)
        for pid in new_by_id
        if abs(new_by_id[pid] - old_by_id.get(pid, 1.0)) > 1e-8
    }
    suspect_patterns = [
        p["id"] for p in updated_brain["patterns"] if p.get("suspect")
    ]

    brain_path.write_text(json.dumps(updated_brain, indent=2))

    return {
        "patterns_updated": updated_brain["patterns_updated_this_decay"],
        "total_confirmed": updated_brain["feedback_total_confirmed"],
        "total_wrong": updated_brain["feedback_total_wrong"],
        "confidence_deltas": deltas,
        "suspect_patterns": suspect_patterns,
        "decay_ts": updated_brain["feedback_decay_ts"],
    }
