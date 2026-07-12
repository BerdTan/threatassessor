---
name: rerun-corpus
description: Audit and selectively re-run the deterministic analysis engine across all 26 corpus architectures. Default (no args) shows a staleness check — which reports are missing metadata, which arch types need engine fixes re-applied, and the current corpus score table. Pass --ai-only to re-run only AI/agentic architectures, --all to re-run everything, or a single arch name to re-run one. Use after engine changes (self_validation.py, ground_truth_generator.py, rapids_driven_controls.py) to confirm scores are consistent and no regressions landed.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Corpus Re-run

Audits `/report/` against the current engine version and re-runs analysis where needed.

Re-run is deterministic only (`python3 -m chatbot.main --gen-arch-truth`) — no LLM calls, no Expert Review. Takes ~15–20 sec per architecture.

## Run

```bash
# Staleness audit only (default — read-only, fast)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py

# Re-run AI/agentic architectures only (highest impact after engine changes)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py --ai-only

# Re-run a single architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py 21_agentic_ai_system

# Re-run all 26 architectures (~8 min)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py --all
```

## What the audit checks

| Signal | Stale if |
|--------|---------|
| `run_id` / `run_ts` | Missing from `ground_truth.json` metadata (pre engine-metadata fix) |
| `pattern_sources` | Missing — engine couldn't show which analysis engines fired |
| `ai_system` validation | Arch type is `ai_system` but `run_ts` predates the self_validation + hop-coverage fix (2026-07-12) |
| Score floor | TATB overall < 70 (below Solid) |

## Output format

```
STALE  22_generic_name_with_ai_nodes  type=ai_system  no run_id  → needs re-run
OK     21_agentic_ai_system           type=ai_system  run_id=21_agentic_ai_system_20260712T060119
OK     05_legacy_flat_network         type=web_app    run_id=05_legacy_flat_network_20260712T...
META   03_aws_3tier                   type=web_app    no run_id  (metadata only — score unaffected)
...

Summary: 1 STALE (need re-run), 24 META (display only), 1 OK
Re-run stale:  python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py --ai-only
Re-run all:    python3 .claude/skills/rerun-corpus/scripts/rerun-corpus.py --all
```

After re-running, a TATB corpus table is printed with before/after scores.

## When to run

- After any change to `self_validation.py`, `ground_truth_generator.py`, `rapids_driven_controls.py`, `per_node_ttp_mapper.py`, or `exhaustive_mitigation_mapper.py`
- After updating MITRE data (`/update-data`)
- To confirm a corpus-wide score regression didn't land

## Related skills

- `/tatb-corpus` — score all architectures from existing reports (read-only)
- `/tatb-score` — score a single architecture
- `/backfill-aivss` — refresh AIVSS governance scores after a harness change
