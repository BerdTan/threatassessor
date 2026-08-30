---
name: priorities
description: Instantly print the current project priorities from memory with ✅/🔄/⬜ status and a Next up line. No checks, no file scanning — just the priorities. Use at any time to answer "what's next".
allowed-tools: Read
---

# Priorities

Read `~/.claude/projects/-mnt-c-BACKUP-DEV-TEST/memory/MEMORY.md` and extract the **Current priorities** section.

Print exactly this format — nothing else, no preamble:

```
## Priorities

1. ✅ ...
2. ✅ ...
3. ⬜ ...
...

Next up: <first ⬜ item> — <one concrete first step>

Unblocked this session: <any item newly unblocked, or omit line if none>
```

Rules:
- ✅ = struck-through in memory (~~text~~)
- 🔄 = explicitly flagged in-progress this session
- ⬜ = everything else
- Keep each line to the item name + a short parenthetical if useful; strip long detail
- **Next up** names the first ⬜ with a concrete first action (file, endpoint, or command)
- No headers before the list, no trailing commentary
