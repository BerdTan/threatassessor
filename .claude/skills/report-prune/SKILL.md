---
name: report-prune
description: Identify and delete redundant report subfolders (numbered variant runs, synthetic training reports) and flag stale .claude/graphs/*.mmd files. Run periodically after bench loops or gym iterations.
allowed-tools: Bash
---

# report-prune

Keeps `report/` lean after bench loops, gym iterations, and synthetic brain training generate piles of repeated pipeline runs.

## Run

```bash
# Dry-run — list candidates, nothing deleted
cd "$(git rev-parse --show-toplevel)" && python3 .claude/skills/report-prune/scripts/report_prune.py

# Delete prunable folders
cd "$(git rev-parse --show-toplevel)" && python3 .claude/skills/report-prune/scripts/report_prune.py --clean

# Only check graph staleness (skip report scan)
cd "$(git rev-parse --show-toplevel)" && python3 .claude/skills/report-prune/scripts/report_prune.py --graphs
```

## What it detects

**Prunable folders:**

| Category | Pattern | Why safe to delete |
|---|---|---|
| Numbered variant runs | `report/<arch>_N` where `report/<arch>` exists | Repeated bench/gym pipeline runs; brain has already ingested them |
| Synthetic training reports | `report/syn_*` | Source MMDs stay in `report/brain/synthetic_queue/`; reports are generated outputs |

**Always kept (never touched):**
- `_boxing_bot` folders — active cache referenced by `ta_boxing.py`
- `report/brain/` — brain data + synthetic queue
- `report/taclaw/` + `report/taclaw_investigator/` — TAclaw outputs
- `report/bench/` — benchmark data
- All canonical arch folders (no numeric suffix)

**Stale graphs:**
- Reads `updated:` date from frontmatter of each `.claude/graphs/*.mmd`
- Flags any graph older than 60 days as needing review

## When to run

- After a bench loop (`bench-loop`) that generates `_1`, `_2`, ... variant folders
- After TAgym iterations that create new synthetic report folders
- Periodically as part of `/session-cleanup`

## Output example

```
## report-prune  [DRY-RUN]

────────────────────────────────────────────────────────────
  Numbered variant runs  (18 folders)
────────────────────────────────────────────────────────────
  [prune]   01_minimal_vulnerable_1              0.3 MB
  [prune]   01_minimal_vulnerable_2              0.3 MB
  ...

────────────────────────────────────────────────────────────
  Synthetic training reports  (13 folders)
────────────────────────────────────────────────────────────
  [prune]   syn_ai_system_gap002                 0.2 MB
  ...

  Total prunable: 31 folders  (8.4 MB)

────────────────────────────────────────────────────────────
  Graph staleness check
────────────────────────────────────────────────────────────
  ✓  All graphs updated within 60 days
```

## Related

- `/bench-loop` — generates numbered variant runs
- `/tagym` — generates synthetic report folders
- `report/brain/synthetic_queue/` — source MMDs (kept regardless)
- `.claude/graphs/` — codebase context graphs checked for staleness
