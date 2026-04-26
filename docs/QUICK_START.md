# Quick Start Guide

## 🚀 First Time Setup

```bash
# 1. Set up environment
cp .env.example .env
# Edit .env and add: OPENROUTER_API_KEY=sk-or-v1-xxxxx

# 2. Install dependencies
pip install -r requirements.txt

# 3. Test integration
python test_openrouter.py

# 4. Generate embedding cache (10-15 min, one-time)
/build-embeddings-cache

# 5. Run chatbot
python chatbot/main.py
```

## 🛠️ Available Skills

Use these skills for common operations:

```bash
# Quick test (~15s) - verify core components
/quick-test

# Full integration test (2-3 min)
/validate-integration

# Generate embedding cache (required after MITRE updates)
/build-embeddings-cache

# Update MITRE ATT&CK data (quarterly)
/update-mitre-data
```

**Typical workflow:**
- Start session: `/quick-test`
- After changes: `/validate-integration`
- Quarterly: `/update-mitre-data` → `/build-embeddings-cache`

## 📚 Documentation Map

**Getting Started:**
- [CLAUDE.md](CLAUDE.md) - Start here, lean baseline
- [docs/INDEX.md](docs/INDEX.md) - Navigation guide

**Development:**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design
- [docs/OPERATIONS.md](docs/OPERATIONS.md) - Workflows
- [docs/TESTING.md](docs/TESTING.md) - Testing guide

**Maintenance:**
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md) - Regular maintenance
- [docs/RATE_LIMITING.md](docs/RATE_LIMITING.md) - Rate limiting guide
- [docs/QUICK_START_RATE_LIMITING.md](docs/QUICK_START_RATE_LIMITING.md) - Quick reference

**Planning:**
- [docs/ROADMAP.md](docs/ROADMAP.md) - Status and future plans
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Phase tracking

## ⚡ Common Tasks

### Test the system
```bash
python test_openrouter.py
```

### Update MITRE data (quarterly)
```bash
/update-mitre-data          # Download + backup + validate
/build-embeddings-cache     # Regenerate cache (REQUIRED)
/validate-integration       # Verify everything works
```

### Check system status
```bash
# Check MITRE data
ls -lh chatbot/data/enterprise-attack.json

# Check embedding cache
ls -lh chatbot/data/technique_embeddings.json

# Verify technique count
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(use_local=True); print(f'{len(m.get_techniques())} techniques')"
```

### Rate limiting
```bash
# Check current rate limit stats
python3 -c "from chatbot.modules.rate_limiter import get_rate_limit_stats; print(get_rate_limit_stats())"

# All API calls MUST use @rate_limited decorator
# See: docs/RATE_LIMITING.md for usage patterns
```

## 🐛 Troubleshooting

**Embedding cache missing:**
```bash
/build-embeddings-cache
```

**MITRE data outdated:**
```bash
/update-mitre-data
/build-embeddings-cache
```

**Rate limit errors (429):**
- Automatic retry (handled by rate limiter)
- See: docs/RATE_LIMITING.md

**Tests failing:**
```bash
# Check environment
python test_openrouter.py

# Verify API key
echo $OPENROUTER_API_KEY
```

## 📖 Key Concepts

**Rate Limiting:**
- OpenRouter free tier: 20 requests/minute
- All API calls use `@rate_limited` decorator
- Cache generation: 10-15 minutes (one-time)

**MITRE Updates:**
- Quarterly releases (Q1, Q2, Q3, Q4)
- Always regenerate cache after update
- Automatic backups to chatbot/data/backups/

**Skills:**
- Automated operations for common tasks
- Use `/skill-name` to invoke
- See .claude/skills/ for definitions

## 🔗 External Links

- MITRE ATT&CK: https://attack.mitre.org/
- MITRE Updates: https://attack.mitre.org/resources/updates/
- OpenRouter: https://openrouter.ai/
- OpenRouter Models: https://openrouter.ai/models
- LiteLLM Docs: https://docs.litellm.ai/

## 💡 Tips

1. **After MITRE updates:** Always run `/build-embeddings-cache`
2. **Rate limiting:** Built-in, automatic, no manual intervention needed
3. **Backups:** Automatic before MITRE updates, stored with timestamps
4. **Testing:** Run `/validate-integration` after any major changes
5. **Documentation:** Check docs/INDEX.md for navigation

## 🎯 Implementation Status

**Completed:**
- ✅ Documentation structure
- ✅ Rate limiting system
- ✅ MITRE update automation
- ✅ Test suite with rate limiting
- ✅ Skills (validate, build-cache, update-mitre)

**Next (Phase 1):**
- Create embeddings.py (with @rate_limited)
- Create mitre_embeddings.py (semantic search)
- Create llm_mitre_analyzer.py (LLM refinement)
- Integrate into agent.py

See [docs/ROADMAP.md](docs/ROADMAP.md) for details.

---

**Quick Reference Card:**

| Task | Command |
|------|---------|
| Test integration | `python test_openrouter.py` or `/validate-integration` |
| Generate cache | `/build-embeddings-cache` |
| Update MITRE | `/update-mitre-data` |
| Run chatbot | `python chatbot/main.py` |
| Check docs | See [docs/INDEX.md](docs/INDEX.md) |
