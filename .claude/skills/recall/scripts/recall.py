#!/usr/bin/env python3
"""
recall.py — print open work from docs/ROADMAP.md plus new/open items from DECISIONS.md.

ROADMAP.md is the single source for "what is next". This script holds no priority
table of its own. Line format in ROADMAP.md:
  - [ID] status | label | file hint | needs: ID,ID | adr: N,N
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ROADMAP_FILE = ROOT / "docs/ROADMAP.md"
DECISIONS_FILE = ROOT / "docs/DECISIONS.md"

ITEM_RE = re.compile(r"^- \[([^\]]+)\]\s+(\w+)\s*\|(.*)$")


def read_file(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def parse_roadmap(text: str) -> list[dict]:
    """Return items in file order: id, status, label, hint, needs, adrs, section."""
    items, section = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        m = ITEM_RE.match(line)
        if not m:
            continue
        fields = [f.strip() for f in m.group(3).split("|")]
        label = fields[0] if fields else ""
        hint = fields[1] if len(fields) > 1 else ""
        needs, adrs = [], []
        for f in fields[2:]:
            if f.startswith("needs:"):
                needs = [x.strip() for x in f[6:].split(",") if x.strip() and x.strip() != "—"]
            elif f.startswith("adr:"):
                adrs = [int(x) for x in re.findall(r"\d+", f)]
        items.append({"id": m.group(1), "status": m.group(2), "label": label,
                      "hint": hint, "needs": needs, "adrs": adrs, "section": section})
    return items


def extract_recent_decisions(decisions: str, max_sessions: int = 2) -> list[str]:
    """Pull open/pending items from the last N session blocks in DECISIONS.md."""
    sessions = re.split(r"(?=^## Session)", decisions, flags=re.M)
    open_items, seen = [], set()
    target_kws = ["blog candidate", "planned", "next steps", "todo", "pending"]
    skip_kws = ["why now", "depends on", "prerequisite", "recursive", "answer arc", "alternatives rejected"]
    for session in sessions[1 : max_sessions + 1]:
        for line in session.splitlines():
            stripped = line.strip()
            if len(stripped) < 10:
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


def extract_open_adrs(decisions: str) -> list[tuple[int, str, str]]:
    """(entry_num, title, status) for entries whose Status says design intent / pending / design constraint."""
    out = []
    for block in re.split(r"(?=^### Entry \d+)", decisions, flags=re.M):
        m = re.match(r"^### Entry (\d+) — (.+)", block)
        if not m:
            continue
        sm = re.search(r"^\*\*Status:\*\*\s*(.+)", block, re.M)
        if sm and any(k in sm.group(1).lower() for k in ("design intent", "pending", "design constraint")):
            out.append((int(m.group(1)), m.group(2).strip(), sm.group(1).strip()))
    return out


def main() -> None:
    items = parse_roadmap(read_file(ROADMAP_FILE))
    decisions = read_file(DECISIONS_FILE)
    lines = ["## Recall\n"]

    if not items:
        lines.append("docs/ROADMAP.md missing or has no items.")
    else:
        open_ids = {i["id"] for i in items}
        lines.append(f"**Open ({len(items)}):** source docs/ROADMAP.md")
        current = None
        for i in items:
            if i["section"] != current:
                current = i["section"]
                lines.append(f"\n  [{current}]")
            mark = "▶" if i["status"] == "doing" else "⬜"
            blocked = [n for n in i["needs"] if n in open_ids]
            dep = f"  ← needs {', '.join(blocked)}" if blocked else ""
            lines.append(f"  {i['id']:<6} {mark} {i['label']}{dep}")
            if i["hint"] and i["hint"] != "—":
                lines.append(f"           → {i['hint']}")

        adr_map: dict[int, list[str]] = {}
        for i in items:
            for n in i["adrs"]:
                adr_map.setdefault(n, []).append(i["id"])
        open_adrs = extract_open_adrs(decisions)
        if open_adrs:
            lines.append("\n**Open ADRs:**")
            for num, title, _ in open_adrs:
                ids = adr_map.get(num)
                tag = f"→ {', '.join(ids)}" if ids else "⚠ no roadmap item yet, needs sequencing"
                lines.append(f"  Entry {num}  {title if len(title) <= 65 else title[:62] + '…'}")
                lines.append(f"           {tag}")

    new_items = [x for x in extract_recent_decisions(decisions)
                 if not any(x.lower()[:30] in i["label"].lower() for i in items)]
    if new_items:
        lines.append("\n**From recent DECISIONS (not on roadmap):**")
        lines.extend(f"  • {x}" for x in new_items[:4])

    ready = next((i for i in items
                  if i["status"] == "doing"), None) or next(
        (i for i in items if not [n for n in i["needs"] if n in {j["id"] for j in items}]), None)
    if ready:
        lines.append(f"\n**Next up:** {ready['id']} — {ready['label']}")
        if ready["hint"] and ready["hint"] != "—":
            lines.append(f"  → {ready['hint']}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
