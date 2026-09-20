# ThreatAssessor Documentation

**Version:** 2.9 — Harness v2 + 40 SOC DETECT rules + MCP server (18 tools) + TA-SIP + TA Brain Stages 1–9 + smart routing + N-model bench + Engine Items 6–10 + adapter fidelity (Engine Item 7)  
**Last Updated:** 2026-09-20

---

## Quick Navigation

| If you want to… | Go to |
|---|---|
| Start a dev session | [CLAUDE.md](../CLAUDE.md) (root) |
| Understand the system structure | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Understand architecture decisions | [DECISIONS.md](DECISIONS.md) |
| Harness v2 implementation | [HARNESS.md](HARNESS.md) |
| TAclaw hardening + test suite plan | [TACLAW.md](TACLAW.md) |
| Run the API server | [operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) |
| Troubleshoot issues | [operations/OPERATIONS.md](operations/OPERATIONS.md) |
| TATB benchmark rubric | [TATB.md](TATB.md) |

---

## Active Documentation

### Root (this directory)

| File | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System structure — 13 layers, execution paths, design invariants, component diagram |
| [DECISIONS.md](DECISIONS.md) | Architectural decision log — read at session start |
| [HARNESS.md](HARNESS.md) | Harness v2 Orchestrator/Broker/Bouncer — implemented; Engine Items 6–10 extensions |
| [TATB.md](TATB.md) | TATB benchmark rubric (Threat/TTP/Risk/Plan); brain_fast coverage notes |
| [TACLAW.md](TACLAW.md) | TAclaw hardening + test suite MVP — export completeness, smart routing, agent passport, eval scorecard |

### Operations

| File | Purpose |
|---|---|
| [operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) | Start/stop/restart API, health checks |
| [operations/OPERATIONS.md](operations/OPERATIONS.md) | Troubleshooting common issues |
| [operations/ARCHITECTURE_VALIDATION.md](operations/ARCHITECTURE_VALIDATION.md) | Orphan node detection workflow |
| [operations/API_LIFECYCLE.md](operations/API_LIFECYCLE.md) | API process lifecycle |
| [operations/API_KEY_SETUP.md](operations/API_KEY_SETUP.md) | API key configuration |
| [operations/CACHE_BUSTING.md](operations/CACHE_BUSTING.md) | MITRE cache management |

### AI Pattern

| File | Purpose |
|---|---|
| [patterns/README.md](patterns/README.md) | AI/ML pattern system overview (ARC + ATLAS) |
| [patterns/AI_PATTERN_STATUS.md](patterns/AI_PATTERN_STATUS.md) | ARC + ATLAS implementation status |
| [patterns/AI_PATTERN_VERIFICATION.md](patterns/AI_PATTERN_VERIFICATION.md) | Pattern verification results |

### SSP

| File | Purpose |
|---|---|
| [ssp/cyber.md](ssp/cyber.md) | Singapore Government ICT&SS SSP reference notes |

### MCP and Connector

| File | Purpose |
|---|---|
| [../mcp_server/README.md](../mcp_server/README.md) | MCP server setup, 4-step testing protocol, 18 tools reference |
| [../mcp_connector/README.md](../mcp_connector/README.md) | Connector package — Claude Desktop, OpenAI, LangChain, n8n integration patterns |
| [../openapi.yaml](../openapi.yaml) | OpenAPI 3.1 spec — 72 paths, importable by n8n / LangChain / Zapier |

### TAclaw — External Agent Interface

TAclaw is the external-facing agent interface to the TA engine. External developers, CI pipelines, and MCP-enabled coding agents (Claude Desktop, Cursor, Copilot) use it to submit repos or IaC for autonomous threat assessment.

| Resource | Purpose |
|---|---|
| [TACLAW.md](TACLAW.md) | Full hardening plan: export completeness, smart routing, agent passport, test suite MVP with eval |
| [../taclaw_cli/README.md](../taclaw_cli/README.md) | CLI install + usage — `ta analyze`, `ta gate`, `ta export` |
| [../mcp_connector/README.md](../mcp_connector/README.md) | MCP connector — `run_taclaw` tool, typed `TAExportBundle` |
| `POST /api/v1/taclaw/run` | REST endpoint — async job; poll `GET /api/v1/taclaw/jobs` |
| `taclaw_cli/tests/run_suite.py` | Test suite MVP — structural + quality + regression eval; `--smoke` for quick check |

**TAclaw pipeline (current):** `git_url / directory → RepoCrawler (MAX_FILES=200) → adapters (TF/CF/OAI/MMD/Prose) → merge_graphs → to_mmd() → ThreatAssessorHarness → build_export → brain ingest`

**Adapter coverage:** Terraform (.tf, plan.json) · CloudFormation (YAML/JSON/SAM/CDK) · OpenAPI / AsyncAPI · Mermaid (.mmd) · Prose (.md/.txt/.pdf/.docx)  
**Not covered yet:** Kubernetes YAML · Docker Compose · Bicep · ARM · Ansible

### Dashboard

| File | Purpose |
|---|---|
| [ui/DASHBOARD_GUIDE.md](ui/DASHBOARD_GUIDE.md) | Dashboard user guide |

---

## Key Design Decisions

Critical architectural choices are logged in [DECISIONS.md](DECISIONS.md). Entries are prepended (newest first). Key entries by topic:

| Topic | Entry range |
|---|---|
| Engine Items 6–10 (integrity gate, critic isolation, adapter fidelity, routing spans, source trust) | 174–179, 185–186 |
| SOC DETECT rules (40 rules, domain renumbering QC/INJ/EXF/SCT/MCP/RES) | 158–162, 174 |
| TA Brain + TACO (Stages 1–9, TACO Phase 1–4, Brier calibration) | 139–154 |
| Smart routing (select_mode, D5 gate, boxing framework) | 146–156 |
| TA-SIP platform (adapters, enrichment API, TAclaw, mcp_connector) | 139–145 |
| Harness v2 (Bouncer, PolicyBroker, EventBroker, circuit breaker) | 100–120 |
| MCP server 18 tools + async job layer | 125–135 |

---

## Archive

Superseded docs (core/, development/, testing/, deployment/, api/, phases/, old blog drafts) are in [archive/](archive/). Nothing in `archive/` needs to be read during normal development.

---
