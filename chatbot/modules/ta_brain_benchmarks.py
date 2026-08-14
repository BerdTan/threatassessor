"""
TA Brain benchmark calibration — Stage 6.

Grounds pattern confidence in external reality via three sources:

1. Brier scoring — brain predicts technique/control frequencies for hold-out
   architectures; comparison to actual ground truth yields a calibration score.

2. Framework alignment floors — NIST CSF / CIS Controls / OWASP AI Security /
   ATLAS define minimum controls per arch_type. Patterns that don't cover these
   get a benchmark_confidence floor below 1.0.

3. Incident ingestion (stub) — AIID / AISI incidents can be ingested; brain
   predicts blind, divergences become forced gaps. Populated externally.

benchmark_confidence is updated in ta_brain.json after calibration.
Published confidence = min(corpus_confidence, benchmark_confidence) — enforced
in _run_infer. Before Stage 6, benchmark_confidence was always 1.0. Now it
reflects whether the brain's predictions match external reality.

Divergence rule: brier_combined > DIVERGENCE_THRESHOLD OR framework_confidence
< FRAMEWORK_DIVERGENCE_FLOOR → divergence → forced_gap=True in meta layer.

Determinism contract: all Brier math is pure. No LLM calls.
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
BRAIN_PATH = REPORT_DIR / "ta_brain.json"
BENCHMARKS_PATH = REPORT_DIR / "ta_brain_benchmarks.json"
INSTANCES_PATH = REPORT_DIR / "ta_brain_instances.jsonl"

# Brier score thresholds
DIVERGENCE_THRESHOLD = 0.35       # Brier > this → pattern systematically wrong
FRAMEWORK_DIVERGENCE_FLOOR = 0.40 # framework_confidence < this → divergence

# Brier → confidence mapping: linear over [0, 0.5]
# Brier=0.0 → conf=1.0, Brier=0.25 → conf=0.5 (random), Brier≥0.5 → conf=0.0
BRIER_SCALE = 0.5


# ── Framework floors ──────────────────────────────────────────────────────────

FRAMEWORK_FLOORS: dict = {
    "web_app": {
        "required_controls": [
            "mfa", "waf", "logging", "input validation",
            "patch management", "authentication",
        ],
        "floor_confidence": 0.70,
        "source": "OWASP Top 10 + CIS Controls v8",
    },
    "ai_system": {
        "required_controls": [
            "rate limiting", "input validation", "audit log",
            "api access control", "least privilege",
        ],
        "floor_confidence": 0.65,
        "source": "OWASP AI Security Top 10 + ATLAS",
    },
    "cloud": {
        "required_controls": [
            "iam", "logging", "encryption", "network segmentation",
            "mfa",
        ],
        "floor_confidence": 0.70,
        "source": "CIS AWS/Azure/GCP Benchmarks",
    },
    "iot": {
        "required_controls": [
            "firmware updates", "network segmentation",
            "authentication", "logging",
        ],
        "floor_confidence": 0.60,
        "source": "NIST IoT Security (SP 800-213)",
    },
    "generic": {
        "required_controls": [
            "logging", "authentication", "patch management",
            "least privilege",
        ],
        "floor_confidence": 0.60,
        "source": "NIST CSF v2.0",
    },
}


# ── Brier scoring (pure) ──────────────────────────────────────────────────────

def brier_score_set(predicted_freqs: dict, actual_set: set) -> float:
    """
    Precision-weighted Brier score over predicted items only.

    The brain is a top-K predictor, not an exhaustive enumerator.
    Scoring over the full union penalises recall gaps with max-penalty (1.0)
    per missed item — making 100%-precision partial coverage score as ~0.6.
    Instead: score only what was predicted. Brier=0 means every prediction
    was correct; Brier=1 means every prediction was wrong.

    Returns 0.5 (neutral) when nothing was predicted.
    """
    if not predicted_freqs:
        return 0.5

    total = sum(
        (freq - (1.0 if item in actual_set else 0.0)) ** 2
        for item, freq in predicted_freqs.items()
    )
    return round(total / len(predicted_freqs), 6)


def brier_to_confidence(brier: float) -> float:
    """Linear mapping: Brier=0 → 1.0, Brier=0.5 → 0.0, Brier>0.5 → 0.0."""
    return round(max(0.0, 1.0 - brier / BRIER_SCALE), 4)


def compute_framework_confidence(pattern: dict, arch_type: str) -> dict:
    """
    Compare pattern's predicted controls to framework-mandated floors.
    Returns {framework_confidence, coverage_ratio, missing_required, source}.
    """
    floor = FRAMEWORK_FLOORS.get(arch_type)
    if not floor:
        return {
            "framework_confidence": 1.0,
            "coverage_ratio": 1.0,
            "missing_required": [],
            "source": "uncalibrated",
        }

    required = {c.lower() for c in floor["required_controls"]}
    predicted = {c.lower() for c in pattern.get("predicts", {}).get("common_missing_controls", [])}

    # Also check control_frequencies keys
    freq_controls = {c.lower() for c in pattern.get("predicts", {}).get("control_frequencies", {})}
    predicted |= freq_controls

    matched = required & predicted
    missing = sorted(required - predicted)
    coverage = len(matched) / len(required) if required else 1.0

    # framework_confidence: floor + (1-floor) * coverage
    # → 0 coverage → floor_confidence, full coverage → 1.0
    fc = floor["floor_confidence"] + (1.0 - floor["floor_confidence"]) * coverage
    return {
        "framework_confidence": round(fc, 4),
        "coverage_ratio": round(coverage, 4),
        "missing_required": missing,
        "source": floor["source"],
    }


def calibrate_pattern_brier(
    pattern: dict,
    hold_out_instances: list,
    report_dir: Path,
) -> dict:
    """
    Compute Brier score for a pattern against matching hold-out instances.

    Returns calibration dict:
    {brier_technique, brier_control, brier_combined, benchmark_confidence_brier,
     samples_used, calibrated_hold_out}

    If no matching hold-out instances: returns samples_used=0, confidence=1.0.
    """
    arch_type = pattern.get("trigger", {}).get("arch_type", "")
    matching = [i for i in hold_out_instances if i.get("arch_type") == arch_type]

    if not matching:
        return {
            "brier_technique": None,
            "brier_control": None,
            "brier_combined": None,
            "benchmark_confidence_brier": 1.0,
            "samples_used": 0,
            "calibrated_hold_out": [],
        }

    tech_freqs = pattern.get("predicts", {}).get("technique_frequencies", {})
    ctrl_freqs = pattern.get("predicts", {}).get("control_frequencies", {})

    brier_tech_scores = []
    brier_ctrl_scores = []
    used_archs = []

    for inst in matching:
        arch_id = inst.get("arch_id", "")
        gt_path = report_dir / arch_id / "ground_truth.json"
        if not gt_path.exists():
            continue

        try:
            gt = json.loads(gt_path.read_text())
        except Exception as exc:
            logger.warning("Could not load %s: %s", gt_path, exc)
            continue

        # Actual techniques
        actual_techs = gt.get("techniques", [])
        if isinstance(actual_techs, dict):
            actual_techs = list(actual_techs.keys())
        actual_tech_set = set(actual_techs)

        # Actual missing controls
        actual_ctrls = (
            gt.get("controls_missing")
            or gt.get("data", {}).get("controls_missing", [])
        )
        actual_ctrl_set = {c.lower() for c in actual_ctrls}

        brier_t = brier_score_set(tech_freqs, actual_tech_set)
        brier_c = brier_score_set(
            {k.lower(): v for k, v in ctrl_freqs.items()},
            actual_ctrl_set,
        )

        brier_tech_scores.append(brier_t)
        brier_ctrl_scores.append(brier_c)
        used_archs.append(arch_id)

    if not used_archs:
        return {
            "brier_technique": None,
            "brier_control": None,
            "brier_combined": None,
            "benchmark_confidence_brier": 1.0,
            "samples_used": 0,
            "calibrated_hold_out": [],
        }

    avg_tech = round(sum(brier_tech_scores) / len(brier_tech_scores), 6)
    avg_ctrl = round(sum(brier_ctrl_scores) / len(brier_ctrl_scores), 6)
    combined = round(0.6 * avg_tech + 0.4 * avg_ctrl, 6)

    return {
        "brier_technique": avg_tech,
        "brier_control": avg_ctrl,
        "brier_combined": combined,
        "benchmark_confidence_brier": brier_to_confidence(combined),
        "samples_used": len(used_archs),
        "calibrated_hold_out": used_archs,
    }


# ── Full calibration pass ─────────────────────────────────────────────────────

def run_calibration(
    brain: dict,
    hold_out_instances: list,
    report_dir: Path = REPORT_DIR,
    existing_benchmarks: Optional[dict] = None,
) -> tuple:
    """
    Run full calibration pass over all patterns.

    Returns (updated_brain, benchmarks_dict).
    Pure computation — caller is responsible for persistence.

    Divergences found (Brier > DIVERGENCE_THRESHOLD or framework < floor):
    → benchmark_confidence updated in pattern
    → forced_gap created in brain.gaps (if not already present)
    """
    patterns = brain.get("patterns", [])
    brier_scores: dict = {}
    framework_results: dict = {}
    divergences: list = []
    new_forced_gaps: list = []

    updated_patterns = []

    for p in patterns:
        pid = p["id"]
        arch_type = p.get("trigger", {}).get("arch_type", "")

        # Brier calibration
        brier = calibrate_pattern_brier(p, hold_out_instances, report_dir)
        brier_scores[pid] = {**brier, "arch_type": arch_type}

        # Framework alignment
        fw = compute_framework_confidence(p, arch_type)
        framework_results[pid] = fw

        # Combined benchmark_confidence
        b_brier = brier["benchmark_confidence_brier"]
        b_fw = fw["framework_confidence"]
        b_combined = round(min(b_brier, b_fw), 4)

        p = dict(p)
        p["benchmark_confidence"] = b_combined

        # Divergence check
        is_divergent = (
            (brier["brier_combined"] is not None and
             brier["brier_combined"] > DIVERGENCE_THRESHOLD)
            or b_fw < FRAMEWORK_DIVERGENCE_FLOOR
        )

        if is_divergent:
            reason = []
            if brier["brier_combined"] is not None and brier["brier_combined"] > DIVERGENCE_THRESHOLD:
                reason.append(f"brier={brier['brier_combined']:.3f} > {DIVERGENCE_THRESHOLD}")
            if b_fw < FRAMEWORK_DIVERGENCE_FLOOR:
                reason.append(f"framework_conf={b_fw:.3f} < {FRAMEWORK_DIVERGENCE_FLOOR}")

            divergence = {
                "pattern_id": pid,
                "arch_type": arch_type,
                "reason": "; ".join(reason),
                "brier_combined": brier["brier_combined"],
                "framework_confidence": b_fw,
                "detected_ts": datetime.now(timezone.utc).isoformat(),
            }
            divergences.append(divergence)

            # Create forced gap if not already in brain.gaps
            existing_regions = {g["region"] for g in brain.get("gaps", [])}
            region = f"arch_type:{arch_type}"
            if region not in existing_regions:
                # Prefer framework gaps; fall back to pattern's common_missing_controls
                specific_gaps = (
                    fw.get("missing_required")
                    or p.get("predicts", {}).get("common_missing_controls", [])
                )
                new_forced_gaps.append({
                    "id": f"GAP-F{len(new_forced_gaps)+1:03d}",
                    "region": region,
                    "type": "benchmark_divergence",
                    "confidence_floor": b_combined,
                    "generation_prompt": (
                        f"Generate {arch_type} architecture variants that address the divergence: "
                        f"{'; '.join(reason)}. Focus on the specific gaps: "
                        f"{', '.join(specific_gaps)[:200]}."
                    ),
                    "priority": 0.9,   # forced gaps get high priority
                    "forced_gap": True,
                    "demand_weight": 0.0,
                    "miss_count": 0,
                    "variant_count": 0,
                    "total_queries": 0,
                })

        updated_patterns.append(p)

    updated_brain = dict(brain)
    updated_brain["patterns"] = updated_patterns
    if new_forced_gaps:
        updated_brain["gaps"] = brain.get("gaps", []) + new_forced_gaps

    benchmarks = {
        "version": 1,
        "calibrated_ts": datetime.now(timezone.utc).isoformat(),
        "brier_scores": brier_scores,
        "framework_results": framework_results,
        "framework_floors": FRAMEWORK_FLOORS,
        "divergences": divergences,
        "incidents": (existing_benchmarks or {}).get("incidents", []),
    }

    return updated_brain, benchmarks


def ingest_incident(
    incident: dict,
    benchmarks_path: Path = BENCHMARKS_PATH,
) -> dict:
    """
    Ingest an AIID/AISI incident record into the benchmark calibration store.

    incident dict fields:
      id, title, arch_type, date, techniques_actual (list), controls_missing_actual (list),
      source ("aiid"|"aisi"|"manual"), url (optional)

    Appends to benchmarks.incidents. Returns the incident entry.
    """
    required = ("id", "arch_type", "techniques_actual")
    missing = [f for f in required if f not in incident]
    if missing:
        raise ValueError(f"Incident missing required fields: {missing}")

    entry = {
        "id": incident["id"],
        "title": incident.get("title", ""),
        "arch_type": incident["arch_type"],
        "date": incident.get("date", ""),
        "source": incident.get("source", "manual"),
        "url": incident.get("url", ""),
        "techniques_actual": incident["techniques_actual"],
        "controls_missing_actual": incident.get("controls_missing_actual", []),
        "ingested_ts": datetime.now(timezone.utc).isoformat(),
    }

    benchmarks: dict = {}
    if benchmarks_path.exists():
        try:
            benchmarks = json.loads(benchmarks_path.read_text())
        except Exception:
            pass

    incidents = benchmarks.get("incidents", [])
    # Deduplicate by id
    if not any(i["id"] == entry["id"] for i in incidents):
        incidents.append(entry)
    benchmarks["incidents"] = incidents
    benchmarks_path.write_text(json.dumps(benchmarks, indent=2))

    return entry


def save_calibration(
    brain_path: Path = BRAIN_PATH,
    benchmarks_path: Path = BENCHMARKS_PATH,
    instances_path: Path = INSTANCES_PATH,
    report_dir: Path = REPORT_DIR,
    hold_out_arch_ids: Optional[set] = None,
) -> dict:
    """
    Run full calibration and persist both ta_brain.json and ta_brain_benchmarks.json.
    Returns summary dict.
    """
    if not brain_path.exists():
        raise ValueError(f"Brain not found: {brain_path}")

    brain = json.loads(brain_path.read_text())

    # Load hold-out instances
    if hold_out_arch_ids is None:
        from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS  # noqa: PLC0415
        hold_out_arch_ids = HOLD_OUT_ARCHS

    all_instances = []
    if instances_path.exists():
        for line in instances_path.read_text().strip().splitlines():
            line = line.strip()
            if line:
                try:
                    all_instances.append(json.loads(line))
                except Exception:
                    pass

    hold_out_instances = [i for i in all_instances if i["arch_id"] in hold_out_arch_ids]

    # Load existing benchmarks (preserve incidents)
    existing = {}
    if benchmarks_path.exists():
        try:
            existing = json.loads(benchmarks_path.read_text())
        except Exception:
            pass

    updated_brain, benchmarks = run_calibration(
        brain, hold_out_instances, report_dir, existing
    )

    # Bump pattern_version so cache entries built before this calibration are evicted
    updated_brain["pattern_version"] = updated_brain.get("pattern_version", 0) + 1

    brain_path.write_text(json.dumps(updated_brain, indent=2))
    benchmarks_path.write_text(json.dumps(benchmarks, indent=2))

    patterns_calibrated = sum(
        1 for v in benchmarks["brier_scores"].values()
        if v.get("samples_used", 0) > 0
    )
    avg_brier = None
    calibrated_scores = [
        v["brier_combined"] for v in benchmarks["brier_scores"].values()
        if v.get("brier_combined") is not None
    ]
    if calibrated_scores:
        avg_brier = round(sum(calibrated_scores) / len(calibrated_scores), 4)

    return {
        "patterns_total": len(updated_brain["patterns"]),
        "patterns_calibrated": patterns_calibrated,
        "patterns_uncalibrated": len(updated_brain["patterns"]) - patterns_calibrated,
        "avg_brier_combined": avg_brier,
        "divergences": len(benchmarks["divergences"]),
        "forced_gaps_added": len([g for g in updated_brain.get("gaps", [])
                                  if g.get("forced_gap") and g.get("type") == "benchmark_divergence"]),
        "hold_out_instances": len(hold_out_instances),
        "calibrated_ts": benchmarks["calibrated_ts"],
    }
