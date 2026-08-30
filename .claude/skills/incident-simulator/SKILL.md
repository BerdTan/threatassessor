---
name: incident-simulator
description: Synthesise realistic governance_signals.json payloads for named incident scenarios, run aivss-to-findings, and assert the expected DETECT rules fire. 35 scenarios cover all 34 DETECT rules (DETECT-001 through DETECT-034), including AST02/05/08-grounded scenarios. Optionally generates a storycaster narrative contextualised to a specific architecture. Pass a scenario name, or omit to list all. Use --story to generate a narrative. Use --write to persist the simulated governance_signals to a report directory.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Incident Simulator

Synthesises `governance_signals.json` payloads based on real AI security incidents,
runs them through the SOC rule evaluator, and optionally generates a plain-English
incident narrative contextualised to a specific architecture.

## Scenarios (19 total — all 18 DETECT rules covered)

### Original incidents (DETECT-001 through 007)
| ID | Name | Based on | Rules fired |
|---|---|---|---|
| `targeted_pipeline_attack` | Adversarial input + divergence suppression | Anthropic Mythos 5 + HuggingFace dataset loader | DETECT-005 + DETECT-002 |
| `rationalize_and_escape` | Confidence swing + token hyperfocus | Anthropic Opus 4.7 + OpenAI ExploitGym | DETECT-001 + DETECT-003 + DETECT-007 |
| `exfil_with_adversarial` | Adversarial input → covert exfiltration | HuggingFace intrusion + DeepSeek/Hermes | DETECT-005 + DETECT-004 |
| `swarm_with_hyperfocus` | Broad recon + single agent spike | HuggingFace swarm + OpenAI ExploitGym | DETECT-006 + DETECT-003 |
| `full_compromise` | All original signals elevated | Composite of all 5 incidents | DETECT-001 + DETECT-002 + DETECT-004 + DETECT-005 |

### Extended scenarios (DETECT-008 through 015)
| ID | Rules fired |
|---|---|
| `sm_selection_pressure` | DETECT-008 |
| `credential_leak_in_architecture` | DETECT-009 |
| `path_traversal_mmd_probe` | DETECT-010 |
| `llm_egress_no_zdr` | DETECT-011 |
| `stale_mitre_data` | DETECT-012 |
| `high_outbound_surface` | DETECT-013 |
| `low_validation_coverage` | DETECT-014 |
| `critic_convergence` | DETECT-015 |
| `supply_chain_and_credentials` | DETECT-009 + DETECT-012 |
| `egress_and_low_validation` | DETECT-011 + DETECT-014 + DETECT-015 |

### AST-grounded scenarios (DETECT-016 through 018, OWASP AST10)
| ID | Based on | Rules fired |
|---|---|---|
| `critic_module_tampered` | OWASP AST02 / CVE-2025-59536 | DETECT-016 |
| `mutable_url_in_mmd` | OWASP AST05 / Air agent takeover PoC | DETECT-017 |
| `homoglyph_evasion_attempt` | OWASP AST08 / scanner bypass | DETECT-018 |
| `ast_composite` | Full AST02 + AST05 + AST08 chain | DETECT-016 + DETECT-017 + DETECT-018 |

## Run

```bash
# List all scenarios
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate && \
  python3 .claude/skills/incident-simulator/scripts/incident_simulator.py

# Run a specific scenario (print findings, don't write)
python3 .claude/skills/incident-simulator/scripts/incident_simulator.py targeted_pipeline_attack

# Run all scenarios and assert expected rules fire
python3 .claude/skills/incident-simulator/scripts/incident_simulator.py --test-all

# Generate storycaster narrative for a scenario + architecture
python3 .claude/skills/incident-simulator/scripts/incident_simulator.py targeted_pipeline_attack \
  --story --arch 03_aws_3tier

# Write simulated governance_signals to a report directory (then open SOC tab)
python3 .claude/skills/incident-simulator/scripts/incident_simulator.py targeted_pipeline_attack \
  --write --arch 03_aws_3tier
```

## What storycaster generates

Given the architecture's ground_truth.json (nodes, attack paths, entry/target nodes) and
the fired DETECT rules, storycaster writes a 3-part incident narrative:

1. **What happened** — specific to this architecture's nodes and topology
2. **How it was detected** — which rules fired, what signals crossed which thresholds
3. **What to do** — the playbook steps from the matched rules, prioritised by severity

The narrative is written for a non-technical stakeholder (CISO/CIO audience), not a
SOC analyst. It names real architecture nodes (e.g. "the Application Load Balancer")
rather than field names.

## Related skills

- `/aivss-to-findings` — run against real governance_signals for live detection
- `/check-governance` — governance guardrail regression suite
- `/run-er` — run Expert Review to generate richer MoE signals
