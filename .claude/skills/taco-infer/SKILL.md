---
name: taco-infer
description: Run TACOAgent brain-only inference vs HOLD_OUT_ARCHS and compare to ground truth. Shows technique and control precision/recall per arch. Tests routing logic and HopRecord format, not raw query_brain(). No API needed.
---

# taco-infer

Brain-only TACO inference vs hold-out ground truth.

Distinct from `/brain-infer` — runs through `TACOAgent` (with `threshold=1.1` to suppress harness)
so routing logic and HopRecord serialization are validated, not just the raw `query_brain()` call.

## Usage

```bash
# All HOLD_OUT_ARCHS (default)
python3 .claude/skills/taco-infer/scripts/taco-infer.py

# Single arch
python3 .claude/skills/taco-infer/scripts/taco-infer.py --arch 03_aws_3tier

# All corpus arches (not just hold-out)
python3 .claude/skills/taco-infer/scripts/taco-infer.py --all

# Raw JSON
python3 .claude/skills/taco-infer/scripts/taco-infer.py --json
```

## Output per arch

- `conf`: brain confidence, cache_route
- `patterns_fired`: count
- Techniques: precision / recall vs ground_truth
- Controls: precision / recall vs missing controls
- Action hint: calibration advisory if confidence is poorly calibrated
