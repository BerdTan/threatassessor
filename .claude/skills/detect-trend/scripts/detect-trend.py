#!/usr/bin/env python3
"""
detect-trend — Per-rule firing trend analysis across governance_signals history.

Usage:
    python3 detect-trend.py 21_agentic_ai_system      # single arch
    python3 detect-trend.py --all                      # full corpus matrix
    python3 detect-trend.py --all --signal-only        # non-never rules only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

REPORT_DIR = REPO / "report"

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"

_TREND_ICON = {
    "new":     "★",
    "rising":  "↑",
    "stable":  "→",
    "falling": "↓",
    "cleared": "✓",
    "never":   "—",
}

_TREND_COLOR = {
    "new":     lambda s: f"\033[35m{s}\033[0m",   # magenta
    "rising":  GREEN,
    "stable":  DIM,
    "falling": AMBER,
    "cleared": GREEN,
    "never":   DIM,
}


def _trend_cell(trend: str, width: int = 10) -> str:
    icon  = _TREND_ICON.get(trend, "?")
    label = f"{icon} {trend}"
    col   = _TREND_COLOR.get(trend, DIM)
    return col(f"{label:<{width}}")


def show_single_arch(arch_name: str, signal_only: bool = False) -> None:
    from chatbot.harness.rule_trend_evaluator import RuleTrendEvaluator

    arch_dir = REPORT_DIR / arch_name
    if not arch_dir.exists():
        print(RED(f"  Architecture not found: {arch_name}"))
        sys.exit(1)

    ev = RuleTrendEvaluator()
    trends = ev.compute_arch(arch_dir)

    hist_path = arch_dir / "governance_signals_history.jsonl"
    n_runs = 0
    if hist_path.exists():
        with hist_path.open() as f:
            n_runs = sum(1 for l in f if l.strip())

    print(f"\n{BOLD('detect-trend')} — {BOLD(arch_name)}")
    print(f"  History: {n_runs} run{'s' if n_runs != 1 else ''} recorded")
    if n_runs < 2:
        print(f"  {AMBER('Note: fewer than 2 runs — only new/never trends available')}")
    print()

    header = f"  {'Rule':<14} {'Trend':<14} {'Runs':>5}  {'Fired':>5}  {'Rate':>6}  Last 5"
    print(header)
    print(f"  {'─'*14} {'─'*14} {'─'*5}  {'─'*5}  {'─'*6}  {'─'*10}")

    for rid, tr in sorted(trends.items()):
        if signal_only and tr.trend == "never":
            continue
        last5 = "".join("█" if b else "░" for b in tr.last_n[-5:])
        rate  = f"{tr.fire_rate:.0%}" if tr.total_runs else "n/a"
        print(f"  {DIM(f'{rid:<14}')} {_trend_cell(tr.trend, 14)} "
              f"{tr.total_runs:>5}  {tr.fired_runs:>5}  {rate:>6}  {DIM(last5)}")
    print()


def show_corpus(signal_only: bool = False) -> None:
    from chatbot.harness.rule_trend_evaluator import RuleTrendEvaluator

    ev = RuleTrendEvaluator()
    corpus = ev.compute_corpus(REPORT_DIR)

    if not corpus:
        print(DIM("  No architectures with governance_signals.json found."))
        return

    rule_ids = ev._rule_ids
    archs    = sorted(corpus.keys())

    # Summary: how many archs have each rule as non-never
    print(f"\n{BOLD('detect-trend')} — {len(archs)} corpus architectures\n")

    # Per-rule summary row
    print(f"  {'Rule':<14} {'Coverage':<10} {'Trends across corpus'}")
    print(f"  {'─'*14} {'─'*10} {'─'*40}")

    for rid in rule_ids:
        results = [corpus[a][rid] for a in archs if rid in corpus[a]]
        non_never = [r for r in results if r.trend != "never"]
        if signal_only and not non_never:
            continue

        trend_counts: dict = {}
        for r in non_never:
            trend_counts[r.trend] = trend_counts.get(r.trend, 0) + 1

        pct = round(len(non_never) / len(archs) * 100) if archs else 0
        cov_str = f"{len(non_never)}/{len(archs)} ({pct}%)"

        parts = []
        for trend in ("new", "rising", "stable", "falling", "cleared"):
            n = trend_counts.get(trend, 0)
            if n:
                icon = _TREND_ICON[trend]
                col  = _TREND_COLOR[trend]
                parts.append(col(f"{icon}{n}"))

        trend_summary = "  ".join(parts) if parts else DIM("all never")
        cov_col = GREEN if pct >= 50 else (AMBER if pct > 0 else DIM)
        print(f"  {DIM(f'{rid:<14}')} {cov_col(f'{cov_str:<10}')} {trend_summary}")

    print()

    # Detail: archs with interesting (non-never) trends
    interesting = {
        a: {rid: corpus[a][rid] for rid in rule_ids
            if corpus[a].get(rid) and corpus[a][rid].trend != "never"}
        for a in archs
        if any(corpus[a].get(rid) and corpus[a][rid].trend != "never"
               for rid in rule_ids)
    }

    if interesting:
        print(f"{BOLD('Architectures with active signals:')}\n")
        for arch, rules in sorted(interesting.items()):
            hist_path = REPORT_DIR / arch / "governance_signals_history.jsonl"
            n_runs = 0
            if hist_path.exists():
                with hist_path.open() as f:
                    n_runs = sum(1 for l in f if l.strip())
            print(f"  {BOLD(arch)} ({n_runs} runs)")
            for rid, tr in sorted(rules.items()):
                rate = f"{tr.fire_rate:.0%}" if tr.total_runs else "n/a"
                last5 = "".join("█" if b else "░" for b in tr.last_n[-5:])
                print(f"    {_trend_cell(tr.trend, 10)} {rid:<14} "
                      f"fired {tr.fired_runs}/{tr.total_runs}  {DIM(last5)}")
            print()


def main() -> None:
    parser = argparse.ArgumentParser(description="DETECT rule firing trend analysis")
    parser.add_argument("arch", nargs="?", help="Architecture name for single-arch view")
    parser.add_argument("--all", action="store_true", help="Show trend matrix for full corpus")
    parser.add_argument("--signal-only", action="store_true",
                        help="Show only rules with non-never trends")
    args = parser.parse_args()

    if args.arch:
        show_single_arch(args.arch, signal_only=args.signal_only)
    elif args.all:
        show_corpus(signal_only=args.signal_only)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
