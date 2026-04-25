# DEV-TEST Chatbot Project

## Project Overview

A modular, security-focused chatbot system that integrates MITRE ATT&CK data to provide intelligent threat analysis, technique identification, and mitigation advice. The system uses LLM-based semantic search to map user-described threat scenarios to relevant MITRE techniques.

**Primary Use Case:** Security teams describe threat scenarios in natural language, system identifies applicable MITRE ATT&CK techniques and provides contextual mitigation guidance.

## Quick Reference

- **Architecture & Design:** See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design, module structure, tech stack, design decisions, performance metrics, and known limitations
- **Operations & Workflows:** See [docs/OPERATIONS.md](docs/OPERATIONS.md) - Environment setup, data management, development workflows, troubleshooting, and security considerations
- **Testing & Validation:** See [docs/TESTING.md](docs/TESTING.md) - Test strategies, scenarios, validation results, and how to run tests
- **Roadmap & Future Plans:** See [docs/ROADMAP.md](docs/ROADMAP.md) - Current status, implementation phases, and backlog features
- **External Resources:** See [docs/REFERENCES.md](docs/REFERENCES.md) - Links to MITRE, OpenRouter, LiteLLM, ADK documentation

## Core Workflow (Quick Summary)

```
User Input → AgentManager → Semantic Search (embeddings) 
  → LLM Refinement (Gemma) → Mitigation Advice → Response
  
Fallback: Keyword search if API unavailable
```

## Key Technologies

- **LLM Services:** OpenRouter (nvidia/llama-nemotron-embed-vl-1b-v2:free for embeddings, google/gemma-4-26b-a4b-it:free for analysis)
- **MITRE Data:** enterprise-attack.json (823 techniques)
- **API Client:** LiteLLM 1.73.6
- **Framework:** Google ADK 1.5.0
- **Database:** Neo4j 5.28.1 (for agentic features)

## Getting Started

### 1. Environment Setup

Create `.env` file:
```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Verify Setup
```bash
python test_openrouter.py
```

### 4. Generate Embedding Cache (one-time, ~10-15 min with rate limiting)
```bash
# Note: Takes 10-15 minutes due to OpenRouter free tier rate limit (20 req/min)
python -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; from chatbot.modules import embeddings; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre, embeddings); save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')"
```

**Important:** OpenRouter free tier limits to 20 requests/minute. Cache generation is automatically rate-limited and will take 10-15 minutes. This is a one-time setup cost.

### 5. Run Chatbot
```bash
python chatbot/main.py
```

## Module Quick Reference

### Core Modules (`chatbot/modules/`)
- `agent.py` - Request routing and coordination
- `mitre.py` - MITRE ATT&CK data access
- `rate_limiter.py` - API rate limiting (20 req/min) **[IMPLEMENTED]**
- `embeddings.py` - OpenRouter embedding client (NEW)
- `mitre_embeddings.py` - Semantic search with caching (NEW)
- `llm_mitre_analyzer.py` - LLM-enhanced analysis (NEW)
- `mitre_template.py` - Keyword fallback (EXISTING)

### Agentic Modules (`agentic/`)
- `llm.py` - LLM client wrapper (TO IMPLEMENT)
- `helper.py` - Utility functions and env management
- `agent_manager.py` - Agentic routing (future)
- `rag.py`, `mcp.py` - Advanced features (placeholders)

## Development Guidelines

### Code Standards
- Follow existing module patterns
- Use type hints for function signatures
- Add docstrings for public APIs
- Handle errors gracefully with fallbacks
- Log important events for debugging

### Before Committing
1. Run test suite
2. Update relevant documentation
3. Test with standard scenarios (see docs/TESTING.md)
4. Verify no secrets in code

### When to Update Docs
- New modules/functions: Update ARCHITECTURE.md
- New workflows/procedures: Update OPERATIONS.md
- New test cases: Update TESTING.md
- Feature planning: Update ROADMAP.md

## Current Status

**Phase:** Planning Complete, Ready for Implementation  
**Last Validated:** 2026-04-25  
**Confidence:** 95%+ (all components validated)

**Validated Systems:**
✅ OpenRouter API (embeddings + LLM)  
✅ LiteLLM integration  
✅ MITRE data loading  
✅ Semantic search pipeline  
✅ Performance metrics  

**Next Implementation Steps:**
1. ✅ Create `chatbot/modules/rate_limiter.py` - Rate limiting (DONE)
2. Create `chatbot/modules/embeddings.py` - Embedding client with rate limiting
3. Create `chatbot/modules/mitre_embeddings.py` - Semantic search with rate limiting
4. Create `chatbot/modules/llm_mitre_analyzer.py` - LLM refinement with rate limiting
5. Implement `agentic/llm.py` - OpenRouter client with rate limiting
6. Integrate into `agent.py` with fallback logic

**Critical:** All OpenRouter API calls MUST use `@rate_limited` decorator to handle 20 req/min limit

## Troubleshooting Quick Fixes

**Embedding cache missing or outdated:**
```bash
# Use skill (recommended)
/build-embeddings-cache

# Note: Will take 10-15 minutes due to rate limiting
```

**MITRE data outdated:**
```bash
# Use skill to download latest version
/update-mitre-data

# IMPORTANT: Must regenerate cache after update
/build-embeddings-cache
```

**API rate limit errors (429):**
- ✅ Automatic retry with 60s wait (handled by rate limiter)
- ✅ Exponential backoff on repeated errors
- ⚠️  If still failing: Check OpenRouter service status
- See [docs/RATE_LIMITING.md](docs/RATE_LIMITING.md) for details

**Poor matching results:**
- Verify embedding cache is current
- Check similarity scores (should be >0.5)
- See docs/OPERATIONS.md for detailed debugging

**Rate limiting issues:**
- All API calls use `@rate_limited` decorator
- Automatic pacing to stay under 20 req/min
- See [docs/RATE_LIMITING.md](docs/RATE_LIMITING.md) for patterns and best practices

## Available Skills

Skills provide automated operations for common tasks:

**Testing & Validation:**
- `/quick-test` - Fast check (~15s) to verify core components are working
- `/validate-integration` - Comprehensive test suite (2-3 min, full validation)

**Maintenance:**
- `/update-mitre-data` - Download latest MITRE ATT&CK data and backup old version
- `/build-embeddings-cache` - Generate embedding cache (10-15 min, one-time)

**Recommended workflow:**
1. Start session: `/quick-test` (verify everything works)
2. After MITRE update: `/update-mitre-data` → `/build-embeddings-cache`
3. Before deployment: `/validate-integration` (full test)

## Additional Resources

- See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for detailed phase tracking
- See [README.md](README.md) for user-facing documentation
- See [.github/](.github/) for CI/CD and contribution guidelines

---

*Version: 0.2.0 (LLM-enhanced semantic search - Planning Phase)*  
*Last Updated: 2026-04-25*  
*Status: Validated & Ready for Implementation*
