# Quick Reference - Phase 2A

**Last Updated:** 2026-04-26  
**Status:** Organized & Ready for Testing

---

## 🚀 Quick Commands

### Run Tests
```bash
# Quick validation (30s)
bash tests/quick_test_phase2.sh

# Comprehensive tests (2-3 min)
python tests/test_phase2_semantic_search.py

# API validation only
python tests/test_openrouter.py
```

### Run Application
```bash
# CLI mode (interactive)
python chatbot/main.py

# Keyword fallback mode (instant, no cache needed)
python chatbot/main.py
```

### Generate Embedding Cache
```bash
# One-time operation (~10-15 minutes)
source .venv/bin/activate
python -c "
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json
mitre = MitreHelper(use_local=True)
cache = build_technique_embeddings(mitre)
save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')
"
```

---

## 📁 Key Directories

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `chatbot/modules/` | Core logic | agent.py, mitre_embeddings.py, llm_mitre_analyzer.py |
| `agentic/` | LLM utilities | llm.py, helper.py |
| `tests/` | All test files | test_phase2_semantic_search.py, quick_test_phase2.sh |
| `docs/` | Documentation | MVP_SPECIFICATION.md, QUICKSTART_PHASE2.md |
| `archive/` | Deprecated code | (13 archived files) |

---

## 🔧 Key Files

### **Running the App**
- `chatbot/main.py` - CLI entry point
- `.env` - API keys (OPENROUTER_API_KEY)

### **Core Modules**
- `chatbot/modules/agent.py` - Request routing
- `chatbot/modules/mitre_embeddings.py` - Semantic search
- `chatbot/modules/llm_mitre_analyzer.py` - LLM analysis

### **Configuration**
- `requirements.txt` - Dependencies
- `.env.example` - Template for environment

### **Documentation**
- `README.md` - User guide
- `CLAUDE.md` - Developer guide
- `PROJECT_STRUCTURE_CURRENT.md` - Current organization
- `IMPLEMENTATION_STATUS.md` - Progress tracking

---

## 🐛 Common Issues

### Import Timeout
**Problem:** Python hangs on import  
**Cause:** LiteLLM takes 30-60s to load  
**Solution:** Be patient, or use longer timeout (120s)

### API Rate Limit (429)
**Problem:** Rate limit exceeded  
**Cause:** OpenRouter free tier (20 req/min)  
**Solution:** Wait 60s, automatic retry handles this

### Cache Not Found
**Problem:** technique_embeddings.json missing  
**Cause:** Cache not yet generated  
**Solution:** Run cache generation command (see above)

### Module Not Found
**Problem:** Import error after housekeeping  
**Cause:** Trying to import archived module  
**Solution:** Check `archive/` or use new module structure

---

## 📊 Project Stats

- **Active Python files:** 18
- **Test files:** 8
- **Documentation files:** 14
- **Archived files:** 13
- **MITRE techniques:** 835
- **Cache size:** ~13 MB
- **Dependencies:** 8 packages

---

## 🎯 Current Phase Status

### ✅ Phase 1: Complete
- LLM client (LiteLLM + OpenRouter)
- Embedding client
- Rate limiting

### ✅ Phase 2A: Complete
- Semantic search engine
- LLM-enhanced analysis
- Attack path construction
- CLI interface

### ⏳ Phase 2A Testing: Pending
- Embedding cache generation
- End-to-end testing
- Quality validation

### 📋 Phase 3: Next
- FastAPI backend
- Mermaid parser
- API endpoints

---

## 🔗 Quick Links

**Documentation:**
- [MVP Spec](docs/MVP_SPECIFICATION.md) - Web app requirements
- [Testing Guide](tests/TESTING_GUIDE.md) - Step-by-step testing
- [Quickstart](docs/QUICKSTART_PHASE2.md) - Phase 2A setup

**Project Files:**
- [Structure](PROJECT_STRUCTURE_CURRENT.md) - Current organization
- [Status](IMPLEMENTATION_STATUS.md) - Implementation progress
- [README](README.md) - User documentation

---

## 💡 Tips

1. **First time?** Run `bash tests/quick_test_phase2.sh` to verify setup
2. **Testing?** Use `tests/test_phase2_semantic_search.py` for full validation
3. **Developing?** Check `CLAUDE.md` for coding guidelines (95% confidence rule)
4. **Deploying?** Wait for Phase 3 (Web API) and Phase 5 (Docker)

---

*Keep this file handy for quick reference during development!*
