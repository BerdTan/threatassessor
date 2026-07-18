#!/usr/bin/env python3
"""
cost-estimate.py — Investment tier cost/effort estimator.

Reads MoE improvement_options from report directories, recomputes
effort and cost from the shared CONTROL_BENCHMARK table, prints a
breakdown table, and optionally self-evaluates the benchmark against
known industry sources to flag stale or missing entries.

Usage:
    python3 cost-estimate.py                      # most recent report/
    python3 cost-estimate.py 21_agentic_ai_system # single arch
    python3 cost-estimate.py --all                # full corpus
    python3 cost-estimate.py --self-eval          # audit the benchmark table
    python3 cost-estimate.py 21_agentic_ai_system --json
"""
import json
import os
import re
import sys
import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from chatbot.modules.control_cost_benchmark import (
    CONTROL_BENCHMARK, aggregate_tier, lookup, _cost_str, _EFFORT_RANK, _CITATION
)

# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):  return _c(t, "1")
def cyan(t):  return _c(t, "36")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def grey(t):  return _c(t, "2")
def dim(t):   return _c(t, "2")

REPORT_DIR = REPO / "report"

# ── Tier display config ───────────────────────────────────────────────────────
TIER_DISPLAY = {
    "quick_wins":  ("⚡", "Quick Wins",         green),
    "recommended": ("⭐", "Recommended Target",  amber),
    "maximum":     ("🔒", "Maximum Security",    red),
}

# ── Effort ordering for display ───────────────────────────────────────────────
EFFORT_ORDER = {v: k for k, v in enumerate(
    ["2–4 hours", "4–8 hours", "1–2 days", "2–3 days",
     "3–5 days", "1–2 weeks", "2–3 weeks", "2–4 weeks"]
)}


def _latest_arch() -> str:
    dirs = sorted(
        [d for d in REPORT_DIR.iterdir() if (d / "07_moe_orchestrator.json").exists()],
        key=lambda d: d.stat().st_mtime, reverse=True
    )
    if not dirs:
        sys.exit("No report directories with MoE data found.")
    return dirs[0].name


def _load_arch(arch_name: str):
    path = REPORT_DIR / arch_name / "07_moe_orchestrator.json"
    if not path.exists():
        sys.exit(f"MoE file not found: {path}")
    with open(path) as f:
        return json.load(f)


def _tier_items(moe: dict, tier_key: str):
    return moe.get("improvement_options", {}).get(tier_key, {}).get("items", [])


# ── Single-arch report ────────────────────────────────────────────────────────

def report_arch(arch_name: str, as_json: bool = False):
    moe = _load_arch(arch_name)
    opts = moe.get("improvement_options", {})

    results = {}
    for tier_key, (icon, label, colour) in TIER_DISPLAY.items():
        items = _tier_items(moe, tier_key)
        agg = aggregate_tier(items)
        results[tier_key] = {
            "label":            label,
            "icon":             icon,
            "items_total":      len(items),
            "items_matched":    len(agg.get("matched_controls", [])),
            "items_unmatched":  agg.get("unmatched_count", 0),
            "effort":           agg["effort"],
            "cost":             agg["cost"],
            "cost_source":      agg["cost_source"],
            "citation":         agg.get("citation", ""),
            "matched_controls": agg.get("matched_controls", []),
            "raw_items":        items,
        }

    if as_json:
        print(json.dumps(results, indent=2))
        return

    _print_arch_report(arch_name, results)


def _print_arch_report(arch_name: str, results: dict):
    print()
    print(bold(cyan(f"Cost-Effort Estimate — {arch_name}")))
    print(dim("─" * 70))
    print(f"  {dim('Source:')} {dim(_CITATION[:90] + '…')}")
    print()

    for tier_key, r in results.items():
        icon, label, colour = TIER_DISPLAY[tier_key]
        matched = r["items_matched"]
        total   = r["items_total"]
        cov_pct = round(matched / total * 100) if total else 0
        cov_bar = green(f"{cov_pct}%") if cov_pct >= 70 else amber(f"{cov_pct}%") if cov_pct >= 40 else red(f"{cov_pct}%")

        print(bold(f"  {icon}  {label}"))
        print(f"     Effort:   {colour(r['effort']) if r['effort'] != 'not estimated' else grey('not estimated')}")
        print(f"     Cost:     {colour(r['cost']) if r['cost'] != 'cost not estimated' else grey('cost not estimated')}")
        print(f"     Coverage: {cov_bar}  ({matched}/{total} controls matched to benchmark)")

        if r["matched_controls"]:
            print(f"     {dim('Breakdown:')}")
            for ctrl, effort, cost in r["matched_controls"]:
                print(f"       {dim('·')} {ctrl[:50]:<50s}  {effort:<12s}  {cost}")

        if r["items_unmatched"] > 0:
            # Show unmatched items so the user can add them to the benchmark
            unmatched_items = _find_unmatched(r["raw_items"], r["matched_controls"])
            n_un = r["items_unmatched"]
            print(f"     {amber('⚠  ' + str(n_un) + ' item(s) not in benchmark table:')}")
            for item in unmatched_items[:5]:
                clean = re.split(r'\s+(?:at |—|with )', item, maxsplit=1)[0].strip()[:60]
                print(f"       {dim('·')} {clean}")
        print()

    print(dim("─" * 70))
    print(dim(f"  Effort = critical-path control (longest calendar task in tier)"))
    print(dim(f"  Cost   = sum of per-control benchmark ranges across matched controls"))
    print()


def _find_unmatched(raw_items: list, matched: list) -> list:
    matched_names = {m[0].lower() for m in matched}
    unmatched = []
    for item in raw_items:
        clean = re.split(r'\s+(?:at |—|with )', item, maxsplit=1)[0].strip()
        if clean.lower() not in matched_names and item.lower() not in matched_names:
            unmatched.append(item)
    return unmatched


# ── Corpus report ─────────────────────────────────────────────────────────────

def report_corpus():
    archs = sorted([
        d.name for d in REPORT_DIR.iterdir()
        if (d / "07_moe_orchestrator.json").exists()
    ])
    if not archs:
        sys.exit("No MoE reports found in report/")

    print()
    print(bold(cyan(f"Cost-Effort Corpus — {len(archs)} architectures")))
    print(dim("─" * 90))
    print(f"  {'Architecture':<35s}  {'⚡ Quick Wins':<24s}  {'⭐ Recommended':<24s}  {'🔒 Maximum':<20s}  {'Cov%'}")
    print(dim("  " + "─" * 86))

    corpus_rows = []
    for arch in archs:
        moe = _load_arch(arch)
        row = {"arch": arch, "tiers": {}}
        total_items = 0
        total_matched = 0
        for tier_key in TIER_DISPLAY:
            items = _tier_items(moe, tier_key)
            agg = aggregate_tier(items)
            row["tiers"][tier_key] = agg
            total_items   += len(items)
            total_matched += len(agg.get("matched_controls", []))
        row["cov_pct"] = round(total_matched / total_items * 100) if total_items else 0
        corpus_rows.append(row)

        qw  = row["tiers"]["quick_wins"]
        rec = row["tiers"]["recommended"]
        mx  = row["tiers"]["maximum"]

        def _cell(agg):
            if agg["cost_source"] == "not_available":
                return dim("—")
            return f"{agg['effort'][:10]} / {agg['cost'][:10]}"

        cov = row["cov_pct"]
        cov_str = green(f"{cov}%") if cov >= 70 else amber(f"{cov}%") if cov >= 40 else red(f"{cov}%")
        print(f"  {arch:<35s}  {_cell(qw):<24s}  {_cell(rec):<24s}  {_cell(mx):<20s}  {cov_str}")

    # Summary
    avg_cov = round(sum(r["cov_pct"] for r in corpus_rows) / len(corpus_rows))
    print(dim("  " + "─" * 86))
    print(f"  {'Corpus avg coverage':<35s}  {'':<24s}  {'':<24s}  {'':<20s}  {green(str(avg_cov)+'%') if avg_cov>=70 else amber(str(avg_cov)+'%')}")
    print()
    print(dim(f"  Coverage = % of tier items matched to a benchmark entry"))
    print(dim(f"  Low coverage (< 70%) means unmatched controls — run --self-eval to add them"))
    print()


# ── Self-evaluation: audit benchmark table ────────────────────────────────────

def self_eval():
    """
    Audit CONTROL_BENCHMARK for:
    1. Controls appearing across the corpus that are NOT in the table
    2. Stale/missing industry references per tier
    3. Entries that may warrant revision based on current market data
    """
    print()
    print(bold(cyan("Benchmark Self-Evaluation")))
    print(dim("─" * 70))
    print()

    # Collect all unmatched control candidates from the corpus
    archs = [
        d.name for d in REPORT_DIR.iterdir()
        if (d / "07_moe_orchestrator.json").exists()
    ]

    candidate_freq: dict = {}
    for arch in archs:
        moe = _load_arch(arch)
        for tier_key in TIER_DISPLAY:
            items = _tier_items(moe, tier_key)
            agg = aggregate_tier(items)
            unmatched = _find_unmatched(items, agg.get("matched_controls", []))
            for item in unmatched:
                clean = re.split(r'\s+(?:at |—|with )', item, maxsplit=1)[0].strip().lower()
                candidate_freq[clean] = candidate_freq.get(clean, 0) + 1

    # Sort by frequency
    top_missing = sorted(candidate_freq.items(), key=lambda x: -x[1])

    print(bold("  1. Controls appearing in corpus NOT in benchmark table"))
    print(dim("     (freq = number of architectures where this control appears unmatched)"))
    print()
    if top_missing:
        for ctrl, freq in top_missing[:20]:
            stars = amber("●" * min(freq, 5)) + dim("●" * max(0, 5 - freq))
            print(f"     {stars}  {freq}×  {ctrl}")
    else:
        print(green("     ✓ All corpus controls matched"))
    print()

    # Tier coverage by effort band
    print(bold("  2. Benchmark table coverage by effort tier"))
    print()
    bands: dict = {}
    for ctrl, (effort, low_k, high_k) in CONTROL_BENCHMARK.items():
        bands.setdefault(effort, []).append(ctrl)
    for effort in sorted(bands, key=lambda e: EFFORT_ORDER.get(e, 99)):
        ctrls = bands[effort]
        print(f"     {effort:<14s}  {len(ctrls):>3d} entries  {dim(', '.join(ctrls[:5])) + (dim(' …') if len(ctrls)>5 else '')}")
    print()

    # Flag entries that may be stale
    print(bold("  3. Industry reference health"))
    print()
    refs = [
        ("CIS Controls v8 IG1–IG3",                 "2021",  "2024", False,
         "Stable — IG tiers unchanged in v8.1 (2024 update)"),
        ("NIST SP 800-53 Rev 5",                     "2020",  "2024", False,
         "Stable — Rev 5 current; Rev 6 not yet published"),
        ("NIST SP 800-207 (Zero Trust Architecture)", "2020",  "2024", False,
         "Stable — architecture guidance, not cost-specific"),
        ("NIST AI RMF 1.0",                          "2023",  "2024", False,
         "Stable — AI RMF 1.1 draft not yet final"),
        ("Gartner Market Guide for Security Tools",   "2024",  "2025", True,
         "⚠ Annual publication — verify edition is 2024 or later"),
        ("SANS Security Spending Survey",             "2024",  "2025", True,
         "⚠ Annual survey — verify edition is 2024 or later"),
        ("OWASP LLM Top 10",                         "2025",  "2025", False,
         "Current — v1.1 (2025) is the latest stable release"),
    ]
    for name, pub_year, check_year, needs_verify, note in refs:
        flag = amber("⚠ verify") if needs_verify else green("✓ current")
        print(f"     {flag}  {name} ({pub_year})")
        print(f"            {dim(note)}")
    print()

    # Suggested additions based on missing corpus controls
    if top_missing:
        print(bold("  4. Suggested additions to CONTROL_BENCHMARK"))
        print(dim("     Add these to chatbot/modules/control_cost_benchmark.py"))
        print()
        # Map common unmatched patterns to suggested benchmark entries
        _SUGGEST = {
            "prompt sanitiz":     ("2–3 days", 3, 8,  "OWASP LLM Top 10 (2025) LLM01"),
            "output filter":      ("2–3 days", 3, 8,  "OWASP LLM Top 10 (2025) LLM01"),
            "capability":         ("3–5 days", 3, 8,  "CIS Controls v8 IG2 safeguard 6.7"),
            "rbac":               ("2–3 days", 2, 5,  "NIST SP 800-53 Rev 5 AC-2/AC-6"),
            "intrusion detection":("2–3 days", 2, 5,  "CIS Controls v8 IG2 safeguard 13.3"),
            "detection sla":      ("1–2 weeks",5, 15, "SANS Incident Response Survey (2024)"),
            "alert aggreg":       ("2–3 days", 2, 5,  "Gartner SIEM Guide (2024)"),
            "supply chain":       ("1–2 weeks",5, 15, "NIST SP 800-161r1 (2022) C-SCRM"),
            "zero-day":           ("1–2 weeks",5, 15, "CIS Controls v8 IG3"),
            "deception":          ("1–2 weeks",5, 15, "Gartner Market Guide (2024)"),
        }
        shown = set()
        for ctrl, freq in top_missing[:15]:
            for pattern, (effort, low_k, high_k, source) in _SUGGEST.items():
                if pattern in ctrl and pattern not in shown:
                    shown.add(pattern)
                    print(f"     \"{ctrl}\"")
                    print(f"       → ({effort!r}, {low_k}, {high_k})  # {source}")
                    print()
                    break
            else:
                if freq >= 2:
                    print(f"     \"{ctrl}\"  ({freq}× in corpus — no suggested range, manual review needed)")
                    print()

    print(dim("─" * 70))
    print(dim("  Run with a specific arch to see per-tier breakdown:"))
    print(dim("  python3 cost-estimate.py 21_agentic_ai_system"))
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Investment tier cost/effort estimator")
    parser.add_argument("arch", nargs="?", help="Architecture name (default: most recent)")
    parser.add_argument("--all",        action="store_true", help="Score all corpus architectures")
    parser.add_argument("--self-eval",  action="store_true", help="Audit benchmark table quality")
    parser.add_argument("--json",       action="store_true", help="JSON output (single arch only)")
    args = parser.parse_args()

    if args.self_eval:
        self_eval()
    elif args.all:
        report_corpus()
    else:
        arch = args.arch or _latest_arch()
        report_arch(arch, as_json=args.json)


if __name__ == "__main__":
    main()
