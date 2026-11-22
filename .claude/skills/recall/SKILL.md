---
name: recall
description: Cross-reference MEMORY.md priorities + recent DECISIONS.md entries and print a concise ranked gist of what's outstanding, what's new, and the concrete next step. Use at session start or when asking "what's next".
allowed-tools: Bash Read
---

# Recall

Synthesise outstanding work from `docs/ROADMAP.md` (single source of open items) and recent DECISIONS.md entries. Output a single clean gist — no preamble.

## Run

```bash
cd "$(git rev-parse --show-toplevel)"
python3 .claude/skills/recall/scripts/recall.py
```

## Output format

```
## Recall

**Done (N):** 1, 2, 3, ...

**Build sequence (open):**

  [Priority 33]
  Step  1 ⬜ DETECT-ABU 6 rules
           → policies/soc_detection_rules.yaml
  Step  2 ⬜ MCPAccessLogger rolling windows + export timestamps  ← needs step 1
           → mcp_server/access_logger.py
  ...

  📝 P34 blog — draft after steps 1–4 live

**From recent DECISIONS (not yet in memory):**
  • blog candidate: ...

**Next up:** Step 1 — DETECT-ABU 6 rules
  → policies/soc_detection_rules.yaml
```

## Rules

- Done items are collapsed to a count + number list — do not expand them
- Open priorities are expanded into their build sub-steps in dependency order
- Each step shows its file hint and which prior step it depends on
- Blog gates are shown inline after the last step that enables them
- New DECISIONS items shown only when not already reflected in priorities
- Next up = first incomplete step in the sequence + file hint
- If priorities list is empty, print only DECISIONS items
- No commentary after the block — the gist is the whole output
- **After a dependency analysis session:** update `PRIORITY_STEPS` in `recall.py` to reflect the new sequence; mark completed steps with a ✅ prefix on their label

## Where the list lives

Open work is `docs/ROADMAP.md` only (`- [ID] status | label | hint | needs | adr`). recall.py holds no priority table. When an item is done, delete its roadmap line. Open ADRs from DECISIONS.md are cross-referenced through each item's `adr:` field; an ADR with no roadmap item is flagged as needing sequencing.

## When to use

- `/recall` at session start instead of reading full MEMORY.md manually
- After `/compact` to reorient before continuing
- When the user asks "what's next" or "where were we"

## Relationship to /priorities

`/priorities` reads MEMORY.md, which no longer keeps a priority list; prefer `/recall`.
`/recall` reads the roadmap, cross-references DECISIONS.md, and gives a concrete first step. Use `/recall` when resuming after a break or context compaction; use `/priorities` for a quick status check mid-session.
