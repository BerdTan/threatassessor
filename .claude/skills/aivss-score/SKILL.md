---
name: aivss-score
description: Run AIVSS v4 scorer on a report directory (ground_truth.json + governance_signals.json) and print the full inbound/internal/outbound breakdown, per-threat table, and a cached-vs-fresh delta if a prior score exists. Pass an architecture name as an argument, or omit for the most recent report. Read-only.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# AIVSS Score Inspector

Recomputes AIVSS scores from disk and prints the full breakdown. No LLM calls. Takes ~1 second.

## Run

```bash
# Most recent report
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/aivss-score/scripts/aivss-score.py

# Specific architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/aivss-score/scripts/aivss-score.py 00_serviceentry_3
```

## What it shows

| Section | Contents |
|---------|----------|
| Summary | Inbound / Internal / Outbound composite + severity + coverage %; Overall composite + severity; industry profile |
| Flow Metric Breakdown | Per-flow: each AIVSS metric (CS, LL, MR, DS, GV, AA, DC, AD, EI…) with sub-scores and composite |
| Per-Threat Scores | Technique ID, name, composite, severity, top_metric, mitigation_multiplier — sorted by score descending |
| Cached vs Fresh | If governance_signals.json already has an `aivss` block, shows delta between cached and freshly computed |
| Coverage warnings | Flags any flow with <50% signal coverage — low coverage = sparse signals, not necessarily clean |

## Failure fixes

| Error | Fix |
|-------|-----|
| `ground_truth.json not found` | Architecture has no analysis yet — run analysis first from dashboard or CLI |
| `AIVSSFlowScorer import fails` | Run `/quick-test` to verify harness_aivss module is importable |
| All composites show None | governance_signals.json missing or empty — run `/backfill-aivss <arch_name>` |
| Internal score = 0.0 | Expected when no Expert Review has run — internal flow uses MoE/SM signals |

## Notes

- **Internal flow** stays near zero until Expert Review (MoE) runs — it reads critic divergence and SM retrigger signals
- **Inbound / Outbound** are fully deterministic from `ground_truth.json` alone
- The script does **not** write `governance_signals.json` — use `/backfill-aivss` to persist scores

## Related skills

- `/backfill-aivss` — generate and persist governance_signals.json for past reports
- `/aivss-gate` — show gate thresholds and last SIEM event without recomputing
- `/quick-test` — broader integration sanity check
