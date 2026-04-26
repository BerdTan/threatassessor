# Current Project Structure (Phase 2A Complete)

**Last Updated:** 2026-04-26  
**Phase:** 2A (Semantic Search Implementation Complete)

---

## Root Directory

```
DEV-TEST/
├── .env                          # Environment variables (API keys)
├── .env.example                  # Template for .env
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
│
├── CLAUDE.md                     # Project instructions & guidelines
├── README.md                     # User-facing documentation
├── IMPLEMENTATION_STATUS.md      # Phase tracking & progress
├── PROJECT_STRUCTURE_CURRENT.md  # This file
│
├── .venv/                        # Python virtual environment
├── .claude/                      # Claude Code configuration
│   └── skills/                   # Automation skills
│       ├── quick-test.md
│       ├── validate-integration.md
│       ├── update-mitre-data.md
│       └── build-embeddings-cache.md
│
├── chatbot/                      # Main application code
├── agentic/                      # Agentic/ADK code (future)
├── tests/                        # All test scripts & guides
├── docs/                         # Documentation
└── archive/                      # Deprecated/unused code
```

---

## chatbot/ - Main Application

### chatbot/modules/ - Core Logic (Active)

**Search & Analysis:**
- `agent.py` - Request routing, semantic search integration
- `mitre.py` - MITRE ATT&CK data loading
- `mitre_embeddings.py` - Semantic search with embeddings
- `llm_mitre_analyzer.py` - LLM-enhanced analysis & attack paths
- `mitre_template.py` - Keyword-based fallback

**Infrastructure:**
- `embeddings.py` - OpenRouter embedding client
- `rate_limiter.py` - API rate limiting (20 req/min)

**Entry Points:**
- `main.py` - CLI interface

### chatbot/data/ - Data Storage

- `enterprise-attack.json` - MITRE ATT&CK data (~35 MB)
- `enterprise-attack-backup.json` - Backup (auto-created)
- `technique_embeddings.json` - Embedding cache (~13 MB, generated)

---

## agentic/ - Future Agentic Features

**Active:**
- `helper.py` - Utility functions (get_openrouter_api_key, etc.)
- `llm.py` - LiteLLM client wrapper

**Future Placeholders:**
- (agent_manager, mcp, rag moved to archive - will be rebuilt in later phases)

---

## tests/ - Testing & Validation

**Test Scripts:**
- `test_openrouter.py` - API validation (Phase 1)
- `test_phase2_semantic_search.py` - Comprehensive Phase 2A tests
- `quick_test_phase2.sh` - Quick validation script
- `run_phase2_tests.sh` - Interactive test suite
- `run_phase2_tests_auto.sh` - Automated test suite

**Testing Files:**
- `test_mitre.py` - MITRE module unit tests
- `demo_mitre_advice.py` - Demo script

**Guides:**
- `TESTING_GUIDE.md` - Step-by-step testing instructions

---

## docs/ - Documentation

**Technical Documentation:**
- `ARCHITECTURE.md` - System design & architecture
- `OPERATIONS.md` - Development workflows
- `TESTING.md` - Test strategies
- `ROADMAP.md` - Implementation phases
- `RATE_LIMITING.md` - Rate limiting patterns
- `REFERENCES.md` - External documentation links

**Specifications:**
- `MVP_SPECIFICATION.md` - Web app MVP requirements
- `PROJECT_STRUCTURE.md` - Planned directory structure
- `QUICKSTART_PHASE2.md` - Phase 2A setup guide

---

## archive/ - Deprecated Code

**From chatbot/modules:**
- `knowledgebase.py` - Unused placeholder
- `mcp.py` - Unused placeholder
- `rag.py` - Unused placeholder
- `logger.py` - Unused utility
- `security.py` - Unused utility

**From agentic/:**
- `agent_manager.py` - Old agentic routing (to be rebuilt)
- `mcp.py` - MCP placeholder (future)
- `neo4j_for_adk.py` - Neo4j integration (future)
- `rag.py` - RAG placeholder (future)
- `tools.py` - ADK tools (future)

**From root:**
- `adk-basic.py` - Old ADK example
- `llm.py` - Old LLM module (replaced by agentic/llm.py)
- `llm_prompt_template.py` - Old prompt templates

---

## Key Files by Purpose

### **Running the Application**
- `chatbot/main.py` - CLI entry point
- `.env` - Configuration (API keys)

### **Core Functionality**
- `chatbot/modules/agent.py` - Main orchestration
- `chatbot/modules/mitre_embeddings.py` - Semantic search
- `chatbot/modules/llm_mitre_analyzer.py` - LLM analysis

### **Testing**
- `tests/test_phase2_semantic_search.py` - Full test suite
- `tests/quick_test_phase2.sh` - Quick validation

### **Documentation**
- `README.md` - Start here
- `CLAUDE.md` - Developer guide
- `docs/MVP_SPECIFICATION.md` - Future web app plan

---

## File Count Summary

| Directory | Files | Purpose |
|-----------|-------|---------|
| `chatbot/modules/` | 8 active | Core application logic |
| `agentic/` | 2 active | LLM & helper utilities |
| `tests/` | 8 files | Testing & validation |
| `docs/` | 10 files | Documentation |
| `archive/` | 13 files | Deprecated code |
| **Total Active** | **18 files** | **Production code** |

---

## Next Steps

### Phase 3: Web API Backend
**New directories to create:**
- `chatbot/api/` - FastAPI routes & models
- `chatbot/parsers/` - Input parsing (text, Mermaid)
- `chatbot/analysis/` - Attack path construction

### Phase 4: Frontend
**New directory:**
- `frontend/` - React web UI

### Phase 5: Deployment
**New files:**
- `Dockerfile` - Container definition
- `docker-compose.yml` - Multi-service setup
- `.github/workflows/` - CI/CD pipelines

---

*Clean, organized, ready for Phase 3 implementation.*
