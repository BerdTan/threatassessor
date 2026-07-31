---
name: incident-simulator
description: Synthesise realistic governance_signals.json payloads for named incident scenarios, run aivss-to-findings, and assert the expected DETECT rules fire. Each scenario fires 2-4 rules simultaneously. Optionally generates a storycaster narrative contextualised to a specific architecture. Pass a scenario name, or omit to list all. Use --story to generate a narrative. Use --write to persist the simulated governance_signals to a report directory.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# Incident Simulator

Synthesises `governance_signals.json` payloads based on real AI security incidents,
runs them through the SOC rule evaluator, and optionally generates a plain-English
incident narrative contextualised to a specific architecture.

## Scenarios

| ID | Name | Based on | Rules fired |
|---|---|---|---|
| `targeted_pipeline_attack` | Adversarial input + divergence suppression | Anthropic Mythos 5 + HuggingFace dataset loader | DETECT-005 (Critical) + DETECT-002 (Critical) |
| `rationalize_and_escape` | Confidence swing + token hyperfocus | Anthropic Opus 4.7 + OpenAI ExploitGym | DETECT-001 (High) + DETECT-003 (High) + DETECT-007 (Medium) |
| `exfil_with_adversarial_input` | Adversarial input leading to covert exfiltration | HuggingFace intrusion + DeepSeek/Hermes | DETECT-005 (Critical) + DETECT-004 (Critical) |
| `swarm_with_hyperfocus` | Broad recon sweep + single agent spike | HuggingFace swarm + OpenAI ExploitGym | DETECT-006 (Medium) + DETECT-003 (High) |
| `full_compromise` | All signals elevated simultaneously | Composite of all 5 incidents | DETECT-001 + DETECT-002 + DETECT-004 + DETECT-005 |

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
