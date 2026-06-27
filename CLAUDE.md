# ThreatAssessor - Developer Quick Reference

**Version:** 1.4  
**Status:** ✅ Production-Ready — REST API live, D3 Visualise tab + Expert Review UX complete  
**Core Feature:** Architecture diagram → Threat assessment + AI/ML analysis + MoE validation + Hardening controls

---

## Session Protocol

**At the start of every session, read:** [`docs/DECISIONS.md`](docs/DECISIONS.md)

This file is the architectural decision log. After any significant decision about architecture, logic, or format, add an entry with: date, what was decided, the reasoning, and what alternatives were rejected.

---

## Primary Commands

**Web Dashboard (Recommended):**
```bash
# Start API server
./scripts/api/api_start.sh

# Access dashboard: http://localhost:8000/dashboard
# API docs:         http://localhost:8000/docs
# See: docs/operations/API_MANAGEMENT.md for full details
```

**CLI Analysis:**
```bash
# Comprehensive analysis with MoE validation
./demo_expert_llm.sh your_architecture.mmd

# Quick deterministic validation (no LLM)
./demo_deterministic_engine.sh --validate-orphan your_architecture.mmd
```

**Output:** 16 files (dashboard + reports + critiques + diagrams)  
**Time:** 2 min (full) or 30 sec (deterministic only)  
**Confidence:** 93-96% (99.5% base ± expert validations)

---

## REST API Endpoints

Base URL: `http://localhost:8000`  
Authentication: `TM-API-KEY` header  
Docs (Swagger UI): `http://localhost:8000/docs`  
OpenAPI spec: `openapi.yaml` (root of repo)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | System health check |
| POST | `/api/v1/analyze` | Yes | Deterministic threat analysis (99.5%) |
| POST | `/api/v1/analyze-stream` | Yes | SSE streaming analysis with progress |
| GET | `/api/v1/expert-review` | Yes | SSE stream for MoE validation |
| GET | `/api/v1/reports` | No | List all report directories |
| GET | `/api/v1/reports/{name}` | No | List files for an architecture |
| GET | `/api/v1/reports/{name}/files/{file}` | No | Serve report file |
| GET | `/api/v1/reports/{name}/summary` | No | JSON summary |
| GET | `/api/v1/reports/{name}/download` | No | Download report as ZIP |
| GET | `/api/v1/mitigations` | No | MITRE mitigation library |
| GET | `/api/v1/technique-mitigations` | No | Technique→mitigation mapping |
| GET | `/api/v1/techniques` | No | MITRE technique library |

---

## Key Module Paths

**Analysis Pipeline:**
- `chatbot/modules/ground_truth_generator.py` - Main analysis engine
- `chatbot/modules/threat_analyst.py` - RAPIDS + AI/ML pattern detection
- `chatbot/modules/completeness_validator.py` - 6-check validation
- `chatbot/modules/threat_report.py` - Report generation with path-based + hardening controls
- `chatbot/modules/exhaustive_mitigation_mapper.py` - Gap-filling controls (100% coverage)
- `chatbot/modules/self_validation.py` - MITRE technique validation
- `chatbot/modules/residual_risk.py` - Residual risk calculation (10% floor, NIST)

**REST API:**
- `chatbot/api/app.py` - FastAPI application factory
- `chatbot/api/dependencies.py` - Auth (`TM-API-KEY` header)
- `chatbot/api/routes/reports.py` - Report serving endpoints
- `chatbot/api/streaming.py` - SSE streaming + expert review
- `chatbot/api/models/` - Pydantic request/response schemas
- `chatbot/api/static/` - Dashboard UI (index.html + JS + CSS)

**Harness (pipeline controller + governance + registry):**
- `chatbot/harness/controller.py` - ThreatAssessorHarness, PipelineContext, ScenarioConfig
- `chatbot/harness/stages.py` - AnalysisStage, ReportStage, QualityStage, CriticStage, ScrumMasterStage
- `chatbot/harness/governance.py` - GovernanceSignals, InhouseGovernanceAdapter, AGTGovernanceAdapter
- `chatbot/harness/registry.py` - CriticRegistry (control tower for agent activation + governance policy)
- `chatbot/modules/harness*.py` - Re-export shims (backwards compat — canonical source is `chatbot/harness/`)

**Agent Architecture (MoE):**
- `chatbot/modules/agents/critics/` - Architect, Tester, Red Team
- `chatbot/modules/agents/analysts/` - ThreatAnalyst + patterns
- `chatbot/modules/agents/orchestrators/` - MoEOrchestrator

**LLM Client:**
- `agentic/llm_client.py` - Multi-provider LLM client (OpenRouter, Bedrock)
- `agentic/llm.py` - Deprecated wrapper (use llm_client directly)

**Patterns:**
- `chatbot/modules/patterns/ai_pattern.py` - ARC Framework + MITRE ATLAS
- `chatbot/modules/pattern_registry.py` - Pattern registration

**Data Sources (not in git):**
- `chatbot/data/enterprise-attack.json` (44MB) - MITRE ATT&CK
- `chatbot/data/technique_embeddings.json` (45MB) - Embeddings cache
- `chatbot/data/atlas/*.yaml` (230KB) - MITRE ATLAS

---

## Development Guidelines

### 95% Confidence Rule
Before code changes: **Ask clarifying questions** → **Research thoroughly** → **Test incrementally**

**Red flags:** "I think...", assumptions, unexplored code paths

### Code Standards
- Follow patterns in `chatbot/modules/`
- Type hints + docstrings for public APIs
- Test on multiple architectures before committing
- No secrets in code (use `.env`)

### Testing Commands
```bash
# Validate + analyze
./demo_deterministic_engine.sh --validate-orphan architecture.mmd
python3 -m chatbot.main --gen-arch-truth architecture.mmd

# Check validation
python3 -m chatbot.modules.completeness_validator architecture_name

# Batch test all architectures
python3 scripts/backtest_all_architectures.py

# Orphan node check
python3 scripts/validation/check_orphans.py architecture_name
```

---

## What NOT to Commit

```
_codex/                      # Experimental code
archive/                     # Historical docs
report/                      # Generated reports
chatbot/data/*.json          # Large data files (44MB + 45MB)
.env                         # API keys
```

**DO commit:** `tests/data/architectures/*.mmd`, `docs/`, `.claude/skills/`, `openapi.yaml`

---

## Quick Troubleshooting

**API Management (see [docs/operations/API_MANAGEMENT.md](docs/operations/API_MANAGEMENT.md) for full guide):**
```bash
./scripts/api/api_status.sh    # Check status
./scripts/api/api_stop.sh      # Stop API
./scripts/api/api_restart.sh   # Restart API
tail -f logs/api.log            # View logs
```

**Orphan nodes detected:**
```bash
python3 scripts/validation/check_orphans.py architecture_name
# See: docs/operations/ARCHITECTURE_VALIDATION.md
```

**Validation fails:**
```bash
python3 -m chatbot.modules.completeness_validator architecture_name
cat report/architecture_name/ground_truth.json
```

**Update MITRE data (quarterly):**
```bash
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(); m.update_data()"
```

---

## Documentation Map

**Navigation:**
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) - Start here for doc overview

**Quick Reference:**
- Markdown sources: [README.md](README.md), [docs/STATUS_AND_PLAN.md](docs/STATUS_AND_PLAN.md)
- API spec: [openapi.yaml](openapi.yaml) - OpenAPI 3.0 machine-readable spec
- API management: [docs/operations/API_MANAGEMENT.md](docs/operations/API_MANAGEMENT.md)
- Development guide: [docs/development/NEXT_STEPS.md](docs/development/NEXT_STEPS.md)

**Core references:**
- [docs/core/V1_FEATURES.md](docs/core/V1_FEATURES.md) - Feature list
- [docs/operations/OPERATIONS.md](docs/operations/OPERATIONS.md) - Troubleshooting
- [docs/phases/phase3d/](docs/phases/phase3d/) - MoE architecture details
- [docs/README.md](docs/README.md) - Full documentation index

---

**Purpose:** AI assistant context + developer quick reference  
**Last Updated:** 2026-06-14
