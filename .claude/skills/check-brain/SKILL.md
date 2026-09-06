---
name: check-brain
description: Brain flywheel health check — detects stagnation (no new corpus ingest, no TACO feedback) and reports pattern layer vitals. Run after any brain build or when brain_fast is routing most traffic. No LLM, no network.
allowed-tools: Bash(python3:*)
---

# check-brain — Brain Flywheel Health Monitor

Reports brain growth vitals and detects stagnation. Stagnant = no new instances
ingested in 30d AND no TACO feedback corrections. All reads are local — no API needed.

## What it checks

| Signal | Healthy | Warning | Stagnant |
|--------|---------|---------|----------|
| Last rebuild (days ago) | < 14 | 14–30 | > 30 |
| TACO feedback (30d) | ≥ 2 | 1 | 0 |
| Total instances | ≥ 10 | 5–9 | < 5 |

## Run

```bash
python3 .claude/skills/check-brain/scripts/check-brain.py
```

## Flywheel growth paths

1. **Novel arch → full pipeline** — new arch routes api_only/full_moe → generates
   ground_truth.json (generated_by: rapids) → brain builder ingests → patterns updated.
2. **TACO feedback** — user flags wrong prediction via `record_brain_feedback` →
   TACO processor adjusts pattern weights → brain rebuild.

brain_fast outputs are tagged `generated_by: brain_fast` and blocked by BrainGuardian
from re-ingest — circular growth prevention is enforced at build time.

## Recovery actions when stagnant

- Run a full pipeline on a new/unseen arch type
- Trigger `/brain-grow` to generate synthetic MMDs for gap arch types
- Run `/brain-infer` on an existing arch and flag corrections via TACO feedback
