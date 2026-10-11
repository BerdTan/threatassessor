---
name: check-detect
description: Run the SOC detection rule regression suite (~15s, no LLM/network). Covers all 58 DETECT rules (rule evaluator), AIVSS→OCSF findings export, incident simulator scenarios (54 scenarios covering all 58 rules), and EventBroker sm_verdicts path. Optionally re-evaluates live governance_signals.json for one or all corpus architectures and shows which rules fire. Use after any change to policies/soc_detection_rules.yaml, chatbot/harness/rule_evaluator.py, chatbot/harness/stages.py, or chatbot/harness/governance.py.
allowed-tools: Bash(python3:*) Bash(source:*) Bash(pytest:*)
---

# check-detect — SOC Detection Rule Regression + Live Corpus Check

Runs the full detection-layer test suite (no LLM, no network) and optionally
re-evaluates all `governance_signals.json` files in `report/` through the live
rule evaluator to show which DETECT rules fire on real architecture data.

## Coverage

| Test file | What it covers |
|-----------|---------------|
| `test_soc_rule_evaluator.py` | All 58 DETECT rules — fire/no-fire, severity, actions, kill_chain_stage |
| `test_aivss_to_findings.py` | AIVSS→OCSF SecurityFinding + DetectionFinding export (escape signals) |
| `test_incident_simulator.py` | 54 incident scenarios → rule co-occurrence assertions (all 58 rules covered) |
| `test_harness_event_broker.py` | sm_verdicts event → LangfuseSink Score objects |

## Run

```bash
# Regression suite only (~15s, no LLM, no network)
python3 .claude/skills/check-detect/scripts/check-detect.py

# Regression + live rule evaluation for one architecture
python3 .claude/skills/check-detect/scripts/check-detect.py 21_agentic_ai_system

# Regression + live evaluation for all corpus architectures
python3 .claude/skills/check-detect/scripts/check-detect.py --all

# 6-dimension Data Quality pass on soc_detection_rules.yaml
python3 .claude/skills/check-detect/scripts/check-detect.py --dq
```

## DQ pass — 6 dimensions

`--dq` runs a static quality audit on the ruleset (no LLM, no network, ~30s with history replay):

| Dimension | What it checks |
|-----------|---------------|
| **Schema** | All required fields present: `id`, `name`, `domain`, `description`, `severity`, `conditions`, `actions`, `kill_chain_stage`, `ocsf_type_uid`, `csa_art`, `atlas_tactic` |
| **Distribution** | Domain × severity heatmap — spots over/under-represented domains and missing severity tiers |
| **Lineage** | Each condition `field:` path traced back to its source file (`governance.py`, `stages.py`, `access_logger.py`, etc.) — flags ghost fields never set in the pipeline |
| **Freshness** | Replays `RuleEvaluator` against `governance_signals_history.jsonl` to find last-fired date per rule — flags never-fired and stale rules |
| **Internal quality** | Action vocab (declared + extended SOC labels), operator set (standard + custom evaluator ops), severity tier validity, `combine` value |
| **Volume** | Severity tier bar chart + domain bar chart with single-rule domain warnings |

Exit 0 only when schema, lineage, and quality are all clean. Freshness and volume produce warnings but do not block.

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
- Run `--dq` when adding rules or new signal namespaces to check lineage coverage
