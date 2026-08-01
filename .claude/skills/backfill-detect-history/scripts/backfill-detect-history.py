#!/usr/bin/env python3
"""
backfill-detect-history — Seed synthetic baseline history for corpus architectures.

Writes one governance_signals_history.jsonl entry per architecture using the
current governance_signals.json snapshot as a baseline data point.

Usage:
    python3 backfill-detect-history.py           # skip if history exists
    python3 backfill-detect-history.py --force   # overwrite existing history
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

REPORT_DIR   = REPO / "report"
BASELINE_TS  = "2026-08-01T00:00:00Z"
BASELINE_RID = "backfill-baseline"
HISTORY_FILE = "governance_signals_history.jsonl"

GREEN = lambda s: f"\033[32m{s}\033[0m"
AMBER = lambda s: f"\033[33m{s}\033[0m"
DIM   = lambda s: f"\033[2m{s}\033[0m"
BOLD  = lambda s: f"\033[1m{s}\033[0m"
CYAN  = lambda s: f"\033[36m{s}\033[0m"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic baseline detection history")
    parser.add_argument("--force", action="store_true",
                        help="Re-seed even if governance_signals_history.jsonl already exists")
    args = parser.parse_args()

    if not REPORT_DIR.exists():
        print(f"  No report directory found at {REPORT_DIR}")
        sys.exit(1)

    archs = sorted(
        d for d in REPORT_DIR.iterdir()
        if d.is_dir() and (d / "governance_signals.json").exists()
    )

    print(f"\n{BOLD(CYAN('backfill-detect-history'))} — {len(archs)} architectures\n")

    seeded = skipped = errors = 0

    for arch_dir in archs:
        hist_path = arch_dir / HISTORY_FILE
        sig_path  = arch_dir / "governance_signals.json"
        arch_name = arch_dir.name

        if hist_path.exists() and not args.force:
            # Count existing entries
            with hist_path.open() as f:
                n = sum(1 for l in f if l.strip())
            print(f"  {DIM('SKIP')} {arch_name:<45} {DIM(f'{n} entries already')}")
            skipped += 1
            continue

        try:
            signals = json.loads(sig_path.read_text(encoding="utf-8"))
            entry = json.dumps({
                "run_id":  BASELINE_RID,
                "ts":      BASELINE_TS,
                "arch":    arch_name,
                "signals": signals,
            }, separators=(",", ":"))

            mode = "w" if args.force else "a"
            with hist_path.open(mode, encoding="utf-8") as f:
                f.write(entry + "\n")

            print(f"  {GREEN('SEED')} {arch_name:<45} {DIM('baseline entry written')}")
            seeded += 1

        except Exception as exc:
            print(f"  {AMBER('ERR ')} {arch_name:<45} {AMBER(str(exc)[:60])}")
            errors += 1

    print(f"\n  {'─'*60}")
    print(f"  {GREEN(f'{seeded} seeded')}  {DIM(f'{skipped} skipped')}  "
          + (f"  {AMBER(f'{errors} errors')}" if errors else ""))
    print(f"\n  Run {BOLD('/detect-trend --all')} to see the baseline snapshot.\n")


if __name__ == "__main__":
    main()
