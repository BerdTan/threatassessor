# decisions-archive — DECISIONS.md maintenance

Time-based archiving and recall for DECISIONS.md. Entries older than `--days`
(default 60) with no open signals are moved to `docs/archive/DECISIONS_archive.md`.
Archived entries stay in the same `### Entry NNN` format and can be recalled back
at any time — useful when CI, skills, or GitHub readers need to see an older decision.

Dry-run by default — nothing moves without `--confirm`.

## When to run

- When DECISIONS.md exceeds ~100 entries
- Before a session where full DECISIONS load would be unnecessary overhead
- When an archived entry is needed back (skills, CI, external references)
- Periodically as part of `/session-cleanup`

## Run — Archive

```bash
# Dry run — classify and show table, nothing moves
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/decisions-archive/scripts/decisions-archive.py

# Keep last 90 days instead of default 60
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/decisions-archive/scripts/decisions-archive.py --days 90

# Safety floor — never archive entries at or above N
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/decisions-archive/scripts/decisions-archive.py --min-entry 195

# Execute archive after reviewing dry-run output
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/decisions-archive/scripts/decisions-archive.py --days 60 --min-entry 195 --confirm
```

## Run — Recall

Pull an archived entry back into DECISIONS.md when needed by skills, CI, or external readers.

```bash
# Dry run — preview what would be recalled
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/decisions-archive/scripts/decisions-archive.py --recall 42

# Execute recall
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/decisions-archive/scripts/decisions-archive.py --recall 42 --confirm
```

Recall inserts the entry into DECISIONS.md at the top (after the header) under its
original session header if that session exists in DECISIONS.md, otherwise creates it.
The entry is removed from the archive. It can be re-archived later by the normal age-based flow.

**Why recall matters:** Many skills, CI scripts, and GitHub references read DECISIONS.md
directly. Once an entry is archived it is invisible to those readers. Recall lets a specific
entry surface again — for example when a follow-up decision needs to reference it, when a
skill's logic branches on it, or when an external team is copying the pattern.

## Classification rules

An entry is **ARCHIVE** only when BOTH of the following are true:
- Older than `--days` (determined by the `## Session NN — YYYY-MM-DD` header preceding it)
- No open signal matches

An entry is **KEEP** if either condition fails. KEEP is the safe default.

## Hard-coded KEEP signals (override age)

These patterns always force KEEP regardless of how old the entry is:
- `pending`, `planned`, `deferred`, `not yet`, `follow-up`, `open`, `TODO`
- `⬅`, `⬜`
- `Engine Item 17`, `Engine Item 18`, `Jev`, `TAgym`
- `DETECT-QC-009`, `DETECT-MCP-005`
- `not started`, `not implemented`, `promote`

Update `KEEP_PATTERNS` in the script when new planned items emerge.

## Output

```
Entry    Status   Reason                                    Title
------------------------------------------------------------------------------------------------------------
  199    KEEP     open signal: 'Jev'                        Engine Item 17: JevTATBLabeller...
  198    KEEP     open signal: 'Jev'                        Jev (typesafe.ai) integration...
  197    KEEP     recent (2026-09-25, 1d old)               Tier 2 security hardening
  ...
  045    ARCHIVE  older than 60 days, no open signals       Engine Item 2 — critic isolation
  ...

Summary: 15 KEEP  |  180 ARCHIVE  (--days 60)

Dry run — pass --confirm to execute archive.
```

## Safety

- Always review dry-run output before `--confirm`
- Use `--days N` to tune the cutoff (default 60, try 90 if you want more context)
- Use `--min-entry N` as an additional hard floor on entry number
- Archived entries go to `docs/archive/DECISIONS_archive.md` — nothing is deleted
- Archive preserves session headers so entries keep their context
- `docs/archive/` is created automatically
- DECISIONS.md gets a pointer line: `*Entries N–M archived to docs/archive/DECISIONS_archive.md*`
- `git diff docs/DECISIONS.md` after `--confirm` shows exactly what moved

## Integration with /session-cleanup

Add to session-cleanup rotation: run dry-run, report entry count.
Flag when DECISIONS.md exceeds 150 entries so the user can decide whether to archive.

## Blog note

Jev + TA integration (TATB labeller, smart router, PolicyBroker, governance pre-flight,
TAclaw) is a candidate for Part 31 — five use cases across three question types (noul /
choice / score), each mapping to a different TA pipeline layer.
