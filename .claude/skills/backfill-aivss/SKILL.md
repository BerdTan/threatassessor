---
name: backfill-aivss
description: Generate or refresh governance_signals.json + AIVSS scores for existing report directories that are missing them. Supports all reports at once, a single architecture by name, or a fresh full analysis from an MMD file. Pass --force to re-score reports that already have AIVSS data. Use after upgrading the governance pipeline or to populate Insights tab cross-run data.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# AIVSS Backfill

Iterates report directories, loads existing `ground_truth.json` (and `07_moe_orchestrator.json` / `08_scrum_master.json` when available for richer internal flow scores), runs `QualityStage`, and writes `governance_signals.json` with AIVSS inbound/internal/outbound scores.

Takes ~1–3 seconds per report. No LLM calls.

## Run

```bash
# All reports missing governance_signals.json
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/backfill-aivss/scripts/backfill-aivss.py

# One architecture by directory name
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/backfill-aivss/scripts/backfill-aivss.py 00_serviceentry_3

# Run full pipeline on a new MMD file (AnalysisStage → ReportStage → QualityStage)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/backfill-aivss/scripts/backfill-aivss.py path/to/arch.mmd

# Re-score even if governance_signals.json already exists
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/backfill-aivss/scripts/backfill-aivss.py --force
```

## What it does

| Mode | Input | Action |
|------|-------|--------|
| All reports (default) | `report/` directory | Scores every dir with `ground_truth.json` but missing valid AIVSS data |
| Single arch | Directory name | Loads existing analysis; scores that one report |
| MMD file | Path ending `.mmd` | Runs `AnalysisStage + ReportStage + QualityStage` (full pipeline, ~30 sec) |
| `--force` | Any of the above | Re-scores even if `governance_signals.json` already has AIVSS composites |

## Output per report

```
NEW   00_serviceentry_3      D1:LOW D3:HIGH D5:LOW  [MoE]  AIVSS in:1.4 int:0.8 out:2.1  overall:2.1 MEDIUM
OK    00_serviceentry        (already had AIVSS data — skipped)
SKIP  example_architecture   no ground_truth.json
```

## Failure fixes

| Error | Fix |
|-------|-----|
| `QualityStage failed` | Check `logs/api.log` for traceback; most common cause is missing `_RE_PHONE` fix or governance import error |
| `No module named 'chatbot'` | Ensure `.venv` is activated; run from repo root |
| MMD path not found | Use absolute path or path relative to current directory |
| All AIVSS composites = None after backfill | `QualityStage` ran but governance adapter returned no signals — check `governance.agt_enabled` in settings |

## Notes

- **Internal flow scores** are low (near 0) unless `07_moe_orchestrator.json` is present — Expert Review enriches D2/D4 signals
- After backfill, `/api/v1/insights/all` will return AIVSS data for all scored architectures
- Re-running does **not** overwrite existing valid scores unless `--force` is passed
- The PII phone regex excludes CVE-YYYY-NNNN patterns (fix landed 2026-06-27); re-run with `--force` on old reports to clear false-positive PII flags

## Related skills

- `/aivss-score` — inspect scores for a single report without writing anything
- `/aivss-gate` — show gate thresholds and last SIEM event
- `/quick-test` — verify environment before running
