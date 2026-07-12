---
name: check-eventbroker
description: Run the EventBroker + Sink regression suite (48 tests, ~9s, no LLM/network). Covers HarnessEvent, EventBrokerCritic fan-out and isolation, BaseSink subscription filtering, SiemSink file-write + schema translation, LangfuseSink credential resolution + event-to-call mapping for all 7 event types, WebhookSink POST, and multi-sink integration. Optionally check live broker status and last SIEM events for one or all corpus architectures. Use after any change to chatbot/harness/event_broker.py or chatbot/harness/sinks.py.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# check-eventbroker — EventBroker Regression + Live Status

Runs the full EventBroker test suite without LLM calls or network access.
Covers all three sinks (SIEM, Langfuse, Webhook) and the broker fan-out layer.

## Run

```bash
# Full regression suite (~9s, no LLM, no network)
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/check-eventbroker/scripts/check-eventbroker.py

# Live broker status — config + last SIEM events for one architecture
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/check-eventbroker/scripts/check-eventbroker.py 21_agentic_ai_system

# Live broker status for all corpus architectures
cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate \
  && python3 .claude/skills/check-eventbroker/scripts/check-eventbroker.py --all
```

## What it tests

### Unit tests (always run)

| Test class | Coverage |
|---|---|
| `TestHarnessEvent` | to_dict round-trip, all 7 event types, default payload |
| `TestEventBrokerInit` | Policy loading, settings override, SiemSink registration |
| `TestEventBrokerEmit` | Fan-out to all sinks, disabled guard, per-sink failure isolation |
| `TestBaseSinkFiltering` | All 4 preset names (stage_trace, critic_trace, governance, aivss) |
| `TestSiemSink` | JSONL write, aivss_gate→SiemEvent schema, subscription filter, webhook |
| `TestLangfuseSink` | Credential resolution (config > env > default), all 7 event→Langfuse call mappings |
| `TestWebhookSink` | POST body shape, no-URL guard, failure isolation |
| `TestMultiSinkIntegration` | SiemSink (real file) + mock Langfuse + mock Webhook fan-out |

### Live status check (when arch or --all passed)

For each architecture, reads `governance_signals.json` and `logs/siem.jsonl`:

- Broker config: enabled flag, verbosity, which sinks are active
- Last N SIEM events from `logs/siem.jsonl` (most recent 5)
- Whether Langfuse is reachable (if enabled)

## Output example

```
EventBroker Regression — tests/test_harness_event_broker.py
  48 passed  0 failed   (8.8s)

Live Broker Status — 21_agentic_ai_system
  broker:   enabled  verbosity=standard
  siem:     enabled  → logs/siem.jsonl
  langfuse: disabled
  webhook:  disabled

  Last SIEM events (siem.jsonl):
    [2026-07-13T10:00:00Z] governance_complete  overall_risk=MEDIUM
    [2026-07-13T09:59:55Z] aivss_gate           severity=LOW  blocked=False
```

## When to run

- After any change to `chatbot/harness/event_broker.py`
- After any change to `chatbot/harness/sinks.py`
- When troubleshooting missing SIEM events or Langfuse traces
- After enabling/disabling sinks in `policies/agent_governance.yaml`

## End-to-end verification (ED)

To verify the full event pipeline end-to-end (broker → sinks → Langfuse):

```bash
# 1. Enable SIEM sink (already on by default) and run an analysis
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/01_minimal_vulnerable.mmd

# 2. Check SIEM output
tail -5 logs/siem.jsonl | python3 -m json.tool

# 3. For Langfuse end-to-end (requires Langfuse running):
#    a. Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY in .env
#    b. Set event_broker.sinks.langfuse.enabled: true in policies/agent_governance.yaml
#    c. Run analysis and check traces in Langfuse UI at http://localhost:3000
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/01_minimal_vulnerable.mmd
# Then open http://localhost:3000 → Traces tab

# 4. Run this skill to confirm no regressions
python3 .claude/skills/check-eventbroker/scripts/check-eventbroker.py
```

## Related skills

- `/check-governance` — governance guardrail regression (D1-D5 signals)
- `/aivss-gate` — show AIVSS gate thresholds and last SIEM event summary
- `/quick-test` — broader integration sanity (API key, MITRE data, embeddings)
