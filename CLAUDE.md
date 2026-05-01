# DEV-TEST: MITRE Chatbot Project

## Project Overview

Production-ready CLI chatbot that maps threat scenarios to MITRE ATT&CK techniques using semantic search and LLM analysis.

**Primary Use Case:** Security teams describe threats in natural language → System identifies MITRE techniques → Provides mitigation guidance.

**Current Status:** ✅ Phase 2A Complete (Production CLI) | Phase 2.2 Next (Validation Testing)

---

## Quick Start

```bash
# Activate environment
source .venv/bin/activate

# Run chatbot
python3 -m chatbot.main

# Test with: "Attacker used PowerShell to create scheduled tasks"
```

---

## Documentation Map

| Document | Purpose |
|----------|---------|
| `README.md` | Quick start guide (start here!) |
| `STATUS_AND_PLAN.md` | Implementation status and roadmap |
| `CLAUDE.md` | This file - Developer guidelines |
| `docs/ARCHITECTURE.md` | System design details |
| `docs/OPERATIONS.md` | Troubleshooting and maintenance |
| `docs/MVP_SPECIFICATION.md` | Web UI requirements (Phase 4) |
| `docs/testing/` | Testing strategy |

---

## Core Architecture

### Data Flow
```
User Input → Semantic Search (embeddings, ~2s)
  → LLM Refinement (optional, ~60s, ~33% uptime)
  → Attack Path + Mitigations
  → Fallback to keyword search if API fails
```

### Key Components

**Production modules:**
- `chatbot/main.py` - CLI entry point
- `chatbot/modules/agent.py` - Request routing with fallback
- `chatbot/modules/mitre.py` - MITRE data access (823 techniques)
- `chatbot/modules/embeddings.py` - Embedding client (2048-dim vectors)
- `chatbot/modules/mitre_embeddings.py` - Semantic search with caching
- `chatbot/modules/llm_mitre_analyzer.py` - LLM refinement (string format)
- `chatbot/modules/rate_limiter.py` - API rate limiting (20 req/min)
- `agentic/llm.py` - LLM client (OpenRouter)

**Data files (required):**
- `chatbot/data/enterprise-attack.json` (44MB) - MITRE data
- `chatbot/data/technique_embeddings.json` (45MB) - Pre-computed cache
- `.env` - API key: `OPENROUTER_API_KEY=sk-or-v1-xxxxx`

---

## Key Technologies

| Component | Technology | Notes |
|-----------|-----------|-------|
| Embeddings | nvidia/llama-nemotron-embed-vl-1b-v2:free | 2048 dimensions |
| LLM | nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free | ~33% uptime (free tier) |
| API Router | LiteLLM 1.73.6 | Multi-provider support |
| Rate Limiting | Custom sliding window | 20 req/min, auto-retry |

---

## Development Guidelines

### 95% Confidence Rule (CRITICAL)

Before making code changes, you MUST achieve **95%+ confidence** that changes are correct and necessary.

**How to reach 95% confidence:**
1. **Ask clarifying questions FIRST** - Don't assume requirements
2. **Research thoroughly** - Read related code, tests, documentation
3. **Validate assumptions** - Test understanding with examples
4. **Plan incrementally** - Break large changes into testable units

**If confidence < 95%:** STOP and ask questions. Better to clarify than break working code.

**Red flags (ask before proceeding):**
- "I think this might work..."
- Making assumptions about requirements
- Changing code you don't fully understand
- Adding features not explicitly requested

### Code Standards

- Follow existing module patterns (see `chatbot/modules/` for reference)
- Use type hints for function signatures
- Add docstrings for public APIs
- Handle errors gracefully with fallbacks
- Log important events for debugging
- Test with standard scenarios before committing

### Testing Before Commit

1. Run semantic search test: `pytest tests/test_semantic_search.py -v`
2. Test CLI manually: `python3 -m chatbot.main`
3. Verify no unintended file changes: `git status`
4. Check no secrets committed: `grep -r "sk-or-v1" .`

---

## Current Status

### ✅ What's Working (Production-Ready)

| Feature | Status | Performance |
|---------|--------|-------------|
| Semantic search | ✅ Working | ~2s, always available |
| LLM analysis | ✅ Working | ~60s, ~33% uptime |
| Attack paths | ✅ Working | Part of LLM output |
| Mitigations | ✅ Working | Mapped to techniques |
| Keyword fallback | ✅ Working | Graceful degradation |
| Rate limiting | ✅ Working | Automatic retry/backoff |

**Validation:**
- Top-3 accuracy: ~60% (informal testing)
- Embedding cache: 834 techniques, 45MB
- Test query: "PowerShell" → Finds T1059.001 (score: 0.856)

### ⏳ What's Next (1 hour)

**Phase 2.2: Validation Testing**
1. Create `tests/test_semantic_search.py`
2. Create `tests/test_llm_analysis.py`
3. Run 109 test queries (already ported)
4. Document baseline accuracy metrics

**See:** `STATUS_AND_PLAN.md` for detailed action plan

### 📦 What's Backlog (5 hours)

**Phase 3: Architecture Analysis (71% complete)**
- Location: `_codex/threatassessor-master` (experimental)
- Missing: Confidence scoring (1.5h), Mermaid output (2-3h)
- Integration: Merge to main repo (2h)

**Phase 4: Web UI (15-20 hours)**
- React + FastAPI interface
- Attack path visualization
- MITRE coverage heatmap

---

## File Exclusions (.gitignore)

**Do NOT commit:**
- `_codex/` - Experimental features (threatassessor)
- `.archive/` - Historical documents
- `archive/` - Session notes and test results
- `chatbot/data/*.json` - Large data files (44MB + 45MB)
- `.venv/` - Virtual environment
- `.env` - API keys

**Rationale:**
- `_codex/` is experimental architecture analysis (separate development track)
- `archive/` contains historical context not needed for production use
- Data files too large for git (regenerate with scripts)

---

## Troubleshooting Quick Fixes

**Chatbot not responding:**
```bash
# Check API key configured
cat .env | grep OPENROUTER_API_KEY

# Activate virtual environment
source .venv/bin/activate

# Run with fallback (works without LLM)
python3 -m chatbot.main
```

**LLM unavailable (429 errors):**
- Expected behavior with free tier (~33% uptime)
- System automatically falls back to semantic search only
- Response will be faster (2-3s) but less detailed

**Cache missing or corrupted:**
```bash
# Regenerate (takes 10-15 min with rate limiting)
python3 -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre); save_embeddings_json(cache)"
```

**Poor matching results:**
- Verify cache exists: `ls -lh chatbot/data/technique_embeddings.json`
- Check similarity scores in output (should be >0.3)
- Try more specific queries: "PowerShell persistence" vs "malware"

**See:** `docs/OPERATIONS.md` for detailed troubleshooting

---

## Quick Commands Reference

**Run chatbot:**
```bash
source .venv/bin/activate && python3 -m chatbot.main
```

**Run tests:**
```bash
pytest tests/ -v
```

**Test OpenRouter API:**
```bash
python3 test_openrouter.py
```

**Update MITRE data (quarterly):**
```bash
# Download latest
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(); m.update_data()"

# Regenerate cache (required after update)
python3 -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre); save_embeddings_json(cache)"
```

---

## Known Issues & Limitations

### 1. LLM Availability (~33% uptime)
**Cause:** Free tier rate limiting on nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free  
**Impact:** LLM analysis intermittently unavailable  
**Mitigation:** Automatic fallback to semantic search only  
**Future:** Switch to paid tier or monitor google/gemma-4-26b-a4b-it:free availability

### 2. Response Time (2-60s)
**Cause:** 2s for semantic search, 60s when LLM available (rate limiting)  
**Impact:** User waits longer for detailed analysis  
**Mitigation:** None for free tier  
**Future:** Paid tier for faster models

### 3. String Parsing Brittleness
**Cause:** LLM sometimes returns inconsistent format  
**Impact:** Occasional parsing failures (attack paths/mitigations)  
**Mitigation:** Regex-based parsing with error recovery (improved from 0% to 100% success when LLM returns text)

---

## Repository Organization

### Main Repo (This Directory)
**Focus:** Production-ready semantic MITRE search  
**Status:** Phase 2A Complete (CLI working)  
**Location:** `/mnt/c/BACKUP/DEV-TEST`

### Experimental Features (_codex/)
**Focus:** Architecture analysis (Mermaid diagrams, attack paths)  
**Status:** 71% complete (5/7 requirements)  
**Location:** `_codex/threatassessor-master` (excluded from git)

**Sync:** Shared components (MITRE data, embeddings, LLM clients) synchronized via `scripts/sync_repos.sh` (weekly)

---

## Next Session Quick Start

**Context:** Production CLI working, validation testing next (1 hour)

**Resume:**
```bash
cd /mnt/c/BACKUP/DEV-TEST
source .venv/bin/activate
cat STATUS_AND_PLAN.md  # Read Phase 2.2 tasks
```

**Immediate tasks:**
1. Create `tests/test_semantic_search.py`
2. Create `tests/test_llm_analysis.py`
3. Run 109 test queries for validation
4. Document baseline accuracy metrics

---

*Version: 0.3.0 (Production CLI - Semantic Search + LLM Analysis)*  
*Last Updated: 2026-05-01*  
*Status: Phase 2A Complete ✅ | Phase 2.2 Next ⏳*
