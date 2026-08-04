# ThreatAssessor — Developer Quick Reference

**Version:** 2.1  
**Status:** Production-ready. REST API + dashboard live. MoE critics + SOC detection layer (22 rules) + Harness v2 + MCP server shipped.  
**Core:** `.mmd` architecture diagram → threat model + MITRE ATT&CK + MoE expert review + 22 SOC DETECT rules + AIVSS scoring + MCP external access

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
- `chatbot/harness/rule_evaluator.py` — `RuleEvaluator` (22 DETECT rules)
- `chatbot/harness/rule_trend_evaluator.py` — `RuleTrendEvaluator` (trend analysis from history JSONL)
- `chatbot/harness/registry.py` — `CriticRegistry`

**SOC detection:**
- `policies/soc_detection_rules.yaml` — 22 DETECT rules with OWASP/ATLAS/incident provenance
- `report/<arch>/governance_signals.json` — signal substrate for rule evaluation
- `report/<arch>/governance_signals_history.jsonl` — append-only run history for trend analysis
- `report/<arch>/ocsf_findings.json` — OCSF DetectionFinding 2004 export

**REST API:**
- `chatbot/api/app.py` — FastAPI factory
- `chatbot/api/routes/reports.py` — report endpoints + `/detect-trend/{arch}`
- `chatbot/api/routes/streaming.py` — SSE analysis stream
- `chatbot/api/routes/jobs.py` — `POST /jobs/expert-review` + `GET /jobs/{id}/status` (async job layer for MCP)
- `chatbot/api/job_store.py` — in-memory job store, 1-hr TTL, `get_job_store()` singleton
- `chatbot/api/static/` — dashboard (index.html + JS)

**MCP server:**
- `mcp_server/server.py` — FastMCP app, 11 tools (stdio transport); all tools log to `MCPAccessLogger`
- `mcp_server/job_client.py` — HTTP wrapper for all REST calls
- `mcp_server/access_logger.py` — `MCPAccessLogger` rolling-window singleton; produces `mcp_access` signals for DETECT-020/021/022
- `mcp_server/client_sim.py` — 6-persona integration simulator (chatbot, code-agent, ciso, soc, copilot, chatgpt)
- `mcp_server/README.md` — setup, 4-step testing protocol, per-client integration snippets

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

## MCP server — 11 tools

| Tool | What it does |
|------|-------------|
| `analyze_architecture` | Submit `.mmd` diagram → full threat model + MITRE TTPs (~30s sync) |
| `run_expert_review` | Queue FULL_MOE (5 critics + SM) → `job_id` (async) |
| `get_job_status` | Poll job; `wait_for_completion=True` to block until done |
| `get_threat_briefing` | CISO briefing (md or json) for a known architecture |
| `get_ciso_brief` | Full CISO brief with investment tiers + multi-critic findings |
| `get_governance_signals` | AIVSS composite + per-dimension signals |
| `get_detect_trends` | SOC DETECT rule firing trends (new/rising/stable/falling/never) |
| `get_tatb_scores` | TATB benchmark scores across corpus or single arch |
| `list_architectures` | All analysed architectures + metadata |
| `lookup_mitre_technique` | Technique details + recommended mitigations by ATT&CK ID |
| `get_mcp_access_signals` | Live session access patterns → feeds DETECT-020/021/022 |

**Transport:** stdio (Claude Desktop standard). See `mcp_server/README.md` for setup + all client types.

**MCP access DETECT rules (020–022):**

| Rule | Signal | Trigger | Severity |
|------|--------|---------|---------|
| DETECT-020 | `mcp_access.recon_sequence` | `list_architectures` + ≥3 `get_governance_signals` in 60s | Medium |
| DETECT-021 | `mcp_access.job_flood` | ≥3 `run_expert_review` in 120s, poll/submit < 0.5 | High |
| DETECT-022 | `mcp_access.auth_failures` | ≥5 auth failures in 300s | High |

---

## Check commands

```bash
# SOC detection regression (22 rules, 23 scenarios, 191 tests)
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

# MCP server — static validation (30 checks, no API needed)
python3 .claude/skills/check-mcp/scripts/check-mcp.py
python3 .claude/skills/check-mcp/scripts/check-mcp.py --live  # + live REST + MCP stdio

# MCP client simulator — integration persona testing (API must be running)
python3 mcp_server/client_sim.py --dry-run             # protocol handshake only
python3 mcp_server/client_sim.py --all --arch web_app  # all 6 personas live
python3 mcp_server/client_sim.py --persona soc --arch web_app
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

**Last Updated:** 2026-08-04
