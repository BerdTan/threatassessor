#!/usr/bin/env python3
"""
report_prune.py — Identify and optionally delete redundant report subfolders.

Detects two categories of prunable folders:
  1. Numbered variant runs — report/<arch>_N where report/<arch> also exists
     (repeated bench/gym pipeline runs; brain has already ingested them)
  2. Synthetic training reports — report/syn_* folders
     (source MMDs remain in report/brain/synthetic_queue/)

Also flags stale codebase context graphs in .claude/graphs/ (updated > 60 days ago).

Usage:
  python3 report_prune.py           # dry-run: list candidates, no deletion
  python3 report_prune.py --clean   # delete prunable folders
  python3 report_prune.py --graphs  # only check graph staleness, skip report scan
"""

import argparse
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR  = ROOT / "report"
GRAPHS_DIR  = ROOT / ".claude" / "graphs"
DECISIONS_FILE = ROOT / "docs" / "DECISIONS.md"

GRAPH_STALE_DAYS     = 60
DECISIONS_STALE_DAYS = 7

# Folders that must never be deleted regardless of name pattern
KEEP_PATTERNS = {
    "_boxing_bot",   # active cache used by ta_boxing.py
}


# ── detection ─────────────────────────────────────────────────────────────────

def find_canonical_arches() -> set[str]:
    """Names of report subfolders that have NO numeric suffix — the canonical runs."""
    canonicals = set()
    for d in REPORT_DIR.iterdir():
        if not d.is_dir():
            continue
        if re.search(r"_\d+$", d.name):
            continue
        if d.name in ("brain", "taclaw", "taclaw_investigator", "bench", "architectures"):
            continue
        canonicals.add(d.name)
    return canonicals


def find_numbered_variants(canonicals: set[str]) -> list[Path]:
    """Folders matching <canonical_arch>_N where the canonical also exists."""
    variants = []
    for d in sorted(REPORT_DIR.iterdir()):
        if not d.is_dir():
            continue
        if any(k in d.name for k in KEEP_PATTERNS):
            continue
        m = re.match(r"^(.+)_(\d+)$", d.name)
        if m and m.group(1) in canonicals:
            variants.append(d)
    return variants


def find_synthetic_reports() -> list[Path]:
    """Folders with the syn_* prefix (synthetic brain training reports)."""
    return sorted(
        d for d in REPORT_DIR.iterdir()
        if d.is_dir() and d.name.startswith("syn_")
    )


# ── DECISIONS.md freshness ────────────────────────────────────────────────────

def check_decisions_freshness() -> tuple[date | None, int]:
    """Return (date_of_most_recent_entry, days_since). None if unparseable."""
    try:
        text = DECISIONS_FILE.read_text(encoding="utf-8")
    except OSError:
        return None, -1
    # Most recent entry header: "## Session NNN — YYYY-MM-DD"
    matches = re.findall(r"^## Session \d+\s*[—–-]+\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if not matches:
        return None, -1
    try:
        latest = date.fromisoformat(matches[0])
    except ValueError:
        return None, -1
    age = (date.today() - latest).days
    return latest, age


# ── graph staleness ───────────────────────────────────────────────────────────

def parse_graph_date(path: Path) -> date | None:
    """Extract the `updated:` date from a graph's YAML frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^updated:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def check_graph_staleness() -> list[tuple[Path, date, int]]:
    """Return list of (graph_path, updated_date, days_since) for stale graphs."""
    today = date.today()
    stale = []
    for mmd in sorted(GRAPHS_DIR.glob("*.mmd")):
        updated = parse_graph_date(mmd)
        if updated is None:
            continue
        age = (today - updated).days
        if age > GRAPH_STALE_DAYS:
            stale.append((mmd, updated, age))
    return stale


# ── display ───────────────────────────────────────────────────────────────────

def folder_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / 1_048_576


def print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clean",  action="store_true", help="Delete prunable folders (default: dry-run)")
    parser.add_argument("--graphs", action="store_true", help="Only check graph staleness")
    args = parser.parse_args()

    if not REPORT_DIR.exists():
        print(f"report/ not found at {REPORT_DIR}", file=sys.stderr)
        sys.exit(1)

    # ── health checks ────────────────────────────────────────
    stale_graphs = check_graph_staleness()
    decisions_date, decisions_age = check_decisions_freshness()

    if args.graphs:
        print_section("Graph staleness check")
        if stale_graphs:
            for path, updated, age in stale_graphs:
                print(f"  ⚠  {path.name:<30}  updated {updated}  ({age}d ago)")
        else:
            print(f"  ✓  All graphs updated within {GRAPH_STALE_DAYS} days")
        print_section("DECISIONS.md freshness check")
        if decisions_date is None:
            print("  ⚠  Could not parse most recent entry date")
        elif decisions_age > DECISIONS_STALE_DAYS:
            print(f"  ⚠  Last entry: {decisions_date}  ({decisions_age}d ago — add an entry)")
        else:
            print(f"  ✓  Last entry: {decisions_date}  ({decisions_age}d ago)")
        return

    # ── report scan ───────────────────────────────────────────
    canonicals = find_canonical_arches()
    variants   = find_numbered_variants(canonicals)
    synthetics = find_synthetic_reports()
    prunable   = variants + synthetics

    mode = "DELETE" if args.clean else "DRY-RUN"
    print(f"\n## report-prune  [{mode}]")

    # Numbered variants
    print_section(f"Numbered variant runs  ({len(variants)} folders)")
    if variants:
        for d in variants:
            mb = folder_size_mb(d)
            print(f"  {'[DELETE]' if args.clean else '[prune] '}  {d.name:<40}  {mb:.1f} MB")
    else:
        print("  ✓  None found")

    # Synthetic reports
    print_section(f"Synthetic training reports  ({len(synthetics)} folders)")
    if synthetics:
        for d in synthetics:
            mb = folder_size_mb(d)
            print(f"  {'[DELETE]' if args.clean else '[prune] '}  {d.name:<40}  {mb:.1f} MB")
    else:
        print("  ✓  None found")

    # Totals
    total_mb = sum(folder_size_mb(d) for d in prunable)
    print(f"\n  Total prunable: {len(prunable)} folders  ({total_mb:.1f} MB)")

    # Graphs
    print_section("Graph staleness check")
    if stale_graphs:
        for path, updated, age in stale_graphs:
            print(f"  ⚠  {path.name:<30}  updated {updated}  ({age}d ago — review needed)")
    else:
        print(f"  ✓  All graphs updated within {GRAPH_STALE_DAYS} days")

    # DECISIONS.md
    print_section("DECISIONS.md freshness check")
    if decisions_date is None:
        print("  ⚠  Could not parse most recent entry date")
    elif decisions_age > DECISIONS_STALE_DAYS:
        print(f"  ⚠  Last entry: {decisions_date}  ({decisions_age}d ago — add a DECISIONS entry)")
    else:
        print(f"  ✓  Last entry: {decisions_date}  ({decisions_age}d ago)")

    # Execute deletion
    if args.clean:
        if not prunable:
            print("\n  Nothing to delete.")
            return
        print(f"\n  Deleting {len(prunable)} folders...")
        deleted = 0
        for d in prunable:
            try:
                shutil.rmtree(d)
                deleted += 1
            except OSError as e:
                print(f"  ✗  {d.name}: {e}", file=sys.stderr)
        print(f"  ✓  Deleted {deleted}/{len(prunable)} folders  ({total_mb:.1f} MB freed)")
    else:
        if prunable:
            print(f"\n  Run with --clean to delete these {len(prunable)} folders.")


if __name__ == "__main__":
    main()
