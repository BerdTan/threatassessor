# check-jev — Jev System 1 integration benchmark

Validates and benchmarks all 5 Jev (typesafe.ai) integration points in ThreatAssessor.
Exits 0 on pass, 1 on any failure.

## When to run

- When setting up Jev (`JEV_API_KEY` first configured)
- After updating `JEV_MODEL` or changing question text in any integration point
- Before promoting Jev to replace existing logic at any integration point
- Monthly as a health check — models update; scores can drift

## Run

```bash
# Full benchmark (requires JEV_API_KEY)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && JEV_API_KEY=<key> python3 .claude/skills/check-jev/scripts/check-jev.py

# With custom model
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && JEV_API_KEY=<key> JEV_MODEL=jev-preview python3 .claude/skills/check-jev/scripts/check-jev.py
```

## Checks

| # | Check | What it validates |
|---|-------|------------------|
| 1 | Connectivity | GET /v1/models — reachable, JEV_API_KEY valid, model present |
| 2 | noul governance | 3 benign + 3 malicious inputs — zero false positives, zero false negatives at threshold 0.70 |
| 3 | choice routing | 5 arch descriptions → expected mode (brain_fast/api_only/full_moe) |
| 4 | choice adapter | 3 known formats (MMD, Terraform, prose) → correct adapter name |
| 5 | Circuit breaker | 3 failures with invalid key → circuit opens; 4th call returns {} instantly |
| 6 | TATB Brier | Optional — compares Jev Brier to naive 0.5 baseline on hold-out instances |

## RECOMMEND output

| Output | Meaning |
|--------|---------|
| `RECOMMEND: ENABLE` | All checks pass — use Jev across all integration points |
| `RECOMMEND: ENABLE with monitoring` | Core checks pass (governance + routing); other checks degraded |
| `RECOMMEND: DISABLE or INVESTIGATE` | Core checks failing — keep `JEV_ENABLED=0` until resolved |

## Fallback behaviour (JEV_ENABLED=0 or offline)

Every integration point is non-fatal. If Jev is unreachable:
- governance pre-flight: regex scan runs unchanged; no `jev_preflight` key in signals
- smart router: falls back to `no_boxing_data_default` from `model_routing.yaml`
- PolicyBroker: existing rules only; no critic blocks from Jev
- adapter registry: existing `can_handle()` logic; raises `ValueError` on no match
- TATB labeller: returns neutral 0.5 for all dims

## Disable Jev globally

```bash
export JEV_ENABLED=0    # disables all integration points for the session
```

## Integration points implemented

1. **TATB labeller** — `chatbot/modules/ta_brain_jev_labeller.py` uses `JevClient`
2. **Smart router cold-start** — `chatbot/harness/smart_router.py:select_mode()` cold path
3. **Governance pre-flight** — `chatbot/harness/governance.py:GovernanceAdaptor.check_input()`
4. **PolicyBroker critic pre-screen** — `chatbot/harness/policy_broker.py:PolicyBroker.decide()`
5. **Adapter selection fallback** — `chatbot/adapters/registry.py:detect_adapter()`

All use `chatbot/modules/jev_client.py:get_jev_client()` (session singleton with circuit breaker).

## Blog reference

Part 31 candidate: "Three types, five integration points, one System 1 model"
- noul for governance: semantic intent detection vs regex pattern matching
- choice for routing: calibrated probability vs static lookup table
- noul for critic gating: Jev confidence replaces heuristic thresholds
