---
name: taco-run
description: CLI wrapper for POST /api/v1/taco/run-sync. Sends a query to the running TACO Agent and prints the HopChain with per-hop confidence, duration, and routing summary. Requires API on localhost:8000.
---

# taco-run

CLI wrapper for the TACO run-sync endpoint.

## Usage

```bash
python3 .claude/skills/taco-run/scripts/taco-run.py "query" [--arch NAME] [--mmd FILE] [--sim] [--json]
```

**Arguments:**
- `query` — natural-language threat question
- `--arch NAME` — known corpus arch_id (enables Brain + RAG)
- `--mmd FILE` — path to a .mmd file (enables Harness escalation)
- `--sim` — sim_mode: always walks Brain → RAG → Harness
- `--json` — print raw HopChain JSON

**Requires:** API running on `http://localhost:8000` with valid `TM-API-KEY` in `.env`.

## Examples

```bash
# Brain + RAG only (arch known, no MMD)
python3 .claude/skills/taco-run/scripts/taco-run.py "main threats?" --arch 03_aws_3tier

# Full chain with harness (low brain/rag confidence or sim_mode)
python3 .claude/skills/taco-run/scripts/taco-run.py "assess this" --mmd tests/data/architectures/03_aws_3tier.mmd --sim

# Raw JSON for scripting
python3 .claude/skills/taco-run/scripts/taco-run.py "threats?" --arch 01_minimal_vulnerable --json
```
