#!/usr/bin/env python3
"""
recall.py — Synthesise outstanding priorities from MEMORY.md + DECISIONS.md.

Outputs a sequence-ordered gist:
  - Done count (collapsed)
  - Open priorities expanded into their build steps with file hints
  - NEXT SESSION pointer
  - New items from recent DECISIONS.md entries not yet in memory
  - Concrete first step (first incomplete step in sequence)

Update PRIORITY_STEPS after any dependency analysis session.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MEMORY_DIR = Path.home() / ".claude/projects/-mnt-c-BACKUP-DEV-TEST/memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
DECISIONS_FILE = ROOT / "docs/DECISIONS.md"

# ── Sequence config ───────────────────────────────────────────────────────────
# Each entry: (step, priority_num, label, file_hint, depends_on_step)
# Update this after a dependency analysis session.
# Mark a step done by prepending ✅ to its label.
PRIORITY_STEPS = [
    # Priority 33 — DETECT-ABU domain
    (1,  33, "DETECT-ABU 6 rules",                     "policies/soc_detection_rules.yaml",          None),
    (2,  33, "MCPAccessLogger rolling windows + export timestamps", "mcp_server/access_logger.py",   1),
    (3,  33, "❼ Jev noul on 6 ABU investigation questions", "chatbot/harness/rule_evaluator.py",     1),
    (4,  33, "Dashboard ABU investigation panel",       "chatbot/api/static/index.html + dashboard.js", 2),
    # → P34 blog: drafted after steps 1–4
    # Priority 34 — Jev Phase 2 (❻ ❽)
    (5,  34, "❻ GT technique applicability noul",       "chatbot/modules/ground_truth_generator.py",  3),
    (6,  34, "❽ CISO posture noul at export",           "chatbot/modules/ta_exporter.py",             5),
    # Priority 35 — Beyond Zero (independent items can run parallel with 5–6)
    (7,  35, "P35-C Opaque reasoning sub-check in DETECT-QC-009", "chatbot/harness/stages.py",       None),
    (8,  35, "P35-B TATB AI Control Maturity sub-dim",  "chatbot/modules/ta_brain_benchmarks.py",    None),
    (9,  35, "P35-A Per-action MCP Jev noul gate",      "mcp_server/server.py",                       3),
    # Freestanding
    (10, 0,  "skill-evolve skill",                      ".claude/skills/skill-evolve/",              None),
]

BLOG_GATES = {
    34: "P34 blog — draft after steps 1–4 live",
    35: "P35 blog — draft after steps 7–9 live",
}

# ── helpers ───────────────────────────────────────────────────────────────────

def read_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def extract_priorities(memory: str) -> list[tuple[int, str, bool]]:
    """Return list of (num, text, done) from the '## Current priorities' section."""
    section = re.search(r"## Current priorities.*?(?=\n##|\Z)", memory, re.S)
    if not section:
        return []
    items = re.findall(r"(\d+)\.\s+(.*)", section.group())
    result = []
    for num, text in items:
        stripped = text.strip()
        done = (
            (stripped.startswith("~~") and stripped.endswith("~~"))
            or stripped.startswith("✅")
            or re.match(r"^1[–-]\d+\.", stripped) is not None
        )
        clean = re.sub(r"~~(.+?)~~", r"\1", stripped).strip()
        result.append((int(num), clean, done))
    return result


def extract_recent_decisions(decisions: str, max_sessions: int = 2) -> list[str]:
    """Pull open/pending items from the last N session blocks in DECISIONS.md."""
    sessions = re.split(r"(?=^## Session)", decisions, flags=re.M)
    open_items = []
    seen = set()
    target_kws = ["blog candidate", "planned", "next steps", "todo", "pending"]
    skip_kws = ["why now", "depends on", "prerequisite", "recursive", "answer arc", "alternatives rejected"]
    for session in sessions[1 : max_sessions + 1]:
        for line in session.splitlines():
            stripped = line.strip()
            if not stripped or len(stripped) < 10:
                continue
            low = stripped.lower()
            if any(kw in low for kw in skip_kws):
                continue
            if any(kw in low for kw in target_kws):
                if not re.match(r"^[-*#]|^\*\*|^Entry", stripped):
                    continue
                clean = re.sub(r"^[-*#]+\s*|\*\*", "", stripped).strip()
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


def priority_is_done(pnum: int, priorities: list[tuple[int, str, bool]]) -> bool:
    for n, _, done in priorities:
        if n == pnum:
            return done
    return False


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    memory = read_file(MEMORY_FILE)
    decisions = read_file(DECISIONS_FILE)

    priorities = extract_priorities(memory)
    decision_items = extract_recent_decisions(decisions, max_sessions=2)

    done = [(n, t) for n, t, d in priorities if d]
    open_pnums = {n for n, _, d in priorities if not d}

    # New items from DECISIONS not yet reflected in memory priorities
    new_items = [item for item in decision_items if not in_priorities(item, priorities)]

    lines = ["## Recall\n"]

    # Done (collapsed)
    if done:
        lines.append(f"**Done ({len(done)}):** " + ", ".join(str(n) for n, _ in done))

    # Open priorities — expanded into build steps, in sequence order
    open_steps = [
        (step, pnum, label, hint, dep)
        for step, pnum, label, hint, dep in PRIORITY_STEPS
        if pnum in open_pnums or pnum == 0  # 0 = freestanding
    ]

    if open_steps:
        lines.append("\n**Build sequence (open):**")
        current_pnum = None
        for step, pnum, label, hint, dep in open_steps:
            done_marker = "✅" if label.startswith("✅") else "⬜"
            # Group header when priority changes
            if pnum != current_pnum:
                p_label = f"Priority {pnum}" if pnum else "Freestanding"
                lines.append(f"\n  [{p_label}]")
                current_pnum = pnum
                # Insert blog gate note if this priority has one
                if pnum in BLOG_GATES and step > 1:
                    # Only show gate at the start of the priority block
                    pass
            dep_note = f"  ← needs step {dep}" if dep else ""
            lines.append(f"  Step {step:2d} {done_marker} {label}{dep_note}")
            lines.append(f"           → {hint}")

        # Blog gates
        gates_shown = set()
        for step, pnum, label, hint, dep in open_steps:
            if pnum in BLOG_GATES and pnum not in gates_shown:
                gates_shown.add(pnum)
        if gates_shown:
            lines.append("")
            for pnum in sorted(gates_shown):
                lines.append(f"  📝 {BLOG_GATES[pnum]}")

    # New from DECISIONS not yet in memory
    if new_items:
        lines.append("\n**From recent DECISIONS (not yet in memory):**")
        for item in new_items[:4]:
            lines.append(f"  • {item}")

    # Concrete next step: first ⬜ step in sequence
    first_open = next(
        ((step, label, hint) for step, pnum, label, hint, dep in open_steps
         if not label.startswith("✅")),
        None
    )
    if first_open:
        s, lbl, hint = first_open
        lines.append(f"\n**Next up:** Step {s} — {lbl}")
        lines.append(f"  → {hint}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
