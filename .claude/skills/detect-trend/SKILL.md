---
name: detect-trend
description: Show per-rule firing trends across governance_signals_history.jsonl for one or all corpus architectures. Trends: new | rising | stable | falling | cleared | never. Requires at least 2 pipeline runs per architecture to show directional trends (single-run snapshot shows new/never only). Use after running /backfill-detect-history to seed synthetic baselines, or after multiple real pipeline runs accumulate. Read-only — no side effects.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# detect-trend — Per-Rule Firing Trend Analysis

Shows how each DETECT rule's firing pattern has changed across pipeline runs
for a single architecture or the full corpus.

## Trend labels

| Label | Meaning |
|-------|---------|
| `★ new` | Fired in the latest run, never fired before |
| `↑ rising` | Firing rate increasing over recent runs |
| `→ stable` | Firing rate unchanged |
| `↓ falling` | Firing rate decreasing over recent runs |
| `✓ cleared` | Was firing, did not fire in latest run |
| `— never` | No run has ever triggered this rule |

## Run

```bash
# Trend for one architecture
python3 .claude/skills/detect-trend/scripts/detect-trend.py 21_agentic_ai_system

# Trend matrix for all corpus architectures
python3 .claude/skills/detect-trend/scripts/detect-trend.py --all

# Show only rules with non-never trends (signal only, no noise)
python3 .claude/skills/detect-trend/scripts/detect-trend.py --all --signal-only
```

## Output

Single arch: one row per rule, columns: rule_id | trend | runs | fired | rate | last 5
Corpus (--all): rule × arch matrix showing trend label per cell

## Data source

Reads `report/<arch>/governance_signals_history.jsonl` — written by AIVSSStage
on every pipeline run. One JSON line per run: `{run_id, ts, arch, signals}`.

If no history file exists for an architecture, all rules show `— never`.
Run `/backfill-detect-history` to seed synthetic baselines from current snapshots.

## When to use

- After running a new analysis to see if any rule changed status (new/cleared)
- After `/detect-loop --all` to verify prescription scenarios changed coverage
- Before writing Part 15 of the blog (trend story requires real data points)
- At session start to get the detection health picture at a glance
