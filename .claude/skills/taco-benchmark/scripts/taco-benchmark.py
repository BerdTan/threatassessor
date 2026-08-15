#!/usr/bin/env python3
"""7-dimension TACO quality scorer CLI."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


DIMS = ["threat_relevant", "ttp_accurate", "risk_defensible", "plan_actionable",
        "groundedness", "confidence_calibration", "ciso_utility", "overall"]
DIM_SHORT = ["Threat", "TTP", "Risk", "Plan", "Ground", "Calib", "CISO", "Overall"]
MODE_COLORS = {"workspace": "\033[33m", "taco_brain": "\033[34m", "taco_rag": "\033[35m"}
RESET = "\033[0m"


def _fmt(v) -> str:
    if v is None:
        return "  n/a"
    return f"{float(v):5.0f}"


def _row(score) -> str:
    col = MODE_COLORS.get(score.mode, "")
    mode_pad = score.mode.ljust(10)
    vals = "  ".join(_fmt(getattr(score, d)) for d in DIMS)
    return f"  {col}{mode_pad}{RESET}  {vals}"


def _header() -> str:
    labels = "  ".join(f"{l:>5}" for l in DIM_SHORT)
    return f"  {'Mode':<10}  {labels}"


def main():
    parser = argparse.ArgumentParser(description="TACO 7-dimension benchmark scorer")
    parser.add_argument("--arch", default=None, help="Single arch_name to score")
    parser.add_argument("--json", dest="raw_json", action="store_true", help="Print raw JSON")
    parser.add_argument("--report-dir", default=None, help="Override report directory")
    args = parser.parse_args()

    from chatbot.modules.taco_benchmark import TACOBenchmark
    from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS

    report_dir = Path(args.report_dir) if args.report_dir else None
    bm = TACOBenchmark(report_dir=report_dir)

    results = []
    if args.arch:
        try:
            results.append(bm.score_arch(args.arch))
        except FileNotFoundError as exc:
            sys.exit(f"Error: {exc}")
    else:
        results = bm.score_hold_out()
        if not results:
            sys.exit("No HOLD_OUT_ARCHS with ground_truth.json found.")

    if args.raw_json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return

    sep = "─" * 90
    print(f"\n{sep}")
    print("  TACO Benchmark — 7-dimension quality scorer")
    print(f"{sep}")
    print(_header())
    print(sep)

    rag_overalls = []
    for result in results:
        print(f"\n  {result.arch_name}")
        for score in (result.workspace, result.taco_brain, result.taco_rag):
            print(_row(score))
            if score.mode == "taco_rag":
                rag_overalls.append(score.overall)

    print(f"\n{sep}")
    if rag_overalls:
        avg = sum(rag_overalls) / len(rag_overalls)
        print(f"  taco_rag overall avg ({len(rag_overalls)} arch{'s' if len(rag_overalls)!=1 else ''}): {avg:.0f}")
    print(sep)
    print()


if __name__ == "__main__":
    main()
