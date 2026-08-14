---
name: brain-grow
description: TA Brain full rebuild + multi-round synthetic generation loop to close Brier calibration gaps. Ingests new corpus archs, generates synthetic MMDs for forced gaps, submits to harness, recalibrates. Run after adding new corpus archs or to improve brain confidence.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Brain Grow

Full rebuild + multi-round generate→ingest→calibrate cycle. Closes the calibration gap between brain predictions and real-world ground truth.

## Run

```bash
# Show current state only
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-grow/scripts/brain-grow.py --status

# Dry run — show what would be generated
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-grow/scripts/brain-grow.py --dry-run

# Full loop (default 3 rounds)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-grow/scripts/brain-grow.py

# More rounds for stubborn gaps
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-grow/scripts/brain-grow.py --rounds 5
```

## What it shows

| Section | Contents |
|---------|----------|
| Brain State | Instances, patterns, forced gaps, pattern version |
| Brier Scores | Per-arch-type prediction error vs hold-out (green ≤ 0.35, red > 0.35) |
| Per-round table | Generated MMDs, submission status, Brier delta |
| Final summary | Total synthetics, remaining gaps, overall improvement |

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--rounds N` | 3 | Max generate→ingest→calibrate cycles |
| `--dry-run` | off | Show gap state without calling LLM |
| `--status` | off | Print current state and exit immediately |

## Failure fixes

| Error | Fix |
|-------|-----|
| `API unreachable` | Start the API: `./scripts/api/api_start.sh` |
| `ta_brain.json not found` | Run `build_brain` first or use `brain-ingest` to add instances |
| Brier not improving | Gaps may need more rounds; calibration is bounded by 1 hold-out per arch type |
| `generate_synthetic_mmds returns []` | All gaps already staged — queue them with `--status` then approve |

## Notes

- The API must be running (`localhost:8000`) for submission. Skill skips submission gracefully if unreachable.
- Each round generates max 2 synthetic MMDs (one per top-priority gap). Multiple rounds target the same gaps until Brier drops below 0.35.
- Calibration improves per round but is bounded by the 1-sample hold-out set. The threshold (0.35) is a strict target; each round narrows the gap.

## Related skills

- `/brain-infer` — inspect prediction accuracy before and after running grow
- `/brain-ingest` — add a single arch incrementally
- `/brain-cache` — warm/evict cache after a grow run
- `/tatb-score` — separate quality score (TATB) for individual architectures
