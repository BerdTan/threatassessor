---
name: docs-health
description: Audits CLAUDE.md, docs/DECISIONS.md, design docs (HARNESS/TATB/TACLAW), and memory files for staleness and accuracy. Use at session start or after a major feature lands. Checks last-updated dates, module paths, API table completeness, implementation status tables, and memory entry validity. Outputs a health table with proposed edits — no auto-writes.
allowed-tools: Bash(git:*) Bash(ls:*) Bash(grep:*) Read
---

# Docs Health

Read-only audit. Output a ✅ / ⚠ / ❌ health table then propose specific line edits for user approval.

## Check 1 — CLAUDE.md

```bash
# Last-updated date vs most recent commit
grep "Last Updated" "$(git rev-parse --show-toplevel)/CLAUDE.md
git -C "$(git rev-parse --show-toplevel)" log -1 --format="%ci %s"

# Module paths — do declared paths exist?
grep -E "chatbot/modules/[a-z_]+\.py" "$(git rev-parse --show-toplevel)/CLAUDE.md \
  | grep -oE "chatbot/modules/[a-z_/]+\.py" \
  | while read p; do
      [ -f "$(git rev-parse --show-toplevel)/$p" ] && echo "✅ $p" || echo "❌ $p"
    done

# API routes — do declared routes exist?
grep -oE "chatbot/api/[a-z_/]+\.py" "$(git rev-parse --show-toplevel)/CLAUDE.md \
  | while read p; do
      [ -f "$(git rev-parse --show-toplevel)/$p" ] && echo "✅ $p" || echo "❌ $p"
    done

# Flag stale confidence/version claims
grep -n "99\.5%\|93-96%\|v1\.[0-9]" "$(git rev-parse --show-toplevel)/CLAUDE.md
```

## Check 2 — docs/DECISIONS.md

```bash
# Date of last decision entry vs last 3 commits
grep -E "^## [0-9]{4}-[0-9]{2}-[0-9]{2}" $(git rev-parse --show-toplevel)/docs/DECISIONS.md | tail -3
git -C "$(git rev-parse --show-toplevel)" log --oneline -5
```

Flag if the last decision entry is >7 days older than the most recent commit.

## Check 3 — Memory files

```bash
# List all memory files
cat \~/.claude/projects/<project>/memory/MEMORY.md

# For each linked .md file: read it and check any path it references exists
ls \~/.claude/projects/<project>/memory/
```

Read each memory file. For any line referencing a module path, commit hash, or script path — verify it still exists. Flag entries with broken references or advice that contradicts the current codebase.

## Check 5 — Design docs (HARNESS / TATB / TACLAW)

The three canonical design docs live at `docs/HARNESS.md`, `docs/TATB.md`, `docs/TACLAW.md`. Each must stay in sync with the implementation.

```bash
ROOT=$(git rev-parse --show-toplevel)

# 1. Status line freshness — does each doc's Status/Last Updated reflect recent commits?
grep -n "^**Status:\|^**Last Updated:\|^**Date:" \
  "$ROOT/docs/HARNESS.md" "$ROOT/docs/TATB.md" "$ROOT/docs/TACLAW.md"
git -C "$ROOT" log -1 --format="%ci %s"

# 2. File path validity — do referenced .py paths still exist?
grep -hE "chatbot/[a-z_/]+\.py|mcp_server/[a-z_/]+\.py|taclaw_cli/[a-z_/]+\.py|policies/[a-z_]+\.yaml" \
  "$ROOT/docs/HARNESS.md" "$ROOT/docs/TATB.md" "$ROOT/docs/TACLAW.md" \
  | grep -oE "[a-z_/]+\.(py|yaml)" | sort -u | while read p; do
      [ -f "$ROOT/$p" ] && echo "✅ $p" || echo "❌ $p"
    done

# 3. Engine Item completeness — are items 11-16 still ⬜ Planned, or have some shipped?
grep -n "Engine Item\|⬜ Planned\|✅ Shipped" "$ROOT/docs/HARNESS.md" | tail -20

# 4. README links — do all docs/README.md links resolve?
grep -oE '\[.*?\]\(([^)]+\.md)\)' "$ROOT/docs/README.md" \
  | grep -oE '\(([^)]+)\)' | tr -d '()' | while read p; do
      target="$ROOT/docs/$p"
      [ -f "$target" ] && echo "✅ $p" || echo "❌ $p (broken link)"
    done

# 5. TACLAW status — are Group statuses accurate?
grep -n "^### Group\|Status:" "$ROOT/docs/TACLAW.md" | head -20
```

**Flag when:**
- Status line date is >14 days behind the most recent commit
- Any `❌` path (referenced file no longer exists)
- Engine Items marked `⬜ Planned` in HARNESS.md but `✅ Shipped` in DECISIONS.md (or vice versa)
- Any docs/README.md link points to a file that does not exist

**Propose:**
- Updated Status/date line for each stale doc
- Corrected path for each broken reference
- Engine Item status flip for anything shipped but still marked Planned

## Check 4 — Current Priorities

Read `~/.claude/projects/<project>/memory/MEMORY.md` and extract the **Current priorities** section.

Print a clean numbered list, prefixed with status:
- ✅ for completed items (struck-through in memory)
- 🔄 for in-progress (started this session or explicitly flagged)
- ⬜ for not started

After the list, add a one-line **Next up:** pointing at the first ⬜ item with a concrete first step.

If any priority is now unblocked by work done this session, call that out explicitly.

## Output Format

```
## Docs Health

| File | Status | Issue | Proposed Fix |
|------|--------|-------|-------------|
| CLAUDE.md | ⚠ | "Last Updated: 2026-05-24" | Update to today's date |
| DECISIONS.md | ✅ | Last entry matches HEAD | — |
| HARNESS.md | ⚠ | Status date 14d behind HEAD | Update status line to today |
| TATB.md | ✅ | All paths valid | — |
| TACLAW.md | ⚠ | Group 1 marked planned; shipped in d1bf90b | Update to ✅ Shipped |
| docs/README.md | ❌ | Broken link: old_name.md | Update to HARNESS.md |
| memory/project_roadmap.md | ✅ | All paths valid | — |

## Priorities

1. ✅ Corpus rerun
2. ✅ Brain re-ingest
3. ⬜ Brain Infer UI panel — calls /api/v1/brain/query, new Brain tab sub-tab
4. ⬜ Fill partial bench runs — nemotron_super + glm
...

Next up: Brain Infer UI panel — start with the sub-tab scaffold in dashboard.js
```

Then ask: "Apply any of these edits?"
