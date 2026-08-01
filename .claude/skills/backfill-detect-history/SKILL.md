---
name: backfill-detect-history
description: Seed governance_signals_history.jsonl for all 27 corpus architectures using their current governance_signals.json as a synthetic baseline entry (run_id=backfill-baseline, ts=2026-08-01T00:00:00Z). Gives /detect-trend at least one data point per architecture immediately. Safe to re-run — skips architectures that already have history. Use once after initial deploy to unblock the trend view before real pipeline runs accumulate.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# backfill-detect-history — Seed Synthetic Baseline History

Writes one `governance_signals_history.jsonl` entry per corpus architecture using
the current `governance_signals.json` as the baseline snapshot. This gives
`/detect-trend` an initial data point for every architecture immediately, without
waiting for real pipeline runs to accumulate.

## Run

```bash
# Seed all corpus architectures (skip those already having history)
python3 .claude/skills/backfill-detect-history/scripts/backfill-detect-history.py

# Force re-seed even if history already exists
python3 .claude/skills/backfill-detect-history/scripts/backfill-detect-history.py --force
```

## What it writes

For each architecture that has `governance_signals.json`:
```json
{"run_id": "backfill-baseline", "ts": "2026-08-01T00:00:00Z", "arch": "21_agentic_ai_system", "signals": {...}}
```

## After running

Run `/detect-trend --all` to see which rules fire on the baseline snapshot.
Then run new analyses — each run appends a second entry, enabling rising/falling trends.
