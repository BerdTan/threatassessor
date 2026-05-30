# Project Documentation Structure

**Version:** 1.4  
**Last Updated:** 2026-05-30

Navigation map for the ThreatAssessor documentation. All docs are Markdown — no generated HTML files.

---

## Quick Links

| I want to… | File |
|---|---|
| Get started fast | [START_HERE.md](START_HERE.md) |
| Read architectural decisions | [DECISIONS.md](DECISIONS.md) |
| Check current status + roadmap | [STATUS_AND_PLAN.md](STATUS_AND_PLAN.md) |
| Understand the MoE agent design | [AGENTIC_DESIGN.md](AGENTIC_DESIGN.md) |
| Developer quick reference | [../CLAUDE.md](../CLAUDE.md) |
| Run / operate the API | [operations/API_MANAGEMENT.md](operations/API_MANAGEMENT.md) |
| Troubleshoot | [operations/OPERATIONS.md](operations/OPERATIONS.md) |
| Browse all active docs | [README.md](README.md) |

---

## Repository Layout

```
/                                  ← Repo root
├── README.md                      ← User quick start (features, API, quick start)
├── CLAUDE.md                      ← Developer quick reference (commands, module paths)
├── openapi.yaml                   ← OpenAPI 3.0 machine-readable spec
├── Makefile                       ← make help for all targets
├── demo_deterministic_engine.sh   ← Fast CLI analysis (no LLM, ~30 s)
├── demo_expert_llm.sh             ← Full MoE pipeline CLI (~2 min)
│
├── chatbot/                       ← Application code
│   ├── api/                       ← FastAPI app, routes, models, static dashboard
│   ├── modules/                   ← Analysis engine, RAPIDS, MoE agents, SSP mapper
│   ├── services/                  ← Thread-safe service layer
│   └── data/                      ← ATLAS YAML, SSP catalog JSON, ARC YAML (in repo)
│                                     MITRE ATT&CK + embeddings (large, not in git)
│
├── agentic/                       ← Multi-provider LLM client (OpenRouter, Bedrock)
│
├── docs/                          ← Documentation (this directory)
│   ├── DECISIONS.md               ← ⭐ Read at session start
│   ├── STATUS_AND_PLAN.md         ← Current status and roadmap
│   ├── AGENTIC_DESIGN.md          ← MoE architecture, AgentTools, MCP design
│   ├── api/                       ← API specification and integration guides
│   ├── core/                      ← Confidence methodology, features, frameworks
│   ├── development/               ← Architecture, LLM client, migration guides
│   ├── operations/                ← API management, troubleshooting, validation
│   ├── patterns/                  ← AI/ML pattern (ARC + ATLAS) documentation
│   ├── phases/phase3d/            ← MoE implementation reference (complete)
│   ├── ssp/                       ← Singapore Government SSP reference notes
│   ├── testing/                   ← Test strategy and ground truth guide
│   └── ui/                        ← Dashboard design and guide
│
├── scripts/                       ← Utility scripts (see scripts/README.md)
│   ├── api/                       ← Server lifecycle (used by Makefile)
│   ├── integration/               ← Backtest, accuracy validation, provider tests
│   ├── validation/                ← Orphan node check, LLM config validation
│   ├── ingest/                    ← SSP catalog scraper
│   └── generation/                ← Ground truth generation
│
├── tests/                         ← Test suite (see tests/README.md)
│   ├── unit/                      ← Fast pytest unit tests (make test)
│   └── data/architectures/        ← 25 .mmd test architectures
│
└── .claude/skills/                ← Claude Code skills
    ├── docs-health/               ← Audit CLAUDE.md, DECISIONS.md, memory files
    ├── repo-organise/             ← Audit docs/tests/scripts/report for cleanup
    ├── update-data/               ← Refresh MITRE/ATLAS/SSP/ARC data
    ├── build-embeddings-cache/    ← Regenerate technique_embeddings.json
    ├── check-deprecation/         ← Check for deprecated imports and broken modules
    └── quick-test/                ← 15-second sanity check
```

---

## Document Hierarchy

```
README.md              ← External-facing (GitHub landing page)
    │
    └── CLAUDE.md      ← Developer context (AI assistant + human reference)
            │
            └── docs/DECISIONS.md  ← Authoritative decision log (read every session)
                    │
                    └── docs/STATUS_AND_PLAN.md  ← Current state + next priorities
```

---

**Getting help:** Start with [README.md](README.md) for the full active file index.  
**For AI assistants:** Load `CLAUDE.md` first, then read `docs/DECISIONS.md`.
