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

    # Classify each unmatched item so we can give a concrete next step per root cause.
    _SM_STRUCTURAL = re.compile(
        r'^\[sm\].*\[structural\]|'
        r'^define rto|^add bcp|^reposition api gateway|'
        r'^introduce a software|^add a vendor|^add privileged|'
        r'^implement microseg|^map all l0', re.I
    )
    _GENERIC_TIER = re.compile(
        r'^all (quick win|recommended|maximum|controls from)', re.I
    )
    _REAL_CONTROL = re.compile(
        r'^(network traffic|zero.trust micro|deception tech|application whitelist|'
        r'immutable infra|intrusion detect|detection sla|alert aggreg|api gateway$|'
        r'capability.based|zero.trust network|sca gate|supply chain)', re.I
    )

    sm_structural, generic_tier, real_missing = [], [], []
    for ctrl, freq in top_missing[:30]:
        if _SM_STRUCTURAL.search(ctrl):
            sm_structural.append((ctrl, freq))
        elif _GENERIC_TIER.search(ctrl):
            generic_tier.append((ctrl, freq))
        else:
            real_missing.append((ctrl, freq))

    print(bold("  1. Unmatched tier items — classified by root cause"))
    print()

    # ── 1a: SM structural boilerplate ──
    if sm_structural:
        print(f"  {amber('1a')}  {bold('SM [Structural] boilerplate')}  ({len(sm_structural)} patterns, appear as full sentences not control names)")
        print(dim("       These are ScrumMaster architectural recommendations injected into tier items."))
        print(dim("       They are NOT deployable controls and should not contribute to cost aggregation."))
        print()
        for ctrl, freq in sm_structural[:5]:
            stars = amber("●" * min(freq, 5)) + dim("●" * max(0, 5 - freq))
            print(f"       {stars}  {freq}×  {ctrl[:80]}")
        if len(sm_structural) > 5:
            print(dim(f"       … and {len(sm_structural)-5} more"))
        print()
        print(f"       {bold('Next step in TA:')} Filter [SM] [Structural] items from tier aggregation in")
        print(f"       {bold('chatbot/modules/control_cost_benchmark.py')} — add a pre-filter in")
        print(f"       {bold('aggregate_tier()')} that skips items starting with '[SM] [Structural]'.")
        print(f"       These belong in the SM action plan, not the cost rollup.")
        print()

    # ── 1b: Generic tier descriptions ──
    if generic_tier:
        print(f"  {amber('1b')}  {bold('Generic tier summaries')}  ({len(generic_tier)} patterns, e.g. \"all quick win controls\")")
        print(dim("       These are legacy MoE summary strings, not individual controls."))
        print()
        for ctrl, freq in generic_tier[:3]:
            stars = amber("●" * min(freq, 5)) + dim("●" * max(0, 5 - freq))
            print(f"       {stars}  {freq}×  {ctrl[:80]}")
        print()
        print(f"       {bold('Next step in TA:')} These originate in older MoE synthesis runs. Run a fresh")
        print(f"       Expert Review ({bold('/run-er')}) on affected archs to replace them with")
        print(f"       specific control names. No benchmark change needed.")
        print()

    # ── 1c: Real missing controls ──
    if real_missing:
        print(f"  {amber('1c')}  {bold('Real controls missing from benchmark')}  ({len(real_missing)} candidates)")
        print(dim("       These are specific, deployable controls that appear frequently but have no"))
        print(dim("       benchmark entry. Adding them will improve corpus coverage."))
        print()
        for ctrl, freq in real_missing[:12]:
            stars = amber("●" * min(freq, 5)) + dim("●" * max(0, 5 - freq))
            print(f"       {stars}  {freq}×  {ctrl[:80]}")
        print()
        print(f"       {bold('Next step in TA:')}")
        print(f"       1. Add entries to {bold('CONTROL_BENCHMARK')} in")
        print(f"          {bold('chatbot/modules/control_cost_benchmark.py')} (see section 4 below)")
        print(f"       2. Re-run {bold('/cost-estimate --self-eval')} to confirm coverage improved")
        print(f"       3. Run {bold('/cost-estimate --all')} to see updated corpus coverage %")
        print()

    if not (sm_structural or generic_tier or real_missing):
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

    # Suggested additions based on real missing controls only (skip SM boilerplate)
    if real_missing:
        print(bold("  4. Ready-to-paste benchmark additions"))
        print(dim("     Copy into CONTROL_BENCHMARK in chatbot/modules/control_cost_benchmark.py"))
        print()
        _SUGGEST = {
            "network traffic":    ("2–3 days", 2,  5,  "CIS Controls v8 IG2 safeguard 13.6 (network traffic analysis)"),
            "nta":                ("2–3 days", 2,  5,  "CIS Controls v8 IG2 safeguard 13.6"),
            "deception":          ("1–2 weeks",5, 15,  "Gartner Market Guide for Security Tools (2024) — deception tech"),
            "honeypot":           ("1–2 weeks",5, 15,  "Gartner Market Guide for Security Tools (2024)"),
            "honeytoken":         ("1–2 weeks",3, 10,  "Gartner Market Guide for Security Tools (2024)"),
            "application whitelist":("3–5 days",3,  8, "CIS Controls v8 IG2 safeguard 2.7 (allowlisting)"),
            "whitelisting":       ("3–5 days", 3,  8,  "CIS Controls v8 IG2 safeguard 2.7"),
            "immutable":          ("1–2 weeks",5, 15,  "CIS Controls v8 IG3 — immutable infrastructure"),
            "zero-trust network": ("2–4 weeks",20,50,  "NIST SP 800-207 (Zero Trust Architecture)"),
            "zero-trust micro":   ("1–2 weeks",10,30,  "NIST SP 800-207 §3.3 (microsegmentation)"),
            "intrusion detect":   ("2–3 days", 2,  5,  "CIS Controls v8 IG2 safeguard 13.3"),
            "detection sla":      ("1–2 weeks",5, 15,  "SANS Incident Response Survey (2024)"),
            "alert aggreg":       ("2–3 days", 2,  5,  "Gartner SIEM Market Guide (2024)"),
            "capability":         ("3–5 days", 3,  8,  "CIS Controls v8 IG2 safeguard 6.7 (access control)"),
            "rbac":               ("2–3 days", 2,  5,  "NIST SP 800-53 Rev 5 AC-2/AC-6"),
            "supply chain":       ("1–2 weeks",5, 15,  "NIST SP 800-161r1 (2022) C-SCRM"),
        }
        shown = set()
        for ctrl, freq in real_missing[:12]:
            for pattern, (effort, low_k, high_k, source) in _SUGGEST.items():
                if pattern in ctrl and pattern not in shown:
                    shown.add(pattern)
                    print(f"     {amber('+')}  \"{ctrl}\"")
                    print(f"          ({effort!r}, {low_k}, {high_k})  # {source}")
                    print()
                    break
            else:
                print(f"     {dim('?')}  \"{ctrl[:70]}\"  ({freq}× — no template; check SANS/Gartner for current range)")
                print()

    # ── Action summary ────────────────────────────────────────────────────────
    print(dim("─" * 70))
    print(bold("  Action summary"))
    print()
    if sm_structural:
        print(f"  {amber('A')}  Filter SM [Structural] items from aggregate_tier() in")
        print(f"       chatbot/modules/control_cost_benchmark.py")
        print(f"       → prevents sentence-length strings from deflating coverage %")
        print()
    if generic_tier:
        print(f"  {amber('B')}  Re-run Expert Review on archs with 'all quick win controls' items")
        print(f"       /run-er <arch>  — replaces generic summaries with specific control names")
        print()
    if real_missing:
        print(f"  {amber('C')}  Add {len(real_missing)} real controls to CONTROL_BENCHMARK (section 4 above)")
        print(f"       → then run /cost-estimate --all to verify corpus coverage improves")
        print()
    stale_refs = [n for n, _, _, stale, _ in refs if stale]
    if stale_refs:
        print(f"  {amber('D')}  Verify annual references are current edition:")
        for ref in stale_refs:
            print(f"       · {ref}")
        print(f"       → update year and cost ranges in CONTROL_BENCHMARK if newer data available")
        print()
    if not (sm_structural or generic_tier or real_missing or stale_refs):
        print(green("  ✓ Benchmark table is complete and references are current"))
        print()
    print(dim("  Re-run: /cost-estimate --self-eval  (after any benchmark changes)"))
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
