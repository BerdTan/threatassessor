#!/usr/bin/env python3
"""
decisions-archive — time-based archive and recall for DECISIONS.md.

Dry-run by default. Use --confirm to execute.

Archive:  entries older than --days (default 60) with no open KEEP signals
Recall:   pull a specific entry back from the archive into DECISIONS.md
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[4]
DECISIONS = ROOT / "docs" / "DECISIONS.md"
ARCHIVE = ROOT / "docs" / "archive" / "DECISIONS_archive.md"
MEMORY_INDEX = Path.home() / ".claude" / "projects" / "-mnt-c-BACKUP-DEV-TEST" / "memory" / "MEMORY.md"

# Signals that force KEEP regardless of age
KEEP_PATTERNS = [
    r"\bpending\b", r"\bplanned\b", r"\bdeferred\b", r"\bnot yet\b",
    r"\bfollow.up\b", r"\bfollow up\b", r"\bopen\b", r"\bTODO\b",
    r"⬅", r"⬜", r"\bEngine Item 17\b", r"\bEngine Item 18\b",
    r"\bJev\b", r"\bTAgym\b", r"\bDETECT-QC-009\b", r"\bDETECT-MCP-005\b",
    r"\bnot started\b", r"\bnot implemented\b", r"\bpromote\b",
]

ARCHIVE_HEADER = """# DECISIONS Archive

Entries older than 60 days (default) with no open signals are moved here.
They remain in the same `### Entry NNN` format and are fully editable.
Use `--recall N` to pull any entry back into DECISIONS.md when needed.

---

"""


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_decisions(text: str) -> tuple[str, list[dict]]:
    """Return (preamble, entries). Preamble is everything before first ### entry."""
    first_match = re.search(r"^###\s", text, re.MULTILINE)
    if not first_match:
        return text, []
    preamble = text[: first_match.start()]
    return preamble, _parse_entry_blocks(text[first_match.start():])


def _parse_entry_blocks(text: str) -> list[dict]:
    parts = re.compile(r"(?=^###\s)", re.MULTILINE).split(text)
    entries = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        first_line = part.splitlines()[0]
        num_match = re.search(r"Entry\s+(\d+)", first_line, re.IGNORECASE)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", first_line)
        entries.append({
            "num": int(num_match.group(1)) if num_match else None,
            "date": date_match.group(1) if date_match else None,
            "title": first_line.lstrip("#").strip(),
            "body": part,
        })
    return entries


def _session_date_for(entry_body: str, full_text: str) -> str | None:
    """Find the ## Session ... date line that appears before this entry in full_text."""
    pos = full_text.find(entry_body[:80])
    if pos == -1:
        return None
    preceding = full_text[:pos]
    session_matches = list(re.finditer(r"^##\s+Session[^\n]*(\d{4}-\d{2}-\d{2})", preceding, re.MULTILINE))
    if session_matches:
        return session_matches[-1].group(0)
    return None


# ── Classification ────────────────────────────────────────────────────────────

def classify(entry: dict, memory_text: str, days: int) -> tuple[str, str]:
    """Return (KEEP|ARCHIVE, reason). KEEP is the safe default."""
    body = entry["body"]

    # Hard-coded open signals — always KEEP
    for pat in KEEP_PATTERNS:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            return "KEEP", f"open signal: '{m.group(0)}'"

    # Referenced in open priorities block in MEMORY.md
    if entry["num"] and memory_text:
        open_block = re.search(r"## Current priorities.*", memory_text, re.DOTALL)
        if open_block and re.search(rf"\b{entry['num']}\b", open_block.group(0)):
            return "KEEP", "referenced in open priorities"

    # Age check — core of the new logic
    if entry["date"]:
        try:
            age = datetime.now() - datetime.strptime(entry["date"], "%Y-%m-%d")
            if age < timedelta(days=days):
                return "KEEP", f"recent ({entry['date']}, {age.days}d old)"
        except ValueError:
            pass
    else:
        # No date found — keep to be safe
        return "KEEP", "no date found"

    return "ARCHIVE", f"older than {days} days, no open signals"


def load_memory() -> str:
    try:
        return MEMORY_INDEX.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ── Archive ───────────────────────────────────────────────────────────────────

def run_archive(confirm: bool, min_entry: int | None, days: int, verbose: bool) -> int:
    if not DECISIONS.exists():
        print(f"ERROR: {DECISIONS} not found", file=sys.stderr)
        return 1

    text = DECISIONS.read_text(encoding="utf-8")
    memory_text = load_memory()
    preamble, entries = parse_decisions(text)

    to_keep: list[tuple[dict, str, str]] = []
    to_archive: list[tuple[dict, str, str]] = []

    for entry in entries:
        if min_entry and entry["num"] and entry["num"] >= min_entry:
            to_keep.append((entry, "KEEP", f">= floor {min_entry}"))
            continue
        verdict, reason = classify(entry, memory_text, days)
        (to_archive if verdict == "ARCHIVE" else to_keep).append((entry, verdict, reason))

    # Print table
    print(f"\n{'Entry':<8} {'Status':<8} {'Reason':<38}  Title")
    print("-" * 108)
    for entry, verdict, reason in sorted(to_keep + to_archive, key=lambda x: -(x[0]["num"] or 0)):
        tag = "KEEP   " if verdict == "KEEP" else "ARCHIVE"
        title = entry["title"][:50]
        print(f"  {str(entry['num'] or '?'):<6} {tag}  {reason:<38}  {title}")
        if verbose and verdict == "ARCHIVE":
            for line in entry["body"].splitlines()[1:4]:
                print(f"           {line}")

    print(f"\nSummary: {len(to_keep)} KEEP  |  {len(to_archive)} ARCHIVE  (--days {days})")

    if not to_archive:
        print("\nNothing to archive.")
        return 0

    if not confirm:
        print("\nDry run — pass --confirm to execute archive.")
        return 0

    # Execute archive
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    existing_archive = ARCHIVE.read_text(encoding="utf-8") if ARCHIVE.exists() else ARCHIVE_HEADER

    # Preserve session headers in archive so entries have context
    archive_blocks = []
    for entry, _, _ in to_archive:
        session_line = _session_date_for(entry["body"], text)
        block = (f"{session_line}\n\n" if session_line else "") + entry["body"]
        archive_blocks.append(block)

    ARCHIVE.write_text(
        existing_archive.rstrip() + "\n\n" + "\n\n".join(archive_blocks) + "\n",
        encoding="utf-8",
    )

    keep_bodies = "\n\n".join(
        e["body"] for e, _, _ in sorted(to_keep, key=lambda x: -(x[0]["num"] or 0))
    )
    archived_nums = sorted(e["num"] for e, _, _ in to_archive if e["num"])
    archive_note = ""
    if archived_nums:
        archive_note = (
            f"*Entries {archived_nums[0]}–{archived_nums[-1]} archived to "
            f"docs/archive/DECISIONS_archive.md "
            f"({len(to_archive)} entries older than {days} days, "
            f"{datetime.now().strftime('%Y-%m-%d')})*\n\n"
        )
    DECISIONS.write_text(preamble + archive_note + keep_bodies + "\n", encoding="utf-8")

    print(f"\nArchived {len(to_archive)} entries → {ARCHIVE}")
    print(f"DECISIONS.md now has {len(to_keep)} active entries.")
    print(f"Use --recall N to pull any entry back when needed.")
    return 0


# ── Recall ────────────────────────────────────────────────────────────────────

def run_recall(entry_num: int, confirm: bool) -> int:
    """Pull entry N from archive back into DECISIONS.md."""
    if not ARCHIVE.exists():
        print(f"ERROR: archive not found at {ARCHIVE}", file=sys.stderr)
        return 1
    if not DECISIONS.exists():
        print(f"ERROR: {DECISIONS} not found", file=sys.stderr)
        return 1

    archive_text = ARCHIVE.read_text(encoding="utf-8")
    _, archive_entries = parse_decisions(archive_text)

    target = next((e for e in archive_entries if e["num"] == entry_num), None)
    if not target:
        print(f"ERROR: Entry {entry_num} not found in archive.", file=sys.stderr)
        print("Available entries:", [e["num"] for e in archive_entries if e["num"]])
        return 1

    print(f"\nRecall Entry {entry_num}: {target['title']}")
    print(f"Date: {target['date'] or 'unknown'}")
    print(f"\nEntry body preview:")
    for line in target["body"].splitlines()[:6]:
        print(f"  {line}")
    print(f"  ...")

    if not confirm:
        print(f"\nDry run — pass --confirm to move Entry {entry_num} back to DECISIONS.md.")
        return 0

    # Remove from archive
    # Remove the entry block (and any preceding session header that belongs only to it)
    new_archive = _remove_entry_from_text(archive_text, target)
    ARCHIVE.write_text(new_archive, encoding="utf-8")

    # Insert into DECISIONS.md after preamble, before first session block
    decisions_text = DECISIONS.read_text(encoding="utf-8")
    preamble, _ = parse_decisions(decisions_text)
    rest = decisions_text[len(preamble):]

    # Find the right session header in DECISIONS.md, or create one
    session_line = _find_or_build_session_header(target, decisions_text)
    session_header_match = re.search(
        re.escape(session_line[:40]), decisions_text
    ) if session_line else None

    if session_header_match:
        # Insert entry after the matching session header
        insert_pos = session_header_match.end()
        # Skip to the next blank line after the header
        after_header = decisions_text[insert_pos:]
        blank = re.match(r"\n+", after_header)
        insert_pos += (blank.end() if blank else 0)
        new_decisions = (
            decisions_text[:insert_pos]
            + "\n" + target["body"] + "\n\n"
            + decisions_text[insert_pos:]
        )
    else:
        # Prepend with its session header after the preamble
        new_decisions = preamble + f"{session_line}\n\n{target['body']}\n\n" + rest

    DECISIONS.write_text(new_decisions, encoding="utf-8")

    print(f"\nEntry {entry_num} recalled into DECISIONS.md.")
    print(f"Archive updated: {ARCHIVE}")
    return 0


def _remove_entry_from_text(text: str, entry: dict) -> str:
    """Remove an entry block from the archive text."""
    body = entry["body"]
    idx = text.find(body[:80])
    if idx == -1:
        return text
    # Check if a session header immediately precedes this entry
    pre = text[:idx]
    session_match = re.search(r"(##\s+Session[^\n]+\n+)$", pre)
    start = session_match.start() if session_match else idx
    end = idx + len(body)
    # Consume trailing whitespace
    while end < len(text) and text[end] in "\n ":
        end += 1
    return text[:start] + text[end:]


def _find_or_build_session_header(entry: dict, decisions_text: str) -> str:
    """Return the session header line for this entry, from DECISIONS.md if found."""
    if not entry["date"]:
        return f"## Session — {datetime.now().strftime('%Y-%m-%d')} (recalled)"
    # Search for a session block with matching date
    m = re.search(
        rf"^##\s+Session[^\n]*{re.escape(entry['date'])}", decisions_text, re.MULTILINE
    )
    if m:
        return m.group(0)
    return f"## Session — {entry['date']} (recalled)"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Archive old DECISIONS.md entries or recall them back."
    )
    parser.add_argument("--confirm", action="store_true",
                        help="Execute the operation (default: dry run)")
    parser.add_argument("--days", type=int, default=60,
                        help="Archive entries older than N days (default: 60)")
    parser.add_argument("--min-entry", type=int, default=None,
                        help="Never archive entries at or above this number (safety floor)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show entry body preview in archive table")
    parser.add_argument("--recall", type=int, default=None, metavar="N",
                        help="Recall entry N from archive back into DECISIONS.md")
    args = parser.parse_args()

    if args.recall is not None:
        sys.exit(run_recall(args.recall, args.confirm))
    else:
        sys.exit(run_archive(args.confirm, args.min_entry, args.days, args.verbose))


if __name__ == "__main__":
    main()
