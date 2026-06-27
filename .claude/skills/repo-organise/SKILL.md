---
name: repo-organise
description: Audits and tidies non-code directories (docs, tests, scripts, report). Use when docs feel cluttered, stale reports pile up, or before a release. Read-only audit by default — proposes moves/deletions for user approval, never auto-executes.
allowed-tools: Bash(find:*) Bash(stat:*) Bash(ls:*) Bash(grep:*) Read
---

# Repo Organise

Read-only audit of the four maintenance directories. Output a findings table; propose actions; wait for user approval before touching anything.

## Check 1 — /docs

```bash
# Files outside archive/ not modified in last 30 days
find "$(git rev-parse --show-toplevel)/docs -maxdepth 1 -name "*.md" -mmin +43200
find "$(git rev-parse --show-toplevel)/docs -mindepth 2 -maxdepth 2 -name "*.md" \
     -not -path "*/archive/*" -mmin +43200

# Verify docs/README.md index covers all subdirectories
ls "$(git rev-parse --show-toplevel)/docs/
grep -o '\[.*\]' $(git rev-parse --show-toplevel)/docs/README.md | head -40
```

Propose: move stale files to `docs/archive/`. Flag any subdirectory not listed in `docs/README.md`.

## Check 2 — /tests vs /report coverage

```bash
# Architecture names in tests
ls "$(git rev-parse --show-toplevel)/tests/data/architectures/ | sed 's/\.mmd$//'

# Report directories that exist
ls "$(git rev-parse --show-toplevel)/report/
```

Diff the two lists. Known gap: architectures 12–20 have no report. Flag any new gaps.

## Check 3 — /scripts

```bash
# Hard-coded absolute paths (fragile if repo moves)
grep -r "BACKUP/DEV-TEST" "$(git rev-parse --show-toplevel)/scripts/ --include="*.sh" --include="*.py" -l

# Scripts with no header comment (first non-blank line not a comment)
for f in $(find "$(git rev-parse --show-toplevel)/scripts -name "*.sh" -o -name "*.py"); do
  head -3 "$f" | grep -qE "^#|^\"\"\"" || echo "No header: $f"
done
```

Propose: replace absolute paths with `$(git rev-parse --show-toplevel)` or `$(dirname "$0")/..`.

## Check 4 — /report pruning

```bash
# Report directories older than 14 days
find "$(git rev-parse --show-toplevel)/report -maxdepth 1 -mindepth 1 -type d \
     -mtime +14 -exec ls -ld {} \;
```

Output a prune candidate list. Never delete — present to user for `rm -rf` approval.

## Output Format

Present findings as a table:

| Area | Finding | Proposed Action |
|------|---------|-----------------|
| docs | `file.md` last modified 45 days ago | Move to `docs/archive/` |
| tests | arch `13_iot` has no report | Note only — no action |
| scripts | `scripts/generation/batch.sh` hard-codes path | Update to relative path |
| report | `random_low_TB_seed42/` is 22 days old | Candidate for deletion |

Then ask: "Proceed with any of these? Which ones?"
