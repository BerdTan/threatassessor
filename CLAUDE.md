# ThreatAssessor — Developer Quick Reference

**Version:** 2.0  
**Status:** Production-ready. REST API + dashboard live. MoE critics + SOC detection layer + Harness v2 shipped.  
**Core:** `.mmd` architecture diagram → threat model + MITRE ATT&CK + MoE expert review + 19 SOC DETECT rules + AIVSS scoring

---

## Session Protocol

**Read at session start:** [`docs/DECISIONS.md`](docs/DECISIONS.md) (gitignored — local only)

Add an entry after any significant architectural decision: date, what, why, alternatives rejected.

---

## Start / Stop

```bash
./scripts/api/api_start.sh      # start API (http://localhost:8000/dashboard)
./scripts/api/api_status.sh     # check
./scripts/api/api_restart.sh    # restart
./scripts/api/api_stop.sh       # stop
tail -f logs/api.log            # logs
```

---

## Key Module Paths

**Analysis pipeline:**
- `chatbot/modules/ground_truth_generator.py` — main engine
- `chatbot/modules/threat_analyst.py` — RAPIDS + AI/ML
- `chatbot/modules/threat_report.py` — report generation
- `chatbot/modules/exhaustive_mitigation_mapper.py` — controls (100% coverage)
- `chatbot/modules/self_validation.py` — MITRE technique validation

**Harness (pipeline controller — v2):**
- `chatbot/harness/controller.py` — `ThreatAssessorHarness`, `PipelineRequest/Response`, `AsyncThreatAssessorHarness`, `BlockedPipelineError`, `CircuitBreaker`
- `chatbot/harness/stages.py` — `AnalysisStage`, `ReportStage`, `QualityStage`, `BouncerStage`(required=True), `CriticStage`, `ScrumMasterStage`, `AIVSSStage`
- `chatbot/harness/governance.py` — `GovernanceSignals`, governance adapter, injection/evasion detection
- `chatbot/harness/policy_broker.py` — `PolicyBroker`, `BrokerDecision` (dynamic routing after QualityStage)
- `chatbot/harness/event_broker.py` — `EventBrokerCritic`, pub/sub to SIEM/Langfuse/Webhook sinks
- `chatbot/harness/rule_evaluator.py` — `RuleEvaluator` (19 DETECT rules)
- `chatbot/harness/rule_trend_evaluator.py` — `RuleTrendEvaluator` (trend analysis from history JSONL)
- `chatbot/harness/registry.py` — `CriticRegistry`

**SOC detection:**
- `policies/soc_detection_rules.yaml` — 19 DETECT rules with OWASP/ATLAS/incident provenance
- `report/<arch>/governance_signals.json` — signal substrate for rule evaluation
- `report/<arch>/governance_signals_history.jsonl` — append-only run history for trend analysis
- `report/<arch>/ocsf_findings.json` — OCSF DetectionFinding 2004 export

**REST API:**
- `chatbot/api/app.py` — FastAPI factory
- `chatbot/api/routes/reports.py` — report endpoints + `/detect-trend/{arch}`
- `chatbot/api/routes/streaming.py` — SSE analysis stream
- `chatbot/api/static/` — dashboard (index.html + JS)

**MoE agents:**
- `chatbot/modules/agents/critics/` — Architect, Tester, Red Team, Purple Team, Blackhat
- `chatbot/modules/agents/orchestrators/` — MoEOrchestrator

**LLM client:**
- `agentic/llm_client.py` — OpenRouter + Bedrock (use this, not `agentic/llm.py`)

**Data (not in git):**
- `chatbot/data/enterprise-attack.json` (44 MB) — MITRE ATT&CK
- `chatbot/data/technique_embeddings.npz` (3 MB float16) — embeddings cache

---

## Harness v2 key concepts

**Stage order (API_ONLY):** Analysis → Report → Quality → **Bouncer** → AIVSS  
**Stage order (FULL_MOE):** Analysis → Report → Quality → **Bouncer** → Critics → SM → AIVSS → OutboundGate

**BouncerStage** halts the pipeline (`required=True`) when `exploitation.blocked=True`, `_outbound_blocked`, or `kill_switch` in `policies/agent_governance.yaml`. Raises `BlockedPipelineError` → API returns 400.

**PolicyBroker** runs after QualityStage on every pipeline run. Reads live governance signals → dynamically adjusts `blocked_agents` + model routing before critics run.

**AsyncThreatAssessorHarness** wraps `run_typed(PipelineRequest)` in `asyncio.to_thread()` for MCP/CI-CD callers.

---

## Check commands

```bash
# SOC detection regression (19 rules, 20 scenarios, 296 tests)
python3 .claude/skills/check-detect/scripts/check-detect.py
python3 .claude/skills/check-detect/scripts/check-detect.py --all   # + live corpus

# Governance guardrails (56 tests)
python3 .claude/skills/check-governance/scripts/check-governance.py

# EventBroker + sinks (60 tests)
python3 .claude/skills/check-eventbroker/scripts/check-eventbroker.py

# DETECT coverage flywheel
python3 .claude/skills/detect-loop/scripts/detect-loop.py --observe-only

# Rule trend analysis
python3 .claude/skills/detect-trend/scripts/detect-trend.py --all
```

---

## What NOT to commit

```
report/                  # generated reports (gitignored)
chatbot/data/*.json      # large data files
chatbot/data/*.npz       # embeddings
.env                     # API keys
docs/DECISIONS.md        # gitignored — local architectural log
docs/blog/               # gitignored — blog drafts
_codex/ archive/         # experimental / historical
```

**DO commit:** `tests/data/architectures/*.mmd`, `docs/` (except DECISIONS.md + blog/), `.claude/skills/`, `policies/`, `openapi.yaml`

---

## Troubleshooting

```bash
python3 scripts/validation/check_orphans.py <arch>        # orphan nodes
python3 -m chatbot.modules.completeness_validator <arch>  # validation
cat report/<arch>/ground_truth.json                        # raw output
```

---

**Last Updated:** 2026-08-01
