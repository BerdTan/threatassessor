---
name: check-routing
description: Run the smart routing regression suite (~5s, no LLM/network). Covers select_mode() tier logic (brain_fast/api_only/full_moe), AIVSS override, boxing signal loading (new format + old fallback), policy file validation, and integration checks against real boxing_results.json. Also validates model_routing.yaml thresholds and optionally shows live routing decisions for all boxed architectures. Use after any change to chatbot/harness/smart_router.py, policies/model_routing.yaml, or chatbot/modules/ta_boxing.py routing_signals.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# check-routing — Smart Routing Regression + Live Decision Check

Runs the routing test harness (no LLM, no network) and optionally prints live
routing decisions for every architecture that has `boxing_results.json`.

## Coverage

| Test class | What it covers |
|---|---|
| `TestLoadBoxingSignals` | New format, old format fallback, missing file, missing delta |
| `TestSelectModeNoData` | Default mode when no boxing data; policy-configurable default |
| `TestSelectModeAivssOverride` | AIVSS ≥ 7.0 forces full_moe; below threshold does not |
| `TestSelectModeBrainFast` | delta ≥ −0.15 AND hits ≥ 3; boundary; brain-wins case |
| `TestSelectModeApiOnly` | delta in middle band; old format corpus_hits=0 → full_moe |
| `TestSelectModeFullMoe` | delta < −0.30; zero hits; very negative delta |
| `TestLoadPolicy` | Real model_routing.yaml loads + has correct thresholds |
| `TestIntegrationRealBoxingFiles` | Live boxing_results.json → expected modes for 3 known arches |

## Usage

```bash
# Unit + integration tests only (~5s)
python3 .claude/skills/check-routing/scripts/check-routing.py

# Tests + live routing decisions for all boxed arches
python3 .claude/skills/check-routing/scripts/check-routing.py --live

# Tests + live decisions + policy dump
python3 .claude/skills/check-routing/scripts/check-routing.py --live --show-policy
```

## When to run

- After any edit to `chatbot/harness/smart_router.py`
- After changing thresholds in `policies/model_routing.yaml`
- After boxing a new architecture (verify it routes as expected)
- Before wiring brain_fast execution into the streaming flow
