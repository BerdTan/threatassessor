---
name: run-er
description: Run Expert Review (MoE critics + ScrumMaster) on any architecture that has an existing analysis. Three modes — sequential (3 core critics), full_moe (5 critics + SM, generates Plan-Actionable data), or single-critic (re-run one critic by name). Streams live critic results with scores, gaps, and final confidence. ~60–120s for full_moe, ~30–60s for sequential.
allowed-tools: Bash(python3:*) Bash(source:*)
compatibility: Requires API server running (./scripts/api/api_start.sh) and an existing analysis (ground_truth.json) for the target architecture.
---

# run-er — Expert Review Runner

Streams the expert review pipeline live: each critic result prints as it arrives — score,
validation status, top gaps, and confidence adjustment. Handles auth, SSE parsing, and
cancellation on Ctrl-C automatically.

## Run

```bash
# 3 core critics — sequential (default)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/run-er/scripts/run-er.py 04_zero_trust

# Full MoE — 5 critics + ScrumMaster (needed for Plan-Actionable TATB score)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/run-er/scripts/run-er.py 04_zero_trust --full

# Run critics in parallel (3 core critics, faster wall-clock)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/run-er/scripts/run-er.py 04_zero_trust --mode parallel

# Re-run a single critic on an existing MoE result
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/run-er/scripts/run-er.py 04_zero_trust --critic red_team

# Run ScrumMaster only (needs 07_moe_orchestrator.json from a prior ER run)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/run-er/scripts/run-er.py 04_zero_trust --critic scrum_master
```

## Modes

| Mode | Critics | SM | Generates | Use when |
|------|---------|-----|-----------|----------|
| default (sequential) | Architect, Tester, Red Team | ✗ | `04–07_*.json` | Quick validation pass |
| `--full` | + Purple Team, Blackhat | ✅ | `04–08_*.json` | Need Plan-Actionable TATB score |
| `--mode parallel` | Architect, Tester, Red Team | ✗ | `04–07_*.json` | Faster, less deterministic |
| `--critic <name>` | One critic only | depends | Updates that critic's file | Targeted re-run |

## What it shows (live)

```
▸ Architect
  ⚠️  Architect     score= 78  adj=-5.0%  gaps=5  strengths=6
      ▸ [HIGH] Validation failure blocks assessment...
      ▸ [MEDIUM] WAF and INPUT VALIDATION are web controls...

▸ Tester
  ✅  Tester        score= 98  adj= 0.0%  gaps=0  strengths=6

▸ Red Team
  ⚠️  Red Team      score= 42  adj=-3.0%  gaps=5  strengths=5

──────────────────────────────────────────────────────────────
  Final confidence:  68.4%  (-11.0pp)  ████████████████░░░░░░░░
  Critical items:    5
  High-priority:     6
```

## Prerequisites

1. API server running: `./scripts/api/api_start.sh`
2. `ground_truth.json` exists for the architecture (run analysis first)
3. For `--critic scrum_master`: `07_moe_orchestrator.json` must exist (run ER first)

## Failure fixes

| Error | Fix |
|-------|-----|
| `API server not running` | `./scripts/api/api_start.sh` |
| `No analysis found for '<arch>'` | Run analysis from dashboard or `python3 -m chatbot.main --gen-arch-truth` |
| `Prerequisites missing: 07_moe_orchestrator.json` | Run `run-er <arch>` (without `--critic`) first |
| `TM-API-KEY not found` | Add `API_KEY=<key>` to `.env` |
| HTTP 400 / invalid critic_mode | Valid modes: `sequential`, `parallel`, `auto` |
| Synthesis hangs at 97% | Bedrock latency — wait up to 60s; if stuck add `drop_params=True` to litellm call |

## Notes

- **`--full` always uses sequential mode** — Purple Team and Blackhat need prior critic
  results to do cross-validation; parallel mode skips the ordering dependency.
- **ScrumMaster generates `08_scrum_master.json`** and unlocks the Plan-Actionable
  rubric in TATB. Without it, Plan shows N/A.
- **Labels are preserved** — `demo_expert_llm.sh` stashes `expected_threats.json` before
  cleaning; `run-er` calls the API directly so labels are never touched.
- **Ctrl-C cancels cleanly** — sends DELETE to `/api/v1/expert-review/cancel`.

## Related skills

- `/tatb-score` — check TATB rubric scores after running ER
- `/tatb-loop` — automated observe→fix→verify loop targeting weak signals
- `/aivss-score` — AIVSS governance scores
- `/quick-test` — verify API + deps before a session
