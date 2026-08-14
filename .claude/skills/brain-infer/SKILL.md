---
name: brain-infer
description: Run TA Brain infer mode against hold-out or all corpus architectures and compare predictions to ground truth. Shows technique/control precision and recall per arch, with actionable hints. Use to validate brain quality before and after brain-grow runs.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Brain Infer

Validates brain predictions against real ground truth. Answers: "how accurate is the brain right now, and what should I do about it?"

## Run

```bash
# Hold-out archs (default — the 3 archs excluded from training)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-infer/scripts/brain-infer.py

# Single arch
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-infer/scripts/brain-infer.py --arch 03_aws_3tier

# All corpus archs (slowest — hits KG for each)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-infer/scripts/brain-infer.py --all

# JSON output
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-infer/scripts/brain-infer.py --json
```

## What it shows

| Field | Description |
|-------|-------------|
| published_conf | min(corpus, benchmark) — what the brain claims |
| patterns fired | Which BRAIN-NNN patterns matched |
| Techniques precision | predicted ∩ actual / predicted |
| Techniques recall | predicted ∩ actual / actual |
| Controls precision | predicted ∩ actual / predicted |
| Controls recall | predicted ∩ actual / actual |
| Action hint | What to do if confidence or precision is low |

## Flags

| Flag | Description |
|------|-------------|
| `--arch NAME` | Single arch from report/ directory |
| `--hold-out` | The 3 defined hold-out archs (default) |
| `--all` | Every arch in instances.jsonl |
| `--json` | Raw JSON output for piping |

## Reading the output

- Results sorted worst published_conf first — the most urgent items are at the top
- **Red** published_conf < 0.4 → run `brain-grow` before trusting predictions
- **Amber** precision < 40% → brain knows the arch type but predicts the wrong specifics
- **Green** precision ≥ 70% → predictions are reliable for this arch type

## Failure fixes

| Error | Fix |
|-------|-----|
| `ground_truth.json not found` | Run analysis for the arch first |
| All controls precision = n/a | Pattern has no control predictions — add more instances of this arch type |
| `patterns_fired = none` | No pattern matches this arch type — run `brain-grow` to add training data |
| Hold-out archs not found | Check `HOLD_OUT_ARCHS` in `ta_brain_builder.py` match actual report dirs |

## Notes

- Hold-out archs are excluded from distiller training — they are the true test set. High precision here = the brain generalises.
- `--all` mode includes training archs; precision there is optimistic (brain saw them during training).
- Use `--hold-out` for an honest calibration check; use `--all` to find arch types with zero coverage.

## Related skills

- `/brain-grow` — run after seeing low precision to improve predictions
- `/brain-cache` — warm cache before running `--all` for faster queries
