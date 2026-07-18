---
name: review-unsure
description: Triage UNSURE cross-expert findings from an ER run. Runs deterministic checks against report artefacts first (no LLM needed for many items), then calls the LLM for a REAL/DISMISS verdict + ADR patch on the remainder. Use after any ER run that produces UNSURE items in the Cross-Expert Findings tab.
allowed-tools: Bash(python3:*) Bash(source:*)
compatibility: Requires 07_moe_orchestrator.json and ground_truth.json for the target architecture. Run /run-er first if they are missing.
---

# review-unsure — UNSURE Finding Triage

After an ER run, UNSURE items in the Cross-Expert Findings tab represent single-critic findings that
lack corroboration. Many can be auto-dismissed by checking the report artefacts (control list,
after.mmd node count, validation status). The rest get an LLM verdict (REAL/DISMISS) with an ADR
patch if real.

## Run

```bash
# Triage all UNSURE items (deterministic checks, then LLM for remainder)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/review-unsure/scripts/review-unsure.py 21_agentic_ai_system

# MEDIUM+ only (skip LOW)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/review-unsure/scripts/review-unsure.py 21_agentic_ai_system --severity MEDIUM

# Dry-run: deterministic checks only — no LLM calls, prints pending count
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/review-unsure/scripts/review-unsure.py 21_agentic_ai_system --dry-run

# Most recent report (no arch argument)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/review-unsure/scripts/review-unsure.py

# JSON output (for scripting)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/review-unsure/scripts/review-unsure.py 21_agentic_ai_system --json
```

## What it checks deterministically (no LLM)

| Category | Check |
|---|---|
| `implementation_status` | Count NEW_* nodes in after.mmd vs control_recommendations count |
| `detection_tuning` / `detection_baseline` | Check if UEBA / behavioral analytics control is in the list |
| `human_layer` | Check if user training or phishing simulation control is present |
| `validation` | Check ground_truth validation_status and whether errors are structural vs environmental |
| `diagram_completeness` | NEW_* count ≥ control count → complete |
| `detection_operability` (LOW) | LOW severity advisory → flag as informational, not blocking |
| `control_gap` / `coverage_gap` | Extract T-code from description, check if any control maps it |

Items that cannot be resolved deterministically escalate to the LLM.

## What the LLM produces

For each unresolved item:
- **VERDICT**: `REAL` or `DISMISS`
- **REASON**: one sentence citing the specific control or node
- **ADR_PATCH**: one-sentence ADR entry to add if REAL (e.g. "Add UEBA with path-specific thresholds for AP-1 to AP-5 end-user corroborated paths.")

## Output example

```
  UNSURE Triage — 21_agentic_ai_system
  5 items · all severities
  ──────────────────────────────────────

  1. ▪    LOW       validation  ← tester
     Ground truth validation shows 32 environmental issues…
     ✓ DISMISS  Validation issues are environmental and MITRE mappings confirmed correct.

  2. ▪▪   MEDIUM    detection tuning  ← purple_team
     AP-1 through AP-5 marked as end-user paths…
     ✗ REAL    No UEBA or behavioral analytics control exists in recommendations.
     → ADR:    Add UEBA with path-specific detection baselines for AP-1 through AP-5.

  3. ▪    LOW       human layer  ← purple_team
     T1566 (Phishing) mapped to all 5 paths…
     ✓ DISMISS  Control 'user training' already addresses the human layer.

  ──────────────────────────────────────
  ✓ 4 dismissed  ✗ 1 real gap
```

## Prerequisites

1. ER run complete: `07_moe_orchestrator.json` exists for the architecture
2. `ground_truth.json` exists (always present after any analysis)
3. For LLM verdicts: LLM API key set in `.env`

## Notes

- `--dry-run` is fast (~1s) — use to get a quick count of how many items need LLM review
- LLM calls use the default model configured in `.env` (same as TA uses for analysis)
- REAL findings with ADR patches are advisory — apply them via the ADR tab or a re-run of `/run-er`
- Items already addressed by recent critic re-runs may appear as false positives; check the ER tab first

## Related skills

- `/run-er` — run or re-run Expert Review critics
- `/tatb-score` — check TATB rubric after resolving gaps
- `/regen-reports` — regenerate report files after ADR updates
