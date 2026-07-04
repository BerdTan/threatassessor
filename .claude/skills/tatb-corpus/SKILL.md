---
name: tatb-corpus
description: Score all architectures in /report/ across the four TATB rubrics and print a visual corpus map — bar table, heatmap, and pipeline stage attribution. Shows which architectures are Excellent/Solid/Weak/Draft on each dimension and identifies which pipeline stages to fix for the largest corpus-wide gain. No UI needed. ~10-15 seconds (MITRE fetch batched once).
allowed-tools: Bash(python3:*) Bash(source:*)
---

# TATB Corpus — All Architectures

Scores every architecture in `report/` on the four TATB rubrics and produces three views: a sortable bar table, a compact heatmap, and a pipeline stage attribution table. Architectures with partial data (GT only, no MoE/SM) are scored on available signals and marked N/A for the rest.

## Run

```bash
# Default — sort by overall, colour output
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/tatb-corpus/scripts/tatb-corpus.py

# Sort by specific rubric
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/tatb-corpus/scripts/tatb-corpus.py --sort ttp

# JSON output (for agent consumption or piping)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/tatb-corpus/scripts/tatb-corpus.py --json > tatb-corpus.json

# No colour (for CI / log files)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/tatb-corpus/scripts/tatb-corpus.py --no-color
```

## What it shows

| View | Contents |
|------|----------|
| Bar table | One row per architecture · four rubric bars (0-100) + overall · sorted |
| Heatmap | One character per arch per dimension · worst→best left→right · patterns visible instantly |
| Stage attribution | Corpus average per sub-signal · maps each signal to the pipeline stage responsible · three ▼ signals = three stages to fix |
| Corpus stats | min/max/avg overall across all scored architectures |

## Interpreting the output

- **TTP row mostly ▼** → most architectures ran `api_only` without full MoE — no cross-critic data
- **Risk hop_pct avg <60%** → ADR generator not assigning all four dir_category layers — fix in `threat_report.py`
- **Plan closure avg <50%** → SM prompt not referencing AP-IDs — add instruction to SM prompt
- **Threat row mostly ■** → AnalysisStage is working correctly; structural inference is consistent

## Sort options

`--sort threat | ttp | risk | plan | overall`

## Feedback loop

The stage attribution table at the bottom maps every weak corpus signal to its pipeline stage. Fix in order of corpus impact:

1. Run `full_moe` on key architectures → raises TTP cross-critic from avg 13% to ~60%
2. Fix ADR dir_category assignment in `ReportStage` → raises hop layer coverage from avg 44%
3. Add AP-ID instruction to SM prompt → raises plan closure from avg 40%
4. Tighten `self_validation.py` thresholds → raises TTP validation from avg 65%

Re-run corpus after each fix to measure improvement.

## Failure fixes

| Error | Fix |
|-------|-----|
| `No architectures found` | Run at least one analysis from dashboard or CLI first |
| MITRE fetch fails (all alignment 50%) | Start API server: `./scripts/api/api_start.sh` |
| Plan shows N/A for all | No architectures have SM data — run `full_moe` from dashboard Expert Review |

## Related skills

- `/tatb-score` — deep-dive on a single architecture
- `/aivss-score` — AIVSS-specific breakdown per architecture
- `/backfill-aivss` — generate governance_signals.json for architectures that lack it
