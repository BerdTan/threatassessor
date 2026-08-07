# ThreatAssessor — Developer Quick Reference

**Version:** 2.2  
**Status:** Production-ready. REST API + dashboard live. MoE critics + SOC detection layer (24 rules) + Harness v2 + MCP server (13 tools) + TA export bundle shipped.  
**Core:** `.mmd` architecture diagram → threat model + MITRE ATT&CK + MoE expert review + 24 SOC DETECT rules + AIVSS scoring + MCP external access + ta-export/1.0

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
- `chatbot/modules/ta_exporter.py` — TA export bundle (`ta-export/1.0`): gate + assessment + TATB + governance + MoE + OCSF + OTM

**Harness (pipeline controller — v2):**
- `chatbot/harness/controller.py` — `ThreatAssessorHarness`, `PipelineRequest/Response`, `AsyncThreatAssessorHarness`, `BlockedPipelineError`, `CircuitBreaker`
- `chatbot/harness/stages.py` — `AnalysisStage`, `ReportStage`, `QualityStage`, `BouncerStage`(required=True), `CriticStage`, `ScrumMasterStage`, `AIVSSStage`
- `chatbot/harness/governance.py` — `GovernanceSignals`, governance adapter, injection/evasion detection
- `chatbot/harness/policy_broker.py` — `PolicyBroker`, `BrokerDecision` (dynamic routing after QualityStage)
- `chatbot/harness/event_broker.py` — `EventBrokerCritic`, pub/sub to SIEM/Langfuse/Webhook sinks
- `chatbot/harness/rule_evaluator.py` — `RuleEvaluator` (24 DETECT rules)
- `chatbot/harness/rule_trend_evaluator.py` — `RuleTrendEvaluator` (trend analysis from history JSONL)
- `chatbot/harness/registry.py` — `CriticRegistry`

**SOC detection:**
- `policies/soc_detection_rules.yaml` — 24 DETECT rules with OWASP/ATLAS/incident provenance
- `report/<arch>/governance_signals.json` — signal substrate for rule evaluation (includes `arch_metadata`, `aivss.delta`)
- `report/<arch>/governance_signals_history.jsonl` — append-only run history; AIVSS delta computed on each append
- `report/<arch>/ocsf_findings.json` — OCSF DetectionFinding 2004 export
- `report/<arch>/ta_export.json` — TA export bundle (written by `save=true` on `/export` endpoint)

**REST API:**
- `chatbot/api/app.py` — FastAPI factory
- `chatbot/api/routes/reports.py` — report endpoints + `/detect-trend/{arch}` + `/governance/check` + `/reports/{arch}/export`
- `chatbot/api/routes/streaming.py` — SSE analysis stream
- `chatbot/api/routes/jobs.py` — `POST /jobs/expert-review` + `GET /jobs/{id}/status` (async job layer for MCP)
- `chatbot/api/routes/mcp_sim.py` — SSE sim stream + personas endpoint + access-signals + jobs snapshot
- `chatbot/api/job_store.py` — in-memory job store, 1-hr TTL, `get_job_store()` singleton
- `chatbot/api/static/` — dashboard (index.html + JS; nav: Overview/Assessment/Simulation/Reporting/Workspace/Settings)

**MCP server:**
- `mcp_server/server.py` — FastMCP app, 13 tools (stdio transport); all tools log to `MCPAccessLogger`
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

**`GovernanceSignals` key fields:** `arch_metadata.is_agentic` (from `ground_truth.metadata`) · `aivss.delta.composite_drop` (computed vs prior history entry) · `mcp_access.*` (from `MCPAccessLogger`)

---

## MCP server — 13 tools

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
| `export_assessment` | Unified TA bundle (ta-export/1.0): gate + OTM + OCSF + TATB |
| `governance_check` | Fast MMD governance scan (~50ms, no LLM) → signals + fired DETECT rules |

**Transport:** stdio (Claude Desktop standard). See `mcp_server/README.md` for setup + all client types.

**Sim personas — 13 total:** 6 benign (chatbot/code-agent/ciso/soc/copilot/chatgpt) + 7 adversarial: `recon_attack` (020), `flood_attack` (021), `auth_probe` (022), `injection_attack` (005/010/019), `tag_injection` (005 CRITICAL), `url_injection` (017/018/019), `c2_exfil_arch` (020/019). Run via dashboard MCP tab or `GET /api/v1/mcp/simulate/{persona}`.

---

## Check commands

```bash
# SOC detection regression (24 rules, 25 scenarios, 327 tests)
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

# MCP server — static validation (40 checks, no API needed)
python3 .claude/skills/check-mcp/scripts/check-mcp.py
python3 .claude/skills/check-mcp/scripts/check-mcp.py --live  # + live REST + MCP stdio

# MCP client simulator — integration persona testing (API must be running)
python3 mcp_server/client_sim.py --dry-run             # protocol handshake only
python3 mcp_server/client_sim.py --all --arch <arch>   # all 6 benign personas live
python3 mcp_server/client_sim.py --persona soc --arch <arch>

# Connector layer (mcp_connector package + openapi.yaml + transport flag)
python3 .claude/skills/check-connector/scripts/check-connector.py          # static + live
python3 .claude/skills/check-connector/scripts/check-connector.py --static # no API needed
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

**Last Updated:** 2026-08-07
