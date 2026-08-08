# ThreatAssessor Documentation

**Version:** 2.2 — Harness v2 shipped, 24 SOC DETECT rules, MCP server (13 tools) + connector package  
**Last Updated:** 2026-08-08

---

## Quick Navigation

| If you want to… | Go to |
|---|---|
| Start a dev session | [CLAUDE.md](../CLAUDE.md) (root) |
| Understand architecture decisions | [DECISIONS.md](DECISIONS.md) (gitignored, local) |
| Harness v2 implementation | [HARNESS_V2_DESIGN.md](HARNESS_V2_DESIGN.md) |
| Run the API server | [operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) |
| Troubleshoot issues | [operations/OPERATIONS.md](operations/OPERATIONS.md) |
| TATB benchmark rubric | [TATB_RUBRIC.md](TATB_RUBRIC.md) |

---

## Active Documentation

### Root (this directory)

| File | Purpose |
|---|---|
| [DECISIONS.md](DECISIONS.md) | Architectural decision log — read at session start (gitignored) |
| [HARNESS_V2_DESIGN.md](HARNESS_V2_DESIGN.md) | Harness v2 Orchestrator/Broker/Bouncer — implemented; two items deferred |
| [TATB_RUBRIC.md](TATB_RUBRIC.md) | TATB benchmark rubric (Threat/TTP/Risk/Plan) |

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
| [../mcp_server/README.md](../mcp_server/README.md) | MCP server setup, 4-step testing protocol, 13 tools reference |
| [../mcp_connector/README.md](../mcp_connector/README.md) | Connector package — Claude Desktop, OpenAI, LangChain, n8n integration patterns |
| [../openapi.yaml](../openapi.yaml) | OpenAPI 3.1 spec — 47 paths, importable by n8n / LangChain / Zapier |

### Dashboard

| File | Purpose |
|---|---|
| [ui/DASHBOARD_GUIDE.md](ui/DASHBOARD_GUIDE.md) | Dashboard user guide |

### Blog

| File | Purpose |
|---|---|
| [blog/](blog/) | Medium draft series — Parts 1–15 published. `draft_latest.md` = most recent. |

---

## Archive

Superseded docs (core/, development/, testing/, deployment/, api/, phases/, old blog drafts) are in [archive/](archive/). Nothing in `archive/` needs to be read during normal development.

---
