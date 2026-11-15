---
name: session-cleanup
description: Master housekeeping skill. Runs docs-health + repo-organise in one pass — audits CLAUDE.md accuracy, DECISIONS.md freshness, memory staleness, orphaned files, stale reports, and bench_results pruning. Outputs a unified findings table; proposes and applies only what the user approves.
allowed-tools: Bash Read Edit Write
---

# Session Cleanup

Combined audit: docs health + repo organisation. Read-only pass first; apply only after user approval.

Run when: post-session, before a push, or when things feel cluttered.

---

## Phase 1 — Docs Health

### 1a — CLAUDE.md accuracy

Run these checks in parallel:

```bash
ROOT=$(git rev-parse --show-toplevel)

# Last-updated vs HEAD
grep "Last Updated" "$ROOT/CLAUDE.md"
git log -1 --format="%ci %s"

# Broken module paths
grep -oE "(chatbot|agentic|mcp_server|chatbot/harness|chatbot/api)/[a-z_/]+\.py" "$ROOT/CLAUDE.md" | sort -u | while read p; do
  [ -f "$ROOT/$p" ] && echo "✅ $p" || echo "❌ $p"
done

# Stale counts — extract declared numbers and compare to live counts
grep -oE "[0-9]+ rules|[0-9]+ tests|[0-9]+ tools|[0-9]+ scenarios" "$ROOT/CLAUDE.md" | sort -u

# Live counts for comparison
grep -c "id: DETECT" "$ROOT/policies/soc_detection_rules.yaml"           # rules
grep -c "@mcp.tool()" "$ROOT/mcp_server/server.py"                        # MCP tools
```

For any `❌` path: find where the file actually lives with `find . -name "<filename>" -not -path "*/.*"` and propose the corrected path.

For count mismatches: compare declared vs live and flag any that differ.

### 1b — DECISIONS.md freshness

```bash
ROOT=$(git rev-parse --show-toplevel)
# Last session header vs HEAD commit date
grep -m1 "^## Session" "$ROOT/docs/DECISIONS.md"
git log -1 --format="%ci"
```

Flag if last entry is >7 days older than HEAD.

### 1c — Memory files

```bash
MDIR=~/.claude/projects/-mnt-c-BACKUP-DEV-TEST/memory
# Orphaned files: exist on disk but not linked in MEMORY.md
comm -23 \
  <(ls "$MDIR"/*.md | xargs -n1 basename | sort) \
  <(grep -oE '[a-z_]+\.md' "$MDIR/MEMORY.md" | sort -u)

# Broken path references in active memory files (those linked in MEMORY.md)
ROOT=$(git rev-parse --show-toplevel)
grep -oE '[a-z_/]+\.py' "$MDIR/project_ta_brain.md" "$MDIR/project_engine_improvements.md" 2>/dev/null | \
  grep -oE '[^:]+\.py$' | sort -u | while read p; do
    [ -f "$ROOT/$p" ] && echo "✅ $p" || echo "❌ $p"
  done
```

---

## Phase 1d — Skill supply-chain integrity

Run `/check-skills` inline — it performs git integrity, URL audit, `allowed-tools` gaps, script supply-chain patterns, and phishing phrase detection across the full `.claude/skills/` corpus. Findings are added to the unified table in Phase 3.

If `/check-skills` surfaces Critical or High findings, resolve them before proceeding with the rest of the cleanup.

---

## Phase 2 — Repo Organisation

### 2a — /docs staleness

```bash
ROOT=$(git rev-parse --show-toplevel)
# Top-level docs files not modified in 60+ days
find "$ROOT/docs" -maxdepth 1 -name "*.md" -mmin +86400 -exec ls -lh {} \;
# Subdirs not in docs/README.md
ls "$ROOT/docs/"
grep -oE '\[.*?\]\(.*?\)' "$ROOT/docs/README.md" 2>/dev/null | head -30
```

### 2b — /bench_results pruning

```bash
ROOT=$(git rev-parse --show-toplevel)
for d in "$ROOT/bench_results"/*/; do
  summary="$d/bench_summary.json"
  [ -f "$summary" ] || { echo "$(basename $d): no summary"; continue; }
  python3 -c "
import json, os, time
s = json.load(open('$summary'))
age = (time.time() - os.path.getmtime('$summary')) / 86400
models = ','.join(s.get('models', ['?']))
archs  = ','.join(s.get('archs', ['?']))
results = s.get('results', {})
errors = sum(1 for ar in results.values() for r in ar.values() if 'error' in r)
total  = sum(len(ar) for ar in results.values())
print(f'{os.path.basename(\"$d\"):<28} models={models:<25} archs={archs:<20} errors={errors}/{total} age={age:.0f}d')
"
done
```

Classification (propose, never auto-delete):
- All errors → **delete**
- `current` model >1 day old, superseded → **delete**
- Named model, partial errors → **archive**
- Named model, complete, superseded by newer same-model run → **archive**
- Named model, complete, most recent → **keep**

### 2c — /report pruning

```bash
ROOT=$(git rev-parse --show-toplevel)
# Synthetic/temp report dirs older than 30 days (non-canonical archs)
find "$ROOT/report" -maxdepth 1 -mindepth 1 -type d -mtime +30 \
  | grep -E "test_|tmp_|scratch_" | xargs -I{} ls -ld {}
```

### 2d — Orphaned memory session files

```bash
MDIR=~/.claude/projects/-mnt-c-BACKUP-DEV-TEST/memory
ls "$MDIR"/project_session*.md 2>/dev/null | wc -l
ls "$MDIR"/project_session*.md 2>/dev/null | head -5
```

These pre-date the MEMORY.md index system. Their content has been absorbed into DECISIONS.md. Propose batch delete unless user wants to keep specific ones.

---

## Phase 3 — Combined Findings Table

Output a single unified table:

| Area | Item | Status | Proposed Action |
|---|---|---|---|
| CLAUDE.md | Last Updated stale | ⚠ | Update date |
| CLAUDE.md | broken path `chatbot/modules/X.py` | ❌ | Fix to correct path |
| CLAUDE.md | count mismatch (rules/tools/tests) | ⚠ | Update to live count |
| DECISIONS.md | last entry >7d behind HEAD | ⚠ | Add session entry |
| memory | `project_session*.md` (N files) not indexed | ⚠ | Batch delete |
| memory | broken path reference in active file | ❌ | Remove or fix line |
| bench_results | run X — all errors | ❌ | Delete |
| bench_results | run Y — superseded | ⚠ | Archive |
| docs | file Z — 60d stale, not in README | ⚠ | Move to archive/ |

Then ask: **"Apply which items? (list numbers or 'all')"**

Apply only what the user approves. For deletions: confirm once more with the exact `rm` command before executing.

---

## Notes

- Never auto-apply. Always show the table first.
- DECISIONS.md: if the last session entry is current, mark ✅ and skip.
- Memory session files: present as a batch (count + first 5 names). User approves the whole batch or picks specific ones to keep.
- CLAUDE.md `Last Updated` is always updated when any other CLAUDE.md fix is applied (no point fixing content but leaving a stale date).
- After applying fixes, commit with message: `chore(cleanup): session-cleanup — <brief summary of what changed>` and co-author `Co-Buddy`.
