---
name: tatb-loop
description: TATB feedback loop — observe corpus or single-arch TATB scores, diagnose weak signals, propose targeted pipeline stage fixes, gate on human approval, apply changes, re-run TATB to verify improvement, and log the before/after delta to docs/DECISIONS.md. The agent does NOT autonomously commit code; every code change requires explicit human approval.
allowed-tools: Bash(python3:*) Bash(source:*) Bash(git:*) Bash(grep:*) Bash(sed:*)
---

# TATB Loop Agent — Evidence-Driven Pipeline Improvement

Runs a scored observe→diagnose→prescribe→gate→apply→verify cycle. Each iteration identifies
the single weakest signal across the corpus (or a named architecture), traces it to its
pipeline stage, generates the minimum change, waits for human approval, applies it, and
measures the delta.

## Run

```bash
# Full corpus — find and fix the worst signal across all 25 architectures
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tatb-loop/scripts/tatb-loop.py

# Single architecture — tighter loop, faster feedback
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tatb-loop/scripts/tatb-loop.py --arch 01_minimal_vulnerable_2

# Diagnose only — show prescription without applying anything
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tatb-loop/scripts/tatb-loop.py --diagnose-only

# Specific signal to target (skip auto-selection)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/tatb-loop/scripts/tatb-loop.py --target hop_pct
```

## What it does

1. **Observe** — runs TATB corpus or single-arch scorer, collects per-signal averages
2. **Diagnose** — identifies the weakest signal, maps it to the responsible pipeline stage
   and the specific code location (file + line) that controls the behaviour
3. **Prescribe** — generates the minimum targeted change: a keyword addition, a prompt
   sentence, a threshold value. Shows a unified diff for review.
4. **Gate** — displays the prescription and waits for `y/n/skip` approval. Nothing is
   written without explicit `y`.
5. **Apply** — writes the approved change to the source file. Does NOT git-commit.
6. **Verify** — re-runs TATB on the same scope. Shows before/after delta per signal.
7. **Log** — appends a dated entry to `docs/DECISIONS.md`:
   signal, stage, change summary, before score, after score.

## Signals and their pipeline stages

| Signal | Stage | File |
|--------|-------|------|
| `closure_pct` | ScrumMasterStage | `chatbot/modules/agents/critics/scrum_master_critic.py` |
| `hop_pct` | ReportStage → ADR | `chatbot/modules/exhaustive_mitigation_mapper.py` |
| `val_pct` | QualityStage | `chatbot/modules/self_validation.py` |
| `mitre_pct` | ReportStage | `chatbot/modules/exhaustive_mitigation_mapper.py` |
| `node_binding` | AnalysisStage | `chatbot/modules/ground_truth_generator.py` |
| `tech_variety` | AnalysisStage | RAPIDS + structural inference (no simple fix) |
| `cross_pct` | CriticStage | Run full_moe on more architectures (no code fix) |

## Safety

- **Read-only until `y` is entered.** All file writes are gated.
- **Does NOT git-commit.** You review and commit separately.
- **Does NOT change security outputs.** Only prompt text, keyword lists, and thresholds.
- **Idempotent prescriptions.** The agent checks whether the change is already present
  before proposing it. Re-running on an already-fixed signal is a no-op.

## Failure fixes

| Error | Fix |
|-------|-----|
| `API server required` | Start: `./scripts/api/api_start.sh` |
| `No architectures scored` | Run at least one analysis from dashboard first |
| MITRE fetch fails | API server must be running for alignment scores |
| `Prescription already applied` | Signal is already fixed — loop moves to next weakest |
| `After score worse than before` | Revert: `git diff` shows the change; `git checkout` to undo |

## Related skills

- `/tatb-score` — single-arch TATB scorecard
- `/tatb-corpus` — corpus map across all architectures
- `/quick-test` — integration sanity check before running a loop
