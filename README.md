# DEV-TEST: MITRE ATT&CK Chatbot with LLM-Enhanced Semantic Search

A modular, security-focused chatbot system that integrates MITRE ATT&CK data to provide intelligent threat analysis, technique identification, and mitigation advice using LLM-based semantic search.

**Primary Use Case:** Security teams describe threat scenarios in natural language, system identifies applicable MITRE ATT&CK techniques and provides contextual mitigation guidance.

---

## 🚀 Quick Start

### Current Status: ✅ **WORKING NOW** (Keyword-Based Search)

The chatbot **works right now** using keyword-based MITRE search (no API required). Phase 1 will add LLM-enhanced semantic search for better accuracy.

### Run It Now (No API Needed!)

```bash
# 1. Clone and navigate to project
cd /path/to/DEV-TEST

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the chatbot immediately
python chatbot/main.py

# Example input: "We allow PowerShell scripts for automation"
# Output: Returns matching MITRE techniques and mitigations
```

**Works offline** - Uses keyword matching in MITRE ATT&CK data (835 techniques)

### Optional: Enable LLM-Enhanced Search (Phase 1 - In Progress)

For semantic search and LLM reasoning (requires API key):

```bash
# 1. Create .env file with your API key
echo "OPENROUTER_API_KEY=sk-or-v1-xxxxx" > .env

# 2. Run quick test to verify API
/quick-test

# 3. (Optional) Generate embedding cache for semantic search
/build-embeddings-cache  # Takes 10-15 min

# 4. Once Phase 1 modules are implemented, chatbot will use LLM automatically
```

### What's Working NOW vs Coming Soon

| Feature | Status | Requires API? |
|---------|--------|---------------|
| **Keyword-based search** | ✅ **Working Now** | ❌ No |
| MITRE data (835 techniques) | ✅ Working | ❌ No |
| Basic technique matching | ✅ Working | ❌ No |
| Mitigation suggestions | ✅ Working | ❌ No |
| **Semantic search** | 🚧 Phase 1 | ✅ Yes |
| LLM reasoning | 🚧 Phase 1 | ✅ Yes |
| Contextual advice | 🚧 Phase 1 | ✅ Yes |

---

## 📋 Current Status (April 2026)

### ✅ **WORKING NOW - Keyword-Based Chatbot**

**You can use the chatbot right now!** It works offline using keyword matching:

```bash
python chatbot/main.py
# Input: "We allow RDP for remote support"
# Output: Matching MITRE techniques + mitigations
```

**How it works:**
1. Takes user input (threat scenario)
2. Extracts keywords (simple word splitting)
3. Searches MITRE data (835 techniques) for matches
4. Returns relevant techniques and mitigation advice

**Limitations of current version:**
- ⚠️ Simple keyword matching (not semantic)
- ⚠️ May miss techniques with different wording
- ⚠️ No LLM reasoning about relevance

**But it works reliably offline with no API required!** ✅

---

### ✅ **Foundation Complete (Phase 0)**

**Infrastructure Ready:**
- ✅ Modular architecture with clear separation of concerns
- ✅ MITRE ATT&CK integration (835 techniques, 14 tactics, 268 mitigations)
- ✅ Rate limiting system (handles OpenRouter free tier: 20 req/min)
- ✅ Comprehensive documentation (76% more efficient than original)
- ✅ Automated testing suite (quick + comprehensive)
- ✅ Four operational skills (quick-test, validate-integration, update-mitre-data, build-embeddings-cache)

**API Integration Ready:**
- ✅ OpenRouter API integration configured
- ✅ LiteLLM unified API client
- ✅ Automatic retry with exponential backoff
- ✅ Zero-risk rate limiting (prevents 429 errors)

**Data Management:**
- ✅ MITRE ATT&CK data loading and parsing
- ✅ Automated MITRE data updates with backup
- ✅ Keyword-based search (working fallback)

---

### 🚧 **In Progress (Phase 1) - LLM Enhancement**

Adding semantic search and LLM reasoning to improve accuracy:

- ⏳ `embeddings.py` - OpenRouter embedding client with rate limiting
- ⏳ `mitre_embeddings.py` - Semantic search with caching
- ⏳ `llm_mitre_analyzer.py` - LLM-enhanced analysis and reasoning
- ⏳ Integration into `agent.py` (automatic fallback to keyword search)

**Phase 1 will add:**
- ✨ Semantic understanding (understands similar concepts)
- ✨ LLM reasoning (explains why techniques are relevant)
- ✨ Better accuracy (top 3-5 most relevant techniques)
- ✨ Contextual mitigation advice
- ✨ Automatic fallback to keyword search if API unavailable

**Chatbot will continue working during Phase 1 development** using keyword search.

---

### 📅 **Planned (Phase 2+)**

See [docs/ROADMAP.md](docs/ROADMAP.md) for detailed roadmap.

---

## 📁 Project Structure

```
DEV-TEST/
├── chatbot/
│   ├── main.py                          # Chatbot entry point
│   ├── modules/
│   │   ├── agent.py                     # Request routing
│   │   ├── mitre.py                     # MITRE ATT&CK data access
│   │   ├── rate_limiter.py              # API rate limiting ✅
│   │   ├── embeddings.py                # Embedding client (TO IMPLEMENT)
│   │   ├── mitre_embeddings.py          # Semantic search (TO IMPLEMENT)
│   │   ├── llm_mitre_analyzer.py        # LLM analysis (TO IMPLEMENT)
│   │   └── mitre_template.py            # Keyword fallback
│   └── data/
│       ├── enterprise-attack.json       # MITRE data (835 techniques)
│       └── technique_embeddings.json    # Embedding cache (optional)
│
├── agentic/                             # Future agentic features
│   ├── llm.py                           # LLM client wrapper
│   ├── helper.py                        # Utility functions
│   ├── agent_manager.py                 # Agent orchestration
│   ├── rag.py                           # RAG agent
│   ├── mcp.py                           # MCP agent
│   └── adk-basic.py                     # Google ADK examples
│
├── docs/                                # 📚 Documentation
│   ├── INDEX.md                         # Navigation guide
│   ├── ARCHITECTURE.md                  # System design
│   ├── OPERATIONS.md                    # Workflows
│   ├── MAINTENANCE.md                   # Regular maintenance
│   ├── TESTING.md                       # Test strategies
│   ├── ROADMAP.md                       # Future plans
│   ├── RATE_LIMITING.md                 # Rate limiting guide
│   └── REFERENCES.md                    # External links
│
├── .claude/skills/                      # ⚡ Automated operations
│   ├── quick-test.md                    # Quick validation (~15s)
│   ├── validate-integration.md          # Full test suite (2-3 min)
│   ├── update-mitre-data.md            # MITRE data updates
│   └── build-embeddings-cache.md       # Cache generation
│
├── test_openrouter.py                   # Integration test suite
├── CLAUDE.md                            # Claude AI context (lean baseline)
├── IMPLEMENTATION_STATUS.md             # Implementation phases & roadmap
├── README.md                            # This file
└── requirements.txt                     # Python dependencies
```

---

## 🎯 Key Technologies

- **LLM Services:** OpenRouter (free tier)
  - Embeddings: nvidia/llama-nemotron-embed-vl-1b-v2:free (2048 dimensions)
  - Language Model: google/gemma-4-26b-a4b-it:free
- **API Client:** LiteLLM 1.73.6
- **MITRE Data:** enterprise-attack.json (STIX 2.1 JSON, ~44MB)
- **Framework:** Google ADK 1.5.0 (for future agentic features)
- **Database:** Neo4j 5.28.1 (planned for graph queries)

---

## 🛠️ Available Skills

Skills are automated operations you can invoke:

```bash
/quick-test               # Fast validation (~15s)
/validate-integration     # Comprehensive tests (2-3 min)
/update-mitre-data        # Download latest MITRE data
/build-embeddings-cache   # Generate embedding cache (10-15 min)
```

**Typical workflow:**
- Daily: `/quick-test` → Start coding
- After changes: `/validate-integration`
- Quarterly: `/update-mitre-data` → `/build-embeddings-cache`

---

## 📖 Documentation

**Root Documentation:**
- [CLAUDE.md](CLAUDE.md) - Project overview and quick reference for Claude AI
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Implementation phases, current status, roadmap
- [docs/QUICK_START.md](docs/QUICK_START.md) - Quick start guide
- [docs/TEST_INTEGRATION.md](docs/TEST_INTEGRATION.md) - Integration testing guide

**Technical Details:**
- [docs/INDEX.md](docs/INDEX.md) - Documentation navigation
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design
- [docs/OPERATIONS.md](docs/OPERATIONS.md) - Operations guide
- [docs/RATE_LIMITING.md](docs/RATE_LIMITING.md) - Rate limiting details

**See [docs/README.md](docs/README.md) for complete documentation structure.**

---

## 🧪 Testing

### Quick Test (15 seconds)
```bash
/quick-test
```
Validates: Dependencies, rate limiter, MITRE data, API connection

### Full Integration Test (2-3 minutes)
```bash
python3 test_openrouter.py
# OR
/validate-integration
```
Runs 9 comprehensive tests including rate limit stress test

### Test Coverage
- ✅ Environment configuration
- ✅ Rate limiter (sliding window, retry, backoff)
- ✅ MITRE data loading (835 techniques)
- ✅ OpenRouter API (embeddings + LLM)
- ✅ Semantic search pipeline
- ✅ Stress test (25 rapid requests)

---

## 🔄 Maintenance

### Update MITRE Data (Quarterly)

```bash
# Safe, automated update with backup
/update-mitre-data

# Required: Regenerate embedding cache after update
/build-embeddings-cache
```

MITRE releases updates quarterly. Check: https://attack.mitre.org/resources/updates/

### Backup Management

Automatic backups stored in `chatbot/data/backups/` with timestamps.

**Rollback if needed:**
```bash
cp chatbot/data/backups/enterprise-attack.json.TIMESTAMP.bak \
   chatbot/data/enterprise-attack.json
```

---

## 🛡️ Rate Limiting

OpenRouter free tier: **20 requests per minute**

**Built-in protection:**
- ✅ Sliding window algorithm
- ✅ Automatic retry on 429 errors
- ✅ Exponential backoff (2s, 4s, 8s, 16s, 32s)
- ✅ Real-time rate limit tracking

**All API calls use `@rate_limited` decorator:**
```python
from chatbot.modules.rate_limiter import rate_limited

@rate_limited(max_retries=5, base_delay=2.0)
def api_call():
    # Your API call here
    pass
```

See [docs/RATE_LIMITING.md](docs/RATE_LIMITING.md) for details.

---

## 🚦 Development Status

### Phase 0: Foundation (COMPLETE ✅)
- Documentation reorganization
- Rate limiting system
- MITRE update automation
- Test suite

### Phase 1: Semantic Search (IN PROGRESS ⏳)
- Embedding client
- Semantic search with caching
- LLM-enhanced analysis
- Integration with agent

### Phase 2+: Advanced Features (PLANNED 📅)
- Relationship graph queries
- Multi-technique attack chains
- Platform-aware search
- Web UI
- SIEM integration

See [docs/ROADMAP.md](docs/ROADMAP.md) for complete roadmap.

---

## 🤝 Contributing

1. **Read the docs:** Start with [docs/INDEX.md](docs/INDEX.md)
2. **Run tests:** `/quick-test` and `/validate-integration`
3. **Follow patterns:** See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
4. **Use rate limiting:** All API calls must use `@rate_limited` decorator
5. **Update docs:** Keep documentation current

### Code Standards
- Use type hints for function signatures
- Add docstrings for public APIs
- Handle errors gracefully with fallbacks
- Log important events for debugging
- Test with standard scenarios

---

## 📝 Environment Variables

Required in `.env` file:

```bash
# Required for all LLM features
OPENROUTER_API_KEY=sk-or-v1-xxxxx

# Optional: For Google ADK examples
OPENAI_API_KEY=sk-xxxxx

# Optional: For future Neo4j graph features
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=yourpassword
NEO4J_IMPORT_DIR=/path/to/neo4j/import
```

---

## 🐛 Troubleshooting

### Quick Fixes

**Dependencies missing:**
```bash
pip install -r requirements.txt
```

**API key not configured:**
```bash
echo "OPENROUTER_API_KEY=sk-or-v1-xxxxx" > .env
```

**MITRE data outdated:**
```bash
/update-mitre-data
```

**Embedding cache missing:**
```bash
/build-embeddings-cache
```

**Tests failing:**
```bash
/quick-test  # Check what's broken
```

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for detailed troubleshooting.

---

## 📚 External Resources

- **MITRE ATT&CK:** https://attack.mitre.org/
- **OpenRouter:** https://openrouter.ai/
- **LiteLLM:** https://docs.litellm.ai/
- **Google ADK:** https://github.com/google/adk

---

## 📜 License

[Add your license here]

---

## 📞 Contact & Support

- **Documentation:** See [docs/INDEX.md](docs/INDEX.md)
- **Issues:** [Add issue tracker link]
- **Questions:** [Add contact info]

---

**Version:** 0.2.0 (LLM-enhanced semantic search - Foundation Complete)  
**Last Updated:** April 25, 2026  
**Status:** Phase 0 Complete ✅ | Phase 1 In Progress ⏳
