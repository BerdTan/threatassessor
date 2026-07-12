#!/usr/bin/env python3
"""
rerun-corpus — audit and selectively re-run corpus architectures.

Usage:
    python3 rerun-corpus.py                      # audit only (default)
    python3 rerun-corpus.py --ai-only            # re-run ai_system archs
    python3 rerun-corpus.py 21_agentic_ai_system # re-run one arch
    python3 rerun-corpus.py --all                # re-run all 26
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# ── Engine-fix reference dates ────────────────────────────────────────────────
# Archs with run_ts before these dates need re-running to pick up the fix.
ENGINE_FIXES = [
    # (iso_date, arch_types_affected, description)
    ("2026-07-12T00:00:00Z", {"ai_system"},
     "self_validation AI keywords + hop-coverage AI controls fix"),
]

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parents[4]
REPORT_DIR  = REPO_ROOT / "report"
ARCH_DIR    = REPO_ROOT / "tests" / "data" / "architectures"
TATB_SCRIPT = REPO_ROOT / ".claude" / "skills" / "tatb-score" / "scripts" / "tatb-score.py"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"


def _load_gt(arch_dir: Path) -> dict:
    gt_path = arch_dir / "ground_truth.json"
    if not gt_path.exists():
        return {}
    with open(gt_path) as f:
        return json.load(f)


def _tatb_score(arch: str) -> dict | None:
    r = subprocess.run(
        [sys.executable, str(TATB_SCRIPT), arch, "--json"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None


def _classify(arch: str, gt: dict) -> tuple[str, list[str]]:
    """Return (status, reasons) where status is STALE | META | OK."""
    meta = gt.get("metadata", {})
    arch_type = meta.get("architecture_type", "unknown")
    run_ts = meta.get("run_ts")
    reasons = []

    # Missing run_ts/run_id — pure display gap, score is unaffected
    if not run_ts:
        reasons.append("no run_ts (pre engine-metadata fix)")
    if not meta.get("pattern_sources"):
        reasons.append("no pattern_sources")

    # Check if engine fixes post-date the last run
    if run_ts:
        for fix_date, affected_types, fix_desc in ENGINE_FIXES:
            if arch_type in affected_types and run_ts < fix_date:
                reasons.append(f"pre-{fix_date[:10]} ({fix_desc})")

    if not reasons:
        return "OK", []

    # Distinguish: STALE = score-affecting fixes not applied; META = display only
    score_affecting = [r for r in reasons if "pre-" in r]
    if score_affecting:
        return "STALE", reasons
    return "META", reasons


def audit(archs: list[str]) -> list[dict]:
    rows = []
    for arch in archs:
        arch_dir = REPORT_DIR / arch
        gt = _load_gt(arch_dir)
        if not gt:
            rows.append({"arch": arch, "status": "SKIP", "reasons": ["no ground_truth.json"], "gt": {}})
            continue
        status, reasons = _classify(arch, gt)
        rows.append({"arch": arch, "status": status, "reasons": reasons, "gt": gt})
    return rows


def rerun_arch(arch: str) -> bool:
    mmd = ARCH_DIR / f"{arch}.mmd"
    if not mmd.exists():
        print(RED(f"  ✗ {arch}.mmd not found in {ARCH_DIR}"))
        return False
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "chatbot.main", "--gen-arch-truth", str(mmd)],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    elapsed = time.time() - t0
    if r.returncode != 0:
        print(RED(f"  ✗ {arch} failed ({elapsed:.0f}s)"))
        if r.stderr:
            print(DIM("    " + r.stderr.strip()[-200:]))
        return False
    print(GREEN(f"  ✓ {arch} ({elapsed:.0f}s)"))
    return True


def print_corpus_table(archs: list[str], label: str = ""):
    if label:
        print(f"\n{BOLD(label)}")
    print(f"\n  {'Arch':<42} {'Overall':>7} {'TTP':>5} {'Risk':>5} {'Plan':>5}  {'MITRE%':>7}")
    print("  " + "-" * 72)
    totals, count = [], 0
    for arch in sorted(archs):
        d = _tatb_score(arch)
        if not d:
            continue
        o = d["overall"]
        band = "Excellent" if o >= 85 else "Solid" if o >= 70 else "Weak" if o >= 55 else "Draft"
        color = GREEN if o >= 85 else (lambda s: s) if o >= 70 else AMBER if o >= 55 else RED
        print(f"  {arch:<42} {color(str(o)):>7}  {d['ttp']['score']:>4}  {d['risk']['score']:>4}  {d['plan']['score']:>4}  {d['ttp']['mitre_pct']:>6}%  {DIM(band)}")
        totals.append(o)
        count += 1
    if totals:
        avg = sum(totals) / len(totals)
        mn, mx = min(totals), max(totals)
        print("  " + "-" * 72)
        print(f"  {'Corpus avg':<42} {BOLD(f'{avg:.1f}'):>7}   min={mn}  max={mx}  n={count}")


def main():
    parser = argparse.ArgumentParser(description="Corpus re-run tool")
    parser.add_argument("arch", nargs="?", help="Single architecture name to re-run")
    parser.add_argument("--all",     action="store_true", help="Re-run all architectures")
    parser.add_argument("--ai-only", action="store_true", help="Re-run ai_system architectures only")
    args = parser.parse_args()

    all_archs = sorted(
        d.name for d in REPORT_DIR.iterdir()
        if d.is_dir() and (d / "ground_truth.json").exists()
    )

    # ── Audit pass ────────────────────────────────────────────────────────────
    rows = audit(all_archs)
    stale  = [r for r in rows if r["status"] == "STALE"]
    meta   = [r for r in rows if r["status"] == "META"]
    ok     = [r for r in rows if r["status"] == "OK"]
    skip   = [r for r in rows if r["status"] == "SKIP"]

    print(f"\n{BOLD('Corpus Staleness Audit')} — {len(all_archs)} architectures\n")
    for r in rows:
        arch = r["arch"]
        gt_meta = r["gt"].get("metadata", {})
        arch_type = gt_meta.get("architecture_type", "?")
        run_id = gt_meta.get("run_id", "—")
        if r["status"] == "STALE":
            tag = RED("STALE")
        elif r["status"] == "META":
            tag = AMBER("META ")
        elif r["status"] == "OK":
            tag = GREEN("OK   ")
        else:
            tag = DIM("SKIP ")
        reason_str = DIM("  " + " | ".join(r["reasons"])) if r["reasons"] else ""
        print(f"  {tag}  {arch:<45} {DIM(f'type={arch_type:<12}')} run_id={DIM(run_id[:35])}{reason_str}")

    print(f"\n  {GREEN(str(len(ok)))} OK · {AMBER(str(len(meta)))} META (display only) · {RED(str(len(stale)))} STALE (score-affecting) · {DIM(str(len(skip)))} SKIP")

    if stale:
        print(AMBER(f"\n  Score-affecting engine fixes not yet applied to: {', '.join(r['arch'] for r in stale)}"))
    if meta:
        print(DIM(f"  META archs have correct scores but missing run_id/pattern_sources — re-run optional"))

    # ── Determine which archs to re-run ──────────────────────────────────────
    to_rerun = []

    if args.arch:
        if args.arch not in all_archs:
            print(RED(f"\nArchitecture '{args.arch}' not found in report/"))
            sys.exit(1)
        to_rerun = [args.arch]
    elif args.all:
        to_rerun = all_archs
    elif args.ai_only:
        to_rerun = [
            r["arch"] for r in rows
            if r["gt"].get("metadata", {}).get("architecture_type") == "ai_system"
        ]
        if not to_rerun:
            print(AMBER("\n  No ai_system architectures found in report/"))
    elif stale:
        # Default: suggest re-running stale archs, don't auto-execute
        print(f"\n  To fix score-affecting gaps, run:")
        print(f"    {DIM('python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py --ai-only')}")
        print(f"  To refresh all display metadata:")
        print(f"    {DIM('python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py --all')}")

    if not to_rerun:
        # Audit-only mode: print current corpus table
        print_corpus_table(all_archs, "Current Corpus Scores")
        return

    # ── Re-run ────────────────────────────────────────────────────────────────
    print(f"\n{BOLD(f'Re-running {len(to_rerun)} architecture(s)...')}\n")
    succeeded, failed = [], []
    for arch in to_rerun:
        result = rerun_arch(arch)
        (succeeded if result else failed).append(arch)

    print(f"\n  Done: {GREEN(str(len(succeeded)))} succeeded · {RED(str(len(failed)))} failed")
    if failed:
        print(RED(f"  Failed: {', '.join(failed)}"))

    # ── Post-run corpus table ─────────────────────────────────────────────────
    if succeeded:
        print_corpus_table(all_archs, "Updated Corpus Scores")


if __name__ == "__main__":
    main()
