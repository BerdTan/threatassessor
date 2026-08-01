---
name: check-detect
description: Run the SOC detection rule regression suite (~15s, no LLM/network). Covers all 19 DETECT rules (rule evaluator), AIVSS→OCSF findings export, incident simulator scenarios (20 scenarios covering all 19 rules), and EventBroker sm_verdicts path. Optionally re-evaluates live governance_signals.json for one or all corpus architectures and shows which rules fire. Use after any change to policies/soc_detection_rules.yaml, chatbot/harness/rule_evaluator.py, chatbot/harness/stages.py, or chatbot/harness/governance.py.
allowed-tools: Bash(python3:*) Bash(source:*) Bash(pytest:*)
---

# check-detect — SOC Detection Rule Regression + Live Corpus Check

Runs the full detection-layer test suite (no LLM, no network) and optionally
re-evaluates all `governance_signals.json` files in `report/` through the live
rule evaluator to show which DETECT rules fire on real architecture data.

## Coverage

| Test file | What it covers |
|-----------|---------------|
| `test_soc_rule_evaluator.py` | All 18 DETECT rules — fire/no-fire, severity, actions, kill_chain_stage |
| `test_aivss_to_findings.py` | AIVSS→OCSF SecurityFinding + DetectionFinding export (escape signals) |
| `test_incident_simulator.py` | 19 incident scenarios → rule co-occurrence assertions (all 18 rules covered) |
| `test_harness_event_broker.py` | sm_verdicts event → LangfuseSink Score objects |

## Run

```bash
# Regression suite only (~15s, no LLM, no network)
python3 .claude/skills/check-detect/scripts/check-detect.py

# Regression + live rule evaluation for one architecture
python3 .claude/skills/check-detect/scripts/check-detect.py 21_agentic_ai_system

# Regression + live evaluation for all corpus architectures
python3 .claude/skills/check-detect/scripts/check-detect.py --all
```

## Live check output

For each architecture shows:
- Which DETECT rules fired and their severity
- `validation.val_pct` and `manipulation.gap_similarity_avg` (new signals)
- `sm_verdicts.acceptance_rate` if present

## When to use

- After editing `policies/soc_detection_rules.yaml`
- After changing `chatbot/harness/rule_evaluator.py`
- After changing `chatbot/harness/stages.py` (AIVSSStage / ScrumMasterStage)
- After changing `chatbot/harness/governance.py` (new exploitation/identity signals)
- After running `/incident-simulator --write` on a new scenario
- After running `/detect-loop` to add a new coverage scenario
- Before committing any detection-layer change
