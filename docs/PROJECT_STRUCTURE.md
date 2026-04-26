# Project Structure - Web App Architecture

**Version:** 0.2.0 (Updated for MVP Web App)  
**Date:** 2026-04-26

---

## Directory Structure (Target State)

```
DEV-TEST/
├── chatbot/                      # Backend core logic
│   ├── __init__.py
│   ├── main.py                   # CLI entry point (legacy, keep for testing)
│   │
│   ├── modules/                  # Core business logic
│   │   ├── __init__.py
│   │   ├── agent.py              # Request routing + orchestration
│   │   ├── mitre.py              # MITRE data access
│   │   ├── mitre_template.py    # Keyword fallback (legacy)
│   │   ├── embeddings.py         # ✅ OpenRouter embedding client
│   │   ├── rate_limiter.py       # ✅ Rate limiting decorator
│   │   ├── mitre_embeddings.py   # TODO: Semantic search + caching
│   │   ├── llm_mitre_analyzer.py # TODO: LLM refinement + attack paths
│   │   └── llm.py                # LLM utilities (if needed)
│   │
│   ├── parsers/                  # TODO: Input parsing
│   │   ├── __init__.py
│   │   ├── text_parser.py        # Extract threat info from text
│   │   └── mermaid_parser.py     # Parse Mermaid diagrams
│   │
│   ├── analysis/                 # TODO: Advanced analysis logic
│   │   ├── __init__.py
│   │   ├── attack_path.py        # Construct attack chains
│   │   └── confidence_scoring.py # Calculate relevance scores
│   │
│   ├── api/                      # TODO: Web API layer
│   │   ├── __init__.py
│   │   ├── app.py                # FastAPI/Flask app initialization
│   │   ├── routes.py             # API endpoints
│   │   ├── models.py             # Request/response schemas
│   │   └── middleware.py         # Error handling, CORS, etc.
│   │
│   └── data/                     # Data storage
│       ├── enterprise-attack.json         # MITRE ATT&CK data
│       ├── technique_embeddings.json      # TODO: Embedding cache
│       └── enterprise-attack-backup.json  # Auto-backup
│
├── frontend/                     # TODO: Web UI
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── components/           # React/Vue components
│   │   │   ├── InputForm.jsx     # Text + Mermaid input
│   │   │   ├── AttackPathGraph.jsx  # Attack path visualization
│   │   │   ├── MitreCoverageMap.jsx # MITRE heatmap
│   │   │   └── AnalysisReport.jsx   # LLM output display
│   │   ├── services/
│   │   │   └── api.js            # Backend API client
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js (or webpack, etc.)
│
├── agentic/                      # Advanced agentic features
│   ├── __init__.py
│   ├── llm.py                    # ✅ LiteLLM client wrapper
│   ├── helper.py                 # ✅ Utility functions
│   ├── agent_manager.py          # TODO: Multi-agent orchestration
│   ├── mcp.py                    # TODO: Model Context Protocol
│   └── rag.py                    # TODO: RAG implementation
│
├── docs/                         # Documentation
│   ├── ARCHITECTURE.md           # System design
│   ├── OPERATIONS.md             # Development workflows
│   ├── TESTING.md                # Test strategies
│   ├── ROADMAP.md                # Implementation plan
│   ├── MVP_SPECIFICATION.md      # ✅ MVP requirements
│   ├── PROJECT_STRUCTURE.md      # ✅ This file
│   ├── RATE_LIMITING.md          # Rate limit patterns
│   └── REFERENCES.md             # External docs
│
├── tests/                        # Test suite
│   ├── test_mitre.py
│   ├── test_embeddings.py
│   ├── test_semantic_search.py   # TODO
│   ├── test_api_endpoints.py     # TODO
│   └── test_mermaid_parser.py    # TODO
│
├── .claude/                      # Claude Code configuration
│   └── skills/                   # Automation skills
│       ├── quick-test.md
│       ├── validate-integration.md
│       ├── update-mitre-data.md
│       └── build-embeddings-cache.md
│
├── archive/                      # Deprecated code
│   ├── adk-basic.py
│   ├── llm.py (old chatbot module version)
│   └── llm_prompt_template.py
│
├── .env                          # Environment variables (gitignored)
├── .env.example                  # Template for .env
├── .gitignore
├── requirements.txt              # Python dependencies
├── CLAUDE.md                     # Project instructions
├── IMPLEMENTATION_STATUS.md      # Phase tracking
├── README.md                     # User-facing docs
└── test_openrouter.py            # API validation script
```

---

## Module Responsibilities

### `chatbot/modules/` - Core Logic

| Module | Responsibility | Status |
|--------|----------------|--------|
| `agent.py` | Request orchestration, routing to appropriate modules | Exists (needs update) |
| `mitre.py` | MITRE ATT&CK data loading, querying | ✅ Complete |
| `embeddings.py` | OpenRouter embedding API client | ✅ Complete |
| `rate_limiter.py` | Rate limiting decorator (20 req/min) | ✅ Complete |
| `mitre_embeddings.py` | Semantic search, embedding cache management | TODO Phase 2 |
| `llm_mitre_analyzer.py` | LLM-based technique refinement, attack path construction | TODO Phase 2 |
| `mitre_template.py` | Keyword-based fallback (legacy) | Exists (keep as fallback) |

### `chatbot/parsers/` - Input Processing (Phase 3)

| Module | Responsibility |
|--------|----------------|
| `text_parser.py` | Extract threat indicators from risk assessment text using LLM |
| `mermaid_parser.py` | Parse Mermaid code to extract components, connections, and attack surface |

### `chatbot/analysis/` - Advanced Analysis (Phase 3)

| Module | Responsibility |
|--------|----------------|
| `attack_path.py` | Construct attack chains from matched techniques (e.g., Initial Access → Execution → Persistence) |
| `confidence_scoring.py` | Calculate and normalize relevance scores for technique matches |

### `chatbot/api/` - Web API Layer (Phase 3)

| Module | Responsibility |
|--------|----------------|
| `app.py` | FastAPI/Flask app initialization, CORS, middleware setup |
| `routes.py` | API endpoints (`/api/analyze`, `/api/technique/{id}`) |
| `models.py` | Pydantic/Marshmallow schemas for request/response validation |
| `middleware.py` | Error handling, logging, rate limiting (external) |

### `frontend/` - Web UI (Phase 4)

| Component | Responsibility |
|-----------|----------------|
| `InputForm` | Text area for risk assessment + Mermaid diagram editor |
| `AttackPathGraph` | Interactive graph visualization of attack chains |
| `MitreCoverageMap` | Heatmap of matched MITRE techniques |
| `AnalysisReport` | Markdown rendering of LLM-generated analysis |

### `agentic/` - Future Enhancements

| Module | Responsibility | Status |
|--------|----------------|--------|
| `llm.py` | LiteLLM client wrapper | ✅ Complete |
| `helper.py` | Environment variable loading, utilities | ✅ Complete |
| `agent_manager.py` | Multi-agent orchestration (future) | Placeholder |
| `mcp.py` | Model Context Protocol integration (future) | Placeholder |
| `rag.py` | RAG implementation for knowledge base (future) | Placeholder |

---

## Data Flow (MVP Architecture)

### Request Flow
```
[Web Browser]
    ↓ HTTP POST
[Frontend (React/Vue)]
    ↓ fetch('/api/analyze')
[FastAPI/Flask Backend]
    ↓
[Input Parsers]
    ├→ text_parser.py (extract threats)
    └→ mermaid_parser.py (extract components)
    ↓
[AgentManager] (chatbot/modules/agent.py)
    ↓
[Semantic Search Pipeline]
    ├→ embeddings.py (generate query embedding)
    ├→ mitre_embeddings.py (search cached embeddings)
    └→ llm_mitre_analyzer.py (refine with LLM)
    ↓
[Analysis Pipeline]
    ├→ attack_path.py (construct chains)
    └→ confidence_scoring.py (calculate scores)
    ↓
[Response Formatter]
    ↓ JSON
[Frontend Visualization]
    ├→ AttackPathGraph (render graph)
    ├→ MitreCoverageMap (render heatmap)
    └→ AnalysisReport (render LLM output)
    ↓
[User sees results]
```

### Caching Strategy
```
[First Run]
    ↓
[mitre_embeddings.py] builds cache
    ├→ Load 823 techniques from mitre.py
    ├→ Generate embeddings via embeddings.py (10-15 min)
    └→ Save to technique_embeddings.json (~13MB)

[Subsequent Runs]
    ↓
[mitre_embeddings.py] loads cache
    ├→ Read technique_embeddings.json (instant)
    └→ Ready for queries
```

---

## File Size Estimates

| File | Size | Notes |
|------|------|-------|
| `enterprise-attack.json` | ~35 MB | MITRE ATT&CK raw data |
| `technique_embeddings.json` | ~13 MB | 823 techniques × 2048 dims |
| Total backend data | ~48 MB | Fits easily in memory |

---

## Development Workflow

### Phase 2: Backend Core (Current)
1. Work in `chatbot/modules/`
2. Test via CLI (`python chatbot/main.py`)
3. Validate with test scripts

### Phase 3: API Layer
1. Create `chatbot/api/` structure
2. Test with `curl` or Postman
3. Document with OpenAPI/Swagger

### Phase 4: Frontend
1. Create `frontend/` with Vite/Create React App
2. Develop against local backend (`http://localhost:8000`)
3. Test with browser DevTools

### Phase 5: Integration
1. Dockerize backend + frontend
2. Deploy to test environment
3. User acceptance testing

---

## Key Dependencies (Updated)

### Backend
```
# Core
litellm>=1.73.6           # LLM client
openai>=1.0.0             # OpenRouter compatibility
numpy>=1.24.0             # Vector operations
scikit-learn>=1.3.0       # Cosine similarity

# Web API (Phase 3)
fastapi>=0.110.0          # Web framework (Option A)
# OR flask>=3.0.0         # Web framework (Option B)
uvicorn>=0.27.0           # ASGI server (if FastAPI)
pydantic>=2.6.0           # Data validation (if FastAPI)

# Existing
requests>=2.31.0          # MITRE data download
python-dotenv>=1.0.0      # Environment variables
```

### Frontend (Phase 4)
```json
{
  "dependencies": {
    "react": "^18.2.0",           // or "vue": "^3.4.0"
    "react-dom": "^18.2.0",
    "axios": "^1.6.0",            // API client
    "mermaid": "^10.8.0",         // Diagram rendering
    "d3": "^7.9.0",               // Visualization (if D3)
    // or "cytoscape": "^3.28.0" // Alternative for graphs
    "marked": "^12.0.0"           // Markdown rendering
  }
}
```

---

## Next Actions

### Before Phase 2 Implementation
- [ ] Review this structure
- [ ] Approve directory layout
- [ ] Confirm module responsibilities align

### During Phase 2
- [ ] Create `mitre_embeddings.py`
- [ ] Create `llm_mitre_analyzer.py`
- [ ] Update `agent.py` to use semantic search
- [ ] Test via CLI (defer web API to Phase 3)

### Before Phase 3
- [ ] Choose web framework (FastAPI vs Flask)
- [ ] Define API schema (request/response formats)
- [ ] Create `chatbot/api/` structure

### Before Phase 4
- [ ] Choose frontend framework (React vs Vue vs Vanilla)
- [ ] Choose visualization library (D3 vs Cytoscape vs React Flow)
- [ ] Create wireframes/mockups (optional but helpful)

---

*This structure balances immediate needs (CLI testing in Phase 2) with future web app requirements (API + Frontend in Phases 3-4).*
