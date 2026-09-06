#!/usr/bin/env python3
"""
check-brain — Brain flywheel health monitor.

Reports pattern layer vitals and detects stagnation (no new ingest + no TACO feedback).
No LLM, no network — reads local brain files only.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from chatbot.modules.ta_brain_builder import BrainGuardian

COLS = {
    "healthy":  "\033[32m",   # green
    "warning":  "\033[33m",   # yellow
    "stagnant": "\033[31m",   # red
    "reset":    "\033[0m",
}


def _color(health: str, text: str) -> str:
    return f"{COLS.get(health, '')}{text}{COLS['reset']}"


def main() -> int:
    guardian = BrainGuardian()
    h = guardian.flywheel_health()

    health = h["health"]
    label = _color(health, health.upper())

    print(f"\n{'─'*52}")
    print(f"  TA Brain Flywheel Health  [{label}]")
    print(f"{'─'*52}")
    print(f"  Pattern version       : v{h['pattern_version']}")
    print(f"  Pattern count         : {h['pattern_count']}")
    print(f"  Total corpus instances: {h['total_instances']}")
    print(f"  Last rebuild          : {h['last_rebuild_days_ago']} days ago")
    print(f"  TACO feedback (30d)   : {h['taco_feedback_last_30d']}")
    print(f"  Stagnant              : {'YES ⚠' if h['stagnant'] else 'no'}")
    print(f"{'─'*52}")
    print(f"  {h['recommendation']}")
    print(f"{'─'*52}\n")

    # Thresholds
    issues = []
    if h["last_rebuild_days_ago"] > 30:
        issues.append(f"Brain not rebuilt in {h['last_rebuild_days_ago']:.0f} days — run /brain-grow")
    if h["taco_feedback_last_30d"] == 0:
        issues.append("No TACO feedback in 30d — users not flagging brain corrections")
    if h["total_instances"] < 5:
        issues.append(f"Only {h['total_instances']} corpus instances — brain needs more arch coverage")

    if issues:
        print("  Issues:")
        for issue in issues:
            print(f"    ⚠  {issue}")
        print()

    return 1 if h["stagnant"] else 0


if __name__ == "__main__":
    sys.exit(main())
