#!/usr/bin/env python3
"""
recall.py — Synthesise outstanding priorities from MEMORY.md + DECISIONS.md.

Outputs a concise ranked gist:
  - Ordered priority list with status markers
  - NEXT SESSION pointer
  - New items from recent DECISIONS.md entries not yet in memory
  - Concrete first step
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MEMORY_DIR = Path.home() / ".claude/projects/-mnt-c-BACKUP-DEV-TEST/memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
DECISIONS_FILE = ROOT / "docs/DECISIONS.md"

# ── helpers ──────────────────────────────────────────────────────────────────

def read_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def extract_priorities(memory: str) -> list[tuple[int, str, bool]]:
    """Return list of (num, text, done) from the '## Current priorities' section."""
    section = re.search(
        r"## Current priorities.*?(?=\n##|\Z)", memory, re.S
    )
    if not section:
        return []
    items = re.findall(r"(\d+)\.\s+(.*)", section.group())
    result = []
    for num, text in items:
        stripped = text.strip()
        # Done: strikethrough markup OR line starts with ✅
        done = (
            (stripped.startswith("~~") and stripped.endswith("~~"))
            or stripped.startswith("✅")
            or re.match(r"^1[–-]\d+\.", stripped) is not None  # merged done-summary like "1–13. ✅ Done"
        )
        clean = re.sub(r"~~(.+?)~~", r"\1", stripped).strip()
        result.append((int(num), clean, done))
    return result


def extract_next_session(memory: str) -> str:
    """Extract the NEXT SESSION topic from the section heading or first meaningful line."""
    # Try to grab the text after 'NEXT SESSION:' on the heading line itself
    m = re.search(r"##\s*.*?NEXT SESSION[:\s–-]+(.+)", memory)
    if m:
        return m.group(1).strip()
    # Fallback: first non-history bullet inside the section
    m = re.search(r"##\s*.*?NEXT SESSION.*?\n(.*?)(?=\n##|\Z)", memory, re.S)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        stripped = line.strip("- •").strip()
        if stripped and not re.match(r"^Session\s+\d", stripped):
            return stripped
    return ""


def extract_recent_decisions(decisions: str, max_sessions: int = 2) -> list[str]:
    """Pull open/pending items from the last N session blocks in DECISIONS.md."""
    sessions = re.split(r"(?=^## Session)", decisions, flags=re.M)
    open_items = []
    seen = set()
    target_kws = ["engine item", "p28", "p29", "p30", "todo", "pending", "blog candidate"]
    skip_kws = ["why now", "blog note", "depends on", "prerequisite", "recursive", "answer arc"]
    for session in sessions[1 : max_sessions + 1]:
        for line in session.splitlines():
            stripped = line.strip()
            if not stripped or len(stripped) < 10:
                continue
            low = stripped.lower()
            if any(kw in low for kw in skip_kws):
                continue
            if any(kw in low for kw in target_kws):
                # Only take header-like lines (bold, bullet, or starts with Engine/Entry)
                if not re.match(r"^[-*#]|^\*\*|^Engine|^Entry", stripped):
                    continue
                clean = re.sub(r"^[-*#]+\s*|\*\*", "", stripped).strip()
                # Truncate long lines
                if len(clean) > 100:
                    clean = clean[:97] + "..."
                key = clean.lower()[:40]
                if clean and key not in seen:
                    seen.add(key)
                    open_items.append(clean)
    return open_items


def in_priorities(text: str, priorities: list[tuple[int, str, bool]]) -> bool:
    low = text.lower()
    for _, p_text, _ in priorities:
        if low[:30] in p_text.lower() or p_text.lower()[:30] in low:
            return True
    return False


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    memory = read_file(MEMORY_FILE)
    decisions = read_file(DECISIONS_FILE)

    priorities = extract_priorities(memory)
    next_session = extract_next_session(memory)
    decision_items = extract_recent_decisions(decisions, max_sessions=2)

    # Partition priorities
    done = [(n, t) for n, t, d in priorities if d]
    open_p = [(n, t) for n, t, d in priorities if not d]

    # New items from DECISIONS not yet reflected in memory priorities
    new_items = [
        item for item in decision_items
        if not in_priorities(item, priorities)
    ]

    lines = ["## Recall\n"]

    # Done (collapsed)
    if done:
        lines.append(f"**Done ({len(done)}):** " + ", ".join(str(n) for n, _ in done))

    # Open priorities
    if open_p:
        lines.append("\n**Open priorities:**")
        for n, text in open_p:
            lines.append(f"  {n}. ⬜ {text}")
    else:
        lines.append("\n**Open priorities:** none")

    # New from DECISIONS not yet in memory
    if new_items:
        lines.append("\n**From recent DECISIONS (not yet in memory):**")
        for item in new_items[:5]:
            lines.append(f"  • {item}")

    # NEXT SESSION pointer
    if next_session:
        lines.append(f"\n**Next session pointer:** {next_session}")

    # Concrete next step: first open priority
    if open_p:
        _, first = open_p[0]
        lines.append(f"\n**Next up:** {first}")

        # Heuristic: map known Engine Items to a concrete first action
        first_low = first.lower()
        if "engine item 6" in first_low:
            lines.append("  → Check `chatbot/harness/stages.py` — critic subprocess isolation; JSONL write gate")
        elif "engine item 7" in first_low:
            lines.append("  → `chatbot/adapters/` — adapter fidelity score; corpus drift signal")
        elif "engine item 8" in first_low:
            lines.append("  → Langfuse span metadata tags; run bench with `--langfuse` flag")
        elif "engine item 9" in first_low:
            lines.append("  → Pre-flight authority layer — trust-level per source, input screener")
        elif "engine item 10" in first_low:
            lines.append("  → Propagation/taint layer — per-node provenance in graph")
        elif "blog" in first_low or "p28" in first_low:
            lines.append("  → Run `/gen-blog` with `--since 2026-09-13`")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
