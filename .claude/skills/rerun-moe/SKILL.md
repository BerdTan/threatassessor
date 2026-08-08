---
name: rerun-moe
description: Batch-rerun FULL_MOE expert review across all or selected corpus architectures via the REST API. Use after critic prompt rewrites (critic-gym), critic logic changes, or any MoE pipeline change where existing report JSON files need refreshing. Requires API running. Runs sequentially with configurable concurrency, polls each job to completion, prints a per-arch result table and TATB delta summary on completion.
argument-hint: "[--all] [--arch <name>] [--ai-only] [--concurrency N] [--dry-run]"
---

# rerun-moe — Batch MoE Expert Review Runner

Submits FULL_MOE expert review jobs to the REST API for all or selected corpus
architectures. Runs sequentially (or N at a time with --concurrency) and polls
each job to completion before moving on.

## When to use

- After `/critic-gym` rewrites — critic JSON files are stale until rerun
- After changes to any critic Python logic (scoring weights, rubric dicts)
- After ScrumMaster changes
- When MoE confidence scores look stale vs the current engine output

## Do NOT use for

- Engine changes (ground_truth.json, attack paths, controls) — use `/rerun-corpus` instead
- TATB rubric changes — TATB is computed from ground_truth, no MoE rerun needed
- DETECT rule changes — those evaluate governance_signals, no MoE rerun needed

## Run

```bash
# Dry run — show what would be submitted, no API calls
python3 .claude/skills/rerun-moe/scripts/rerun_moe.py --dry-run

# Rerun all 27 corpus archs (sequential, ~40 min)
python3 .claude/skills/rerun-moe/scripts/rerun_moe.py --all

# Rerun with 3 concurrent jobs (~15 min)
python3 .claude/skills/rerun-moe/scripts/rerun_moe.py --all --concurrency 3

# Rerun AI/agentic archs only
python3 .claude/skills/rerun-moe/scripts/rerun_moe.py --ai-only

# Rerun a single arch
python3 .claude/skills/rerun-moe/scripts/rerun_moe.py --arch 10_complex_enterprise

# Rerun a comma-separated list
python3 .claude/skills/rerun-moe/scripts/rerun_moe.py --arch 01_minimal_vulnerable,10_complex_enterprise
```

## Output

Per-arch progress with job status and elapsed time. On completion:
- Per-arch result table (PASS/FAIL + confidence)
- TATB corpus delta if --tatb flag set

## Prerequisites

- API running: `./scripts/api/api_start.sh`
- API key in .env: `API_KEY=...`
