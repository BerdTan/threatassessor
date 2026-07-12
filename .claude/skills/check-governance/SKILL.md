---
name: check-governance
description: Run the governance guardrail regression suite (56 tests, ~9s, no LLM calls). Covers all 5 governance dimensions — injection categories, evasion layers, PII/credential leakage, manipulation signals, sovereignty. Optionally re-check live governance_signals.json for one or all corpus architectures. Use after any change to chatbot/harness/governance.py to confirm no regressions.
allowed-tools: Bash(python3:*) Bash(source:*) Bash(pytest:*)
---

# check-governance — Governance Guardrail Regression

Runs the full governance test suite without any LLM calls or network access.
Covers injection detection (9 categories), evasion layers (base64, char-spacing,
typoglycemia), PII/credential leakage, manipulation signals, sovereignty checks.

## Run

```bash
# Full regression suite (~9s, no LLM, no network)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/check-governance/scripts/check-governance.py

# Check live governance_signals.json for one architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/check-governance/scripts/check-governance.py 21_agentic_ai_system

# Check all corpus architectures that have governance_signals.json
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/check-governance/scripts/check-governance.py --all
```

## What it checks

### Unit tests (always run)

| Test class | Coverage |
|---|---|
| `TestCleanInputs` | All 5 dimensions LOW on benign input |
| `TestExploitation` | Injection node, path traversal, oversized label |
| `TestDataLeakage` | NRIC, email, phone, credential keywords |
| `TestManipulation` | Fallback synthesis, divergence, confidence swing |
| `TestSovereignty` | Cross-boundary nodes, ZDR inference edges |
| `TestInjectionCategories` | 9 named categories, injection_categories dict |
| `TestEvasionLayers` | Char-spacing, dot-spacing, base64, typoglycemia |
| `TestNoFalsePositivesOnSecurityControls` | Security control labels → no FP |

### Live signal check (when arch or --all passed)

For each architecture, loads `governance_signals.json` from `report/` and reports:

- Exploitation severity and any injection categories found
- Leakage flags (PII, credential keywords)
- Manipulation signals (confidence swing, divergence)
- Sovereignty flags (cross-boundary nodes, ZDR signals)
- Overall risk level

## Output example

```
Governance Regression — tests/test_harness_governance.py
  56 passed  2 xfailed  0 failed   (9.1s)

Live Signal Check — 21_agentic_ai_system
  exploitation:   LOW  — no injection patterns
  leakage:        LOW  — no PII indicators
  manipulation:   MEDIUM  — confidence_swing=16.78, divergence=0
  sovereignty:    MEDIUM  — zdr_signals: inference→external: LLMGateway → Anthropic
  overall_risk:   MEDIUM
```

## When to run

- After any edit to `chatbot/harness/governance.py`
- After updating MITRE ATLAS data (new injection technique names)
- At session start when working on the governance or QualityStage pipeline

## Related skills

- `/quick-test` — broader integration sanity (MITRE load, API key, embeddings)
- `/aivss-score` — AIVSS scoring deep-dive for a specific architecture
- `/aivss-gate` — show gate thresholds and last SIEM event summary
