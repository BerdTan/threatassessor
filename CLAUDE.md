# ThreatAssessor — Developer Quick Reference

**Version:** 3.0  
**Core:** `.mmd` / repo / IaC → threat model + MITRE ATT&CK + MoE review + 70 SOC DETECT rules + AIVSS + MCP (18 tools) + ta-export/1.0 + TA Brain (181 instances, brain_fast/api_only/full_moe) + TA-SIP (TF/CF/OAI/Prose/MMD → ArchitectureGraph) + TAgym (instrument gym flywheel)

---

## Session Protocol

**Read at session start:** [`docs/DECISIONS.md`](docs/DECISIONS.md)

Add an entry after any significant architectural decision: date, what, why, alternatives rejected.

**Before any ⬜ priority item:** 30-second audit against [`docs/PRINCIPLES.md`](docs/PRINCIPLES.md) — ten governing principles. Flag any tension in the DECISIONS entry before coding. Guides, does not restrict.

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
- `chatbot/harness/smart_router.py` — `select_mode(arch_name)` → `RoutingDecision`; brain_fast / api_only / full_moe selection
- `chatbot/harness/rule_evaluator.py` — `RuleEvaluator` (70 DETECT rules)
- `chatbot/harness/spend_gate.py` — `check()` returns a verdict (`allow<steer<throttle<block<kill`, fail-closed); `SPEND_ROUTES` lists the 18 gated REST routes; `MODE_WEIGHT` (full_moe=5, a guess)
- `chatbot/harness/spend_ledger.py` — per-caller sliding-window requests/tokens (soft limits: `TM-CALLER` is self-asserted); `chatbot/harness/caller_context.py` — caller/session labels

**SOC detection:**
- `policies/soc_detection_rules.yaml` — 70 DETECT rules with OWASP/ATLAS/incident provenance

**REST API:**
- `chatbot/api/app.py` — FastAPI factory
- `chatbot/api/routes/reports.py` — report endpoints + `/detect-trend/{arch}` + `/governance/check` + `/reports/{arch}/export`
- `chatbot/api/routes/streaming.py` — SSE analysis stream
- `chatbot/api/routes/jobs.py` — `POST /jobs/expert-review` + `GET /jobs/{id}/status` (async job layer for MCP)
- `chatbot/api/static/` — dashboard (index.html + JS; nav: Overview/Assessment/Simulation/Platform/Reporting/Workspace/Settings)

**TA-SIP (Security Intelligence Platform):**
- `chatbot/adapters/` — `ArchitectureGraph` + adapters: TF/CF/OAI/Prose/MMD; `RepoCrawler` (MAX_FILES=200, dedup 0.85)
- `chatbot/api/routes/enrich.py` — `POST /api/v1/enrich`: fuzzy component→attack paths (<50ms, no LLM)
- `chatbot/api/routes/taclaw.py` — `POST /api/v1/taclaw/run` + `GET /api/v1/taclaw/jobs` (async crawl+assess)
- `chatbot/api/routes/gym.py` — `POST /api/v1/gym/start|status|stop`; `GymSession`/`GymIteration`; Brier snapshots per iteration
- `chatbot/schemas/ta_export_v1.json` — JSON Schema for ta-export/1.0; served at `GET /api/v1/schemas/ta-export`
- `taclaw/` — `ta`/`taclaw` CLI; `ta gate` exits 1 on BLOCK (CI); `ta gym start/status/stop`; publish on `taclaw-v*` tags

**MCP server:**
- `mcp_server/server.py` — FastMCP app, 18 tools (stdio transport); all tools log to `MCPAccessLogger`
- `mcp_server/client_sim.py` — 6-persona integration simulator (chatbot, code-agent, ciso, soc, copilot, chatgpt)
- `mcp_server/README.md` — setup, 4-step testing protocol, per-client integration snippets

**TA Brain:**
- `chatbot/modules/ta_brain_builder.py` — instance ingest + distiller + `HOLD_OUT_ARCHS` (8 archs)
- `chatbot/modules/ta_brain_benchmarks.py` — Brier calibration (precision-weighted, score over predicted only) + framework floors
- `chatbot/modules/ta_brain_query.py` — TACO query surface (infer/gaps/patterns/explain modes)
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

**Spend gate** (Entry 264): every token-spending route carries the `spend_gate` dependency (503 kill, 403 block, 429 throttle); it decides, the route refuses, Langfuse emit is separate. Per-caller limits are soft; MCP/CLI are not gate-verified. Detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**BouncerStage** halts the pipeline (`required=True`) when `exploitation.blocked=True`, `_outbound_blocked`, or `kill_switch` in `policies/agent_governance.yaml`. Raises `BlockedPipelineError` → API returns 400. It runs after Analysis, Report and Quality, so it does not stop analysis-stage spend; the spend gate does.

**PolicyBroker** runs after QualityStage on every pipeline run. Reads live governance signals → dynamically adjusts `blocked_agents` + model routing before critics run.

**AsyncThreatAssessorHarness** wraps `run_typed(PipelineRequest)` in `asyncio.to_thread()` for MCP/CI-CD callers.

**`GovernanceSignals` key fields:** `arch_metadata.is_agentic` (from `ground_truth.metadata`) · `aivss.delta.composite_drop` (computed vs prior history entry) · `mcp_access.*` (from `MCPAccessLogger`)

---

## MCP server — 18 tools

Full tool reference, sim personas (17), and client integration: [`mcp_server/README.md`](mcp_server/README.md).  
**Transport:** stdio (Claude Desktop standard). `mcp_server/server.py` — FastMCP app.

---

## Check commands

Full list in [`docs/CHECKS.md`](docs/CHECKS.md); each is also a skill. The ones used most:

```bash
/docs-health          # CLAUDE.md, DECISIONS.md, memory staleness (read-only)
/check-detect         # 70 DETECT rules regression (~15s, no API)
/tmeval               # adversarial probe; Phase 3 = spend gate (use PYTHONPATH=. .venv/bin/python)
/taprover             # claims vs ATT&CK; --prove-docs checks doc stage-order claims
/session-cleanup      # housekeeping: docs-health + repo-organise
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

**Last Updated:** 2026-11-22
