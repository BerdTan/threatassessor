---
name: brain-ingest
description: Add one architecture report directory to the TA Brain instance layer incrementally without a full rebuild. Appends the instance and re-runs the distiller to update patterns. Use after running a one-off analysis you want the brain to learn from.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Brain Ingest

Incrementally add one arch to the brain instance layer. Faster than `brain-grow` when you just ran a single analysis and want the brain to learn from it immediately.

## Run

```bash
# Dry run — show extracted instance without writing
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-ingest/scripts/brain-ingest.py --arch-dir report/03_aws_3tier --dry-run

# Ingest for real
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && python3 .claude/skills/brain-ingest/scripts/brain-ingest.py --arch-dir report/my_new_arch
```

## What it shows

| Field | Description |
|-------|-------------|
| arch_id | Directory name used as instance ID |
| arch_type | Detected architecture type (web_app, ai_system, etc.) |
| topology_sig | Structural fingerprint (hash of node types + edge pattern) |
| techniques | Count of MITRE techniques found |
| controls_missing | Count and top-5 missing controls |

## Flags

| Flag | Required | Description |
|------|----------|-------------|
| `--arch-dir PATH` | Yes | Path to report dir with ground_truth.json |
| `--dry-run` | No | Show extraction result without writing |

## Failure fixes

| Error | Fix |
|-------|-----|
| `ground_truth.json not found` | Run analysis from dashboard or CLI first |
| `Already ingested` | Arch already in instances.jsonl — use `--dry-run` to inspect |
| `Could not extract instance` | Check that governance_signals.json also exists in the arch dir |
| Pattern count drops | Normal if new arch shifts co-occurrence frequencies; run `brain-grow` for full rebuild |

## Related skills

- `/brain-grow` — full rebuild + multi-round calibration loop
- `/brain-infer` — check prediction accuracy after ingesting
- `/brain-cache` — evict stale cache after pattern version bumps
