---
name: taco-benchmark
description: 7-dimension TACO quality scorer against ground_truth.json. Scores workspace / taco_brain / taco_rag modes on HOLD_OUT_ARCHS (8 archs). Use after TACOminiRAG changes to verify quality. No API needed — runs directly against report files.
---

# taco-benchmark

7-dimension TACO quality scorer.

## Dimensions

| Dim | What | Weight |
|-----|------|--------|
| Threat-Relevant | Technique recall vs ground truth | 0.20 |
| TTP-Accurate | Technique precision vs confirmed list | 0.20 |
| Risk-Defensible | Control coverage of missing controls | 0.15 |
| Plan-Actionable | SM action plan quality (None if no SM JSON) | 0.10 |
| Groundedness | Weighted T-ID + control coverage | 0.15 |
| Confidence-Calibration | Reported confidence vs actual accuracy | 0.10 |
| CISO-Utility | 5 proxy signals for actionability | 0.10 |

## Usage

```bash
# All HOLD_OUT_ARCHS (default)
python3 .claude/skills/taco-benchmark/scripts/taco-benchmark.py

# Single arch
python3 .claude/skills/taco-benchmark/scripts/taco-benchmark.py --arch 03_aws_3tier

# Raw JSON
python3 .claude/skills/taco-benchmark/scripts/taco-benchmark.py --json
```

## Output

Table with 3 rows per arch (workspace / taco_brain / taco_rag), one column per dimension + overall.
Footer shows taco_rag average across all hold-out arches.

**No API needed** — reads from `report/<arch>/ground_truth.json` directly.
