---
name: recall
description: Cross-reference MEMORY.md priorities + recent DECISIONS.md entries and print a concise ranked gist of what's outstanding, what's new, and the concrete next step. Use at session start or when asking "what's next".
allowed-tools: Bash Read
---

# Recall

Synthesise outstanding work across two sources: the MEMORY.md priority list and recent DECISIONS.md session entries. Output a single clean gist — no preamble.

## Run

```bash
cd "$(git rev-parse --show-toplevel)"
python3 .claude/skills/recall/scripts/recall.py
```

## Output format

```
## Recall

**Done (N):** 1, 2, 3, ...

**Open priorities:**
  4. ⬜ Engine Item 6 — ...
  5. ⬜ Engine Item 7 — ...

**From recent DECISIONS (not yet in memory):**
  • P28 blog candidate: ...

**Next session pointer:** Engine Items 6–8 ...

**Next up:** Engine Item 6 — critic subprocess isolation
  → Check chatbot/harness/stages.py — ...
```

## Rules

- Done items are collapsed to a count + number list — do not expand them
- Open items keep enough context to act on (Engine Item label + short description)
- New DECISIONS items shown only when not already reflected in priorities
- Next up = first open item + one concrete first action (file, command, or endpoint)
- If priorities list is empty, print only DECISIONS items + NEXT SESSION pointer
- No commentary after the block — the gist is the whole output

## When to use

- `/recall` at session start instead of reading full MEMORY.md manually
- After `/compact` to reorient before continuing
- When the user asks "what's next" or "where were we"

## Relationship to /priorities

`/priorities` reads only MEMORY.md and prints the full numbered list.
`/recall` cross-references DECISIONS.md, surfaces newly logged items not yet in memory, and gives a concrete first step. Use `/recall` when resuming after a break or context compaction; use `/priorities` for a quick status check mid-session.
