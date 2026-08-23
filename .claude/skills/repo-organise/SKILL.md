---
name: repo-organise
description: Audits and tidies non-code directories (docs, tests, scripts, report, bench_results). Use when docs feel cluttered, stale reports pile up, or before a release. Read-only audit by default — proposes moves/deletions for user approval, never auto-executes.
allowed-tools: Bash(find:*) Bash(stat:*) Bash(ls:*) Bash(grep:*) Read
---

# Repo Organise

Read-only audit of maintenance directories. Output a findings table; propose actions; wait for user approval before touching anything.

## Check 1 — /docs

```bash
# Files outside archive/ not modified in last 30 days
find "$(git rev-parse --show-toplevel)/docs" -maxdepth 1 -name "*.md" -mmin +43200
find "$(git rev-parse --show-toplevel)/docs" -mindepth 2 -maxdepth 2 -name "*.md" \
     -not -path "*/archive/*" -mmin +43200

# Verify docs/README.md index covers all subdirectories
ls "$(git rev-parse --show-toplevel)/docs/"
grep -o '\[.*\]' "$(git rev-parse --show-toplevel)/docs/README.md" | head -40
```

Propose: move stale files to `docs/archive/`. Flag any subdirectory not listed in `docs/README.md`.

## Check 2 — /tests vs /report coverage

```bash
ls "$(git rev-parse --show-toplevel)/tests/data/architectures/" | sed 's/\.mmd$//'
ls "$(git rev-parse --show-toplevel)/report/"
```

Diff the two lists. Known gap: architectures 12–20 have no report. Flag any new gaps.

## Check 3 — /scripts

```bash
# Hard-coded absolute paths (fragile if repo moves)
grep -r "BACKUP/DEV-TEST" "$(git rev-parse --show-toplevel)/scripts/" --include="*.sh" --include="*.py" -l

# Scripts with no header comment
for f in $(find "$(git rev-parse --show-toplevel)/scripts" -name "*.sh" -o -name "*.py"); do
  head -3 "$f" | grep -qE "^#|^\"\"\"" || echo "No header: $f"
done
```

Propose: replace absolute paths with `$(git rev-parse --show-toplevel)` or `$(dirname "$0")/..`.

## Check 4 — /report pruning

```bash
# Report directories older than 14 days
find "$(git rev-parse --show-toplevel)/report" -maxdepth 1 -mindepth 1 -type d \
     -mtime +14 -exec ls -ld {} \;
```

Output a prune candidate list. Never delete — present to user for `rm -rf` approval.

## Check 5 — /bench_results pruning

```bash
ROOT="$(git rev-parse --show-toplevel)"
# List all runs with their model, arch, age, and whether they errored
for d in "$ROOT/bench_results"/[0-9]*/; do
  summary="$d/bench_summary.json"
  [ -f "$summary" ] || continue
  python3 -c "
import json, os, time
s = json.load(open('$summary'))
age_days = (time.time() - os.path.getmtime('$summary')) / 86400
models = ','.join(s.get('models', []))
archs  = ','.join(s.get('archs', []))
results = s.get('results', {})
errors  = sum(1 for ar in results.values() for r in ar.values() if 'error' in r)
total   = sum(len(ar) for ar in results.values())
print(f'{os.path.basename(\"$d\"):<22} models={models:<30} archs={archs} errors={errors}/{total} age={age_days:.0f}d')
"
done
ls "$ROOT/bench_results/_archive/" 2>/dev/null && echo "(archive contents above)"
```

Classification rules — propose action for each run:
- **All errors** → delete (no usable data)
- **`current` model, >1 day old, superseded by a named-model run** → delete (development iteration)
- **`current` model, still the only run for its arch** → keep or archive
- **Named model (hetzner/gemini_flash/etc), any errors** → archive (partial data, may be reference)
- **Named model, all complete, superseded by a newer run of same models** → archive
- **Named model, all complete, most recent** → keep
- **`_archive/` contents** → list only; propose delete if >30 days old and superseded

Always show a proposed action table before touching anything.

## Output Format

Present findings as a table:

| Area | Item | Status | Proposed Action |
|------|------|--------|-----------------|
| docs | `file.md` last modified 45d | stale | Move to `docs/archive/` |
| tests | arch `13_iot` has no report | gap | Note only |
| scripts | `batch.sh` hard-codes path | fragile | Update to relative path |
| report | `random_low_TB_seed42/` 22d old | stale | Candidate for deletion |
| bench_results | `20260823_104948` current+errors | debug run | Delete |
| bench_results | `20260823_120925` hetzner partial | historical | Archive |
| bench_results | `20260823_152847` gemini complete | reference | Keep |

Then ask: "Proceed with any of these? Which ones?"
