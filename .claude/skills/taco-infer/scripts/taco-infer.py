#!/usr/bin/env python3
"""TACO brain-only inference vs hold-out ground truth."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"


def _pct(a, b) -> str:
    if not b:
        return "n/a"
    return f"{len(a & b) / b * 100:.0f}%"


def _conf_color(conf: float) -> str:
    if conf >= 0.70: return GREEN
    if conf >= 0.50: return YELLOW
    return RED


def score_arch(arch_name: str, report_dir: Path) -> dict:
    from chatbot.modules.taco_agent import TACOAgent, TACOminiBrain

    gt_path = report_dir / arch_name / "ground_truth.json"
    if not gt_path.exists():
        return {"arch_name": arch_name, "error": "no ground_truth.json"}

    with open(gt_path) as f:
        gt = json.load(f)

    actual_techs = set()
    raw = gt.get("techniques") or []
    if isinstance(raw, dict):
        actual_techs = set(raw.keys())
    else:
        actual_techs = {str(t) for t in raw}

    actual_missing = {c.lower() for c in (gt.get("controls_missing") or [])}

    agent = TACOAgent(
        minis={"brain": TACOminiBrain()},
        threshold=1.1,
    )
    chain = agent.run(
        f"what are the main threats and missing controls for {arch_name}?",
        arch_name=arch_name,
    )
    hop = chain.hops[0]
    preds = hop.metadata.get("predictions") or {}

    pred_techs = set(preds.get("techniques") or [])
    pred_controls = {c.lower() for c in (preds.get("missing_controls") or [])}
    conf = hop.confidence or 0.0
    patterns_fired = len(hop.metadata.get("patterns_fired") or [])
    cache_route = hop.metadata.get("cache_route") or "?"

    tech_prec = f"{_pct(pred_techs, pred_techs)}" if pred_techs else "n/a"
    tech_rec  = _pct(pred_techs, actual_techs)
    ctrl_prec = _pct(pred_controls, pred_controls) if pred_controls else "n/a"
    ctrl_rec  = _pct(pred_controls, actual_missing)

    # Calibration hint
    groundedness = 0.0
    if actual_techs or actual_missing:
        tc = len(pred_techs & actual_techs) / max(1, len(actual_techs))
        cc = len(pred_controls & actual_missing) / max(1, len(actual_missing))
        groundedness = tc * 0.60 + cc * 0.40
    calibration_error = abs(conf - groundedness)
    hint = ""
    if calibration_error > 0.3:
        hint = f"  ⚠ confidence poorly calibrated (err={calibration_error:.2f})"

    return {
        "arch_name": arch_name,
        "conf": conf,
        "cache_route": cache_route,
        "patterns_fired": patterns_fired,
        "tech_precision": tech_prec,
        "tech_recall": tech_rec,
        "ctrl_precision": ctrl_prec,
        "ctrl_recall": ctrl_rec,
        "groundedness": f"{groundedness * 100:.0f}%",
        "hint": hint,
    }


def main():
    parser = argparse.ArgumentParser(description="TACO brain-only inference vs hold-out")
    parser.add_argument("--arch", default=None, help="Single arch_name")
    parser.add_argument("--all", dest="all_corpus", action="store_true", help="All corpus arches")
    parser.add_argument("--json", dest="raw_json", action="store_true", help="Raw JSON output")
    parser.add_argument("--report-dir", default=None)
    args = parser.parse_args()

    report_dir = Path(args.report_dir) if args.report_dir else ROOT / "report"

    from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS

    if args.arch:
        arch_list = [args.arch]
    elif args.all_corpus:
        arch_list = sorted(d.name for d in report_dir.iterdir()
                           if d.is_dir() and not d.name.startswith("brain")
                           and (d / "ground_truth.json").exists())
    else:
        arch_list = sorted(
            a for a in HOLD_OUT_ARCHS
            if (report_dir / a / "ground_truth.json").exists()
        )

    if not arch_list:
        sys.exit("No archs found.")

    results = [score_arch(a, report_dir) for a in arch_list]

    if args.raw_json:
        print(json.dumps(results, indent=2))
        return

    sep = "─" * 80
    print(f"\n{sep}")
    print("  TACO Brain Inference — hold-out evaluation")
    print(sep)
    for r in results:
        if "error" in r:
            print(f"\n  {r['arch_name']}  {RED}ERROR: {r['error']}{RESET}")
            continue
        col = _conf_color(r["conf"])
        print(f"\n  {r['arch_name']}")
        print(f"    conf={col}{r['conf']:.2f}{RESET}  route={r['cache_route']}  patterns={r['patterns_fired']}")
        print(f"    techs  precision={r['tech_precision']}  recall={r['tech_recall']}")
        print(f"    ctrls  precision={r['ctrl_precision']}  recall={r['ctrl_recall']}")
        print(f"    groundedness={r['groundedness']}")
        if r.get("hint"):
            print(f"{YELLOW}{r['hint']}{RESET}")
    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
