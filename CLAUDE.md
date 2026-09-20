# ThreatAssessor — Developer Quick Reference

**Version:** 2.9  
**Core:** `.mmd` / repo / IaC → threat model + MITRE ATT&CK + MoE review + 40 SOC DETECT rules + AIVSS + MCP (18 tools) + ta-export/1.0 + TA Brain (181 instances, brain_fast/api_only/full_moe) + TA-SIP (TF/CF/OAI/Prose/MMD → ArchitectureGraph)

---

## Session Protocol

**Read at session start:** [`docs/DECISIONS.md`](docs/DECISIONS.md)

Add an entry after any significant architectural decision: date, what, why, alternatives rejected.

---

## GitHub Actions CI

**Workflow:** `.github/workflows/ta-review.yml` — triggers on `**/*.mmd` PR changes.  
**Flow:** governance_check → analyze-stream → export gate → PR comment + request_changes on BLOCK  
**Secrets:** `TA_API_KEY`, `OPENROUTER_API_KEY` (optional for deterministic-only)  
**Local test:** `TA_API_URL=http://localhost:8000 TA_API_KEY=<key> BASE_REF=master python3 scripts/ci/ta_pr_review.py`

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
- `chatbot/modules/agents/analysts/threat_analyst.py` — RAPIDS + AI/ML
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
- `chatbot/harness/sinks.py` — `SiemSink`, `LangfuseSink`, `WebhookSink`; routing_mode tag preservation across trace.update() calls
- `chatbot/harness/smart_router.py` — `select_mode(arch_name)` → `RoutingDecision`; brain_fast / api_only / full_moe selection
- `chatbot/harness/rule_evaluator.py` — `RuleEvaluator` (40 DETECT rules)
- `chatbot/harness/rule_trend_evaluator.py` — `RuleTrendEvaluator` (trend analysis from history JSONL)
- `chatbot/harness/registry.py` — `CriticRegistry`

**SOC detection:**
- `policies/soc_detection_rules.yaml` — 40 DETECT rules with OWASP/ATLAS/incident provenance

**REST API:**
- `chatbot/api/app.py` — FastAPI factory
- `chatbot/api/routes/reports.py` — report endpoints + `/detect-trend/{arch}` + `/governance/check` + `/reports/{arch}/export`
- `chatbot/api/routes/streaming.py` — SSE analysis stream
- `chatbot/api/routes/jobs.py` — `POST /jobs/expert-review` + `GET /jobs/{id}/status` (async job layer for MCP)
- `chatbot/api/routes/mcp_sim.py` — SSE sim stream + personas endpoint + access-signals + jobs snapshot
- `chatbot/api/job_store.py` — in-memory job store, 1-hr TTL, `get_job_store()` singleton; `list_all()` for SIP jobs panel
- `chatbot/api/static/` — dashboard (index.html + JS; nav: Overview/Assessment/Simulation/Platform/Reporting/Workspace/Settings)

**TA-SIP (Security Intelligence Platform):**
- `chatbot/adapters/` — `ArchitectureGraph` + adapters: TF/CF/OAI/Prose/MMD; `RepoCrawler` (MAX_FILES=200, dedup 0.85)
- `chatbot/api/routes/enrich.py` — `POST /api/v1/enrich`: fuzzy component→attack paths (<50ms, no LLM)
- `chatbot/api/routes/artifact.py` — `POST /api/v1/analyze/artifact`: file upload → adapter → SSE stream
- `chatbot/api/routes/taclaw.py` — `POST /api/v1/taclaw/run` + `GET /api/v1/taclaw/jobs` (async crawl+assess)
- `chatbot/api/routes/platform.py` — `GET /api/v1/adapters` + `GET /api/v1/sip/health`
- `chatbot/schemas/ta_export_v1.json` — JSON Schema for ta-export/1.0; served at `GET /api/v1/schemas/ta-export`
- `mcp_connector/` — `threatassessor-mcp` v1.1.0; typed `TAExportBundle`, `ComponentContext`; `enrich_finding()`
- `taclaw/` — `ta`/`taclaw` CLI; `ta gate` exits 1 on BLOCK (CI); publish on `taclaw-v*` tags

**MCP server:**
- `mcp_server/server.py` — FastMCP app, 18 tools (stdio transport); all tools log to `MCPAccessLogger`
- `mcp_server/job_client.py` — HTTP wrapper for all REST calls
- `mcp_server/access_logger.py` — `MCPAccessLogger` rolling-window singleton; produces `mcp_access` signals for DETECT-MCP-001/021/022
- `mcp_server/client_sim.py` — 6-persona integration simulator (chatbot, code-agent, ciso, soc, copilot, chatgpt)
- `mcp_server/README.md` — setup, 4-step testing protocol, per-client integration snippets

**TA Brain:**
- `chatbot/modules/ta_brain_builder.py` — instance ingest + distiller + `HOLD_OUT_ARCHS` (8 archs)
- `chatbot/modules/ta_brain_benchmarks.py` — Brier calibration (precision-weighted, score over predicted only) + framework floors
- `chatbot/modules/ta_brain_mmd_generator.py` — Gap→MMD generator (Stage 8); synthetic queue in `report/brain/synthetic_queue/`
- `chatbot/modules/ta_brain_query.py` — TACO query surface (infer/gaps/patterns/explain modes)
- `chatbot/modules/ta_brain_taco_processor.py` — idempotent feedback processor (Stage 7)
- `chatbot/api/routes/brain.py` — all `/api/v1/brain/*` endpoints
- `report/brain/ta_brain.json` — pattern layer + meta layer (`pattern_version` key drives cache invalidation)
- `report/brain/ta_brain_instances.jsonl` — append-only instance layer (use `incremental=True` to avoid duplicates)
- `report/brain/synthetic_queue/` — staged synthetic MMDs awaiting approval before harness submission

**LLM client:**
- `agentic/llm_client.py` — OpenRouter + Bedrock (use this, not `agentic/llm.py`)

---

## Harness v2 key concepts

**Stage order (API_ONLY):** Analysis → Report → Quality → **Bouncer** → AIVSS  
**Stage order (FULL_MOE):** Analysis → Report → Quality → **Bouncer** → Critics → SM → AIVSS → OutboundGate

**BouncerStage** halts the pipeline (`required=True`) when `exploitation.blocked=True`, `_outbound_blocked`, or `kill_switch` in `policies/agent_governance.yaml`. Raises `BlockedPipelineError` → API returns 400.

**PolicyBroker** runs after QualityStage on every pipeline run. Reads live governance signals → dynamically adjusts `blocked_agents` + model routing before critics run.

**AsyncThreatAssessorHarness** wraps `run_typed(PipelineRequest)` in `asyncio.to_thread()` for MCP/CI-CD callers.

**`GovernanceSignals` key fields:** `arch_metadata.is_agentic` (from `ground_truth.metadata`) · `aivss.delta.composite_drop` (computed vs prior history entry) · `mcp_access.*` (from `MCPAccessLogger`)

---

## MCP server — 18 tools

Full tool reference, sim personas (17), and client integration: [`mcp_server/README.md`](mcp_server/README.md).  
**Transport:** stdio (Claude Desktop standard). `mcp_server/server.py` — FastMCP app.

---

## Check commands

```bash
# ── Session start ────────────────────────────────────────────────────────────
# Docs health — CLAUDE.md, DECISIONS.md, memory staleness (read-only, no API)
/docs-health

# ── Pipeline / gate ──────────────────────────────────────────────────────────
# AIVSS gate config + HarnessModelGuardian model assignments + last SIEM scores
/aivss-gate

# ── SOC detection ────────────────────────────────────────────────────────────
# Regression suite (40 rules, 43 scenarios)
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

# ── MCP / connector ──────────────────────────────────────────────────────────
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

# ── SIP platform ──────────────────────────────────────────────────────────────
# Adapter registry, endpoints, TAclaw, CLI (15 static + 7 live)
python3 .claude/skills/check-sip/scripts/check-sip.py
python3 .claude/skills/check-sip/scripts/check-sip.py --live  # + REST API checks
```

---

## Occasional checks

```bash
/session-cleanup      # master housekeeping: docs-health + repo-organise in one pass
/health-audit         # structural health: orphaned routes/adapters, DETECT coverage gaps, env-var drift
/check-skills         # supply-chain + phishing audit of .claude/skills/ corpus
/check-deprecation    # broken imports + anti-patterns — run after heavy refactoring
/skill-stress-test    # red-team a skill before finalising — pass skill name as arg
/langfuse-to-ocsf     # pipeline traces → OCSF events — requires LANGFUSE_* env vars
/repo-organise        # audit docs/tests/scripts/report — proposes, never auto-executes
/cost-estimate        # investment tier costs vs CIS/NIST/Gartner benchmarks
```

---

## What NOT to commit

```
report/                  # generated reports (gitignored)
chatbot/data/*.json      # large data files
chatbot/data/*.npz       # embeddings
.env                     # API keys
docs/blog/               # gitignored — blog drafts
_codex/ archive/         # experimental / historical
```

**DO commit:** `tests/data/architectures/*.mmd`, `docs/` (except blog/), `.claude/skills/`, `policies/`, `openapi.yaml`

---

## Troubleshooting

```bash
python3 scripts/validation/check_orphans.py <arch>        # orphan nodes
python3 -m chatbot.modules.completeness_validator <arch>  # validation
cat report/<arch>/ground_truth.json                        # raw output
```

---

**Last Updated:** 2026-09-20
