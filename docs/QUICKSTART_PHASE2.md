# Phase 2A Quick Start Guide

**Status:** Implementation Complete ✅  
**Date:** 2026-04-26  
**Next:** Testing & Validation

---

## What Was Built

Phase 2A implements **semantic search + LLM-enhanced analysis** for MITRE ATT&CK technique matching:

### Core Components

1. **`chatbot/modules/mitre_embeddings.py`** - Semantic Search Engine
   - Generates embeddings for all 823 MITRE techniques
   - Caches embeddings to JSON (~13MB, 10-15 min build time)
   - Performs cosine similarity search for technique matching

2. **`chatbot/modules/llm_mitre_analyzer.py`** - LLM Analysis Pipeline
   - Refines semantic search results with LLM explanations
   - Constructs logical attack paths (Initial Access → Execution → Persistence...)
   - Generates prioritized mitigation recommendations

3. **`chatbot/modules/agent.py`** - Updated Routing
   - Integrates semantic search + LLM pipeline
   - Maintains keyword fallback for API failures
   - Returns structured results (JSON-ready for future web API)

4. **`chatbot/main.py`** - Enhanced CLI
   - Pretty-printed semantic search results
   - Displays attack paths and mitigations
   - User-friendly terminal output

---

## Installation & Setup

### Step 1: Install Dependencies

```bash
# Activate virtual environment (if not already active)
source .venv/bin/activate

# Install updated dependencies
pip install -r requirements.txt
```

**New dependencies:**
- `numpy>=1.24.0` - Vector operations
- `scikit-learn>=1.3.0` - Cosine similarity
- `openai>=1.0.0` - OpenRouter compatibility
- `python-dotenv>=1.0.0` - Environment variables

### Step 2: Verify Environment

```bash
# Check API key is configured
cat .env | grep OPENROUTER_API_KEY

# Should output: OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

If not set:
```bash
echo "OPENROUTER_API_KEY=your_key_here" >> .env
```

### Step 3: Generate Embedding Cache (One-Time, ~10-15 min)

**Option A: Run Test Script (Recommended)**
```bash
python test_phase2_semantic_search.py
```

This will:
- Validate all components
- Generate embedding cache
- Run sample queries
- Test LLM analysis
- Verify agent integration

**Option B: Run CLI Directly**
```bash
python chatbot/main.py
```

The CLI will auto-generate cache on first run.

**Note:** Cache generation takes 10-15 minutes due to OpenRouter free tier rate limit (20 req/min). This is a **one-time cost**. Subsequent runs load cache instantly.

---

## Usage Examples

### Example 1: Simple Query

```bash
python chatbot/main.py
```

**Input:**
```
> Attacker used PowerShell to execute malicious scripts
```

**Output:**
```
📊 MATCHED TECHNIQUES:

1. T1059.001 - PowerShell
   Similarity: 0.856 | Confidence: high
   Relevance: PowerShell is directly relevant as the primary execution vector...
   Tactics: execution

2. T1059.003 - Windows Command Shell
   Similarity: 0.723 | Confidence: medium
   Relevance: Often used alongside PowerShell for command execution...
   Tactics: execution

🎯 ATTACK PATH ANALYSIS:

The attacker begins with execution using PowerShell (T1059.001), leveraging 
its powerful scripting capabilities to run malicious code directly in memory...

Attack Progression:
  Stage 1: Execution
  Techniques: T1059.001
  PowerShell executes the initial payload, establishing a foothold...

🛡️ MITIGATION RECOMMENDATIONS:

Priority Actions:
  1. [CRITICAL] Enable PowerShell script block logging and transcription
     Addresses: T1059.001
     Rationale: Provides visibility into PowerShell commands for detection...

Quick Wins (Easy to Implement):
  1. Enable constrained language mode for PowerShell
  2. Require code signing for PowerShell scripts
```

### Example 2: Complex Scenario

**Input:**
```
> Phishing email with malicious Excel macro that downloads and executes 
> a payload, then creates scheduled tasks for persistence
```

**Expected Output:**
- Multiple matched techniques (T1566, T1059, T1053, etc.)
- Multi-stage attack path (Initial Access → Execution → Persistence)
- Prioritized mitigations covering each stage

### Example 3: Architecture-Based (Future Phase 3)

**Input (text + Mermaid diagram):**
```
Scenario: Web application vulnerable to command injection

Architecture:
graph TD
    A[Internet] --> B[WAF]
    B --> C[Web Server]
    C --> D[App Server]
    D --> E[Database]
```

**Note:** Mermaid parsing not yet implemented (Phase 3). Current version only processes text.

---

## Testing & Validation

### Quick Validation (30 seconds)

```bash
python -c "
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import get_or_build_cache
mitre = MitreHelper(use_local=True)
cache = get_or_build_cache(mitre)
print(f'✅ Ready: {len(cache)} techniques cached')
"
```

### Comprehensive Test Suite (15-20 minutes)

```bash
python test_phase2_semantic_search.py
```

**Tests:**
1. Environment check (API key)
2. MITRE data loading
3. Embedding cache status
4. Cache generation/loading
5. Semantic search with sample queries
6. LLM-enhanced analysis
7. Agent integration

### Manual Testing Checklist

- [ ] Run CLI with sample threat scenario
- [ ] Verify techniques are relevant (similarity score >0.5)
- [ ] Check attack path makes logical sense
- [ ] Review mitigation recommendations for practicality
- [ ] Test fallback mode (temporarily rename .env to test keyword mode)

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'numpy'"

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: "OPENROUTER_API_KEY not found"

**Solution:**
```bash
# Check .env file exists
ls -la .env

# Add API key if missing
echo "OPENROUTER_API_KEY=your_key_here" >> .env
```

### Issue: "Rate limit exceeded (429)"

**Cause:** OpenRouter free tier limits to 20 requests/minute

**Solution:** 
- Wait 60 seconds and retry
- Rate limiter handles this automatically with exponential backoff
- If persistent, check OpenRouter service status

### Issue: "Embedding cache not found"

**Solution:**
```bash
# Generate cache manually
python -c "
from chatbot.modules.mitre import MitreHelper
from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json

mitre = MitreHelper(use_local=True)
cache = build_technique_embeddings(mitre)
save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')
"
```

Takes 10-15 minutes.

### Issue: "LLM analysis returns empty results"

**Possible Causes:**
1. API rate limit hit (wait 60s)
2. API key invalid/expired (check .env)
3. OpenRouter service down (check status.openrouter.ai)

**Fallback:** System automatically uses keyword-based search if LLM fails.

---

## Performance Metrics

### Expected Timings

| Operation | Time | Notes |
|-----------|------|-------|
| Cache generation (first time) | 10-15 min | One-time only, rate limited |
| Cache loading (subsequent) | <1s | Instant from disk |
| Semantic search query | 1-2s | Single embedding + search |
| LLM analysis (full) | 10-15s | Refine + attack path + mitigations |
| Complete CLI workflow | 15-20s | End-to-end analysis |

### Cache Specifications

- **Size:** ~13 MB (823 techniques × 2048 dimensions)
- **Format:** JSON (human-readable)
- **Location:** `chatbot/data/technique_embeddings.json`
- **Rebuild:** Only after MITRE data updates

---

## Next Steps (Phase 3)

Once Phase 2A is validated:

1. **Design API schema** (request/response formats)
2. **Build FastAPI backend** (`chatbot/api/`)
3. **Implement Mermaid parser** (`chatbot/parsers/mermaid_parser.py`)
4. **Create attack path builder** (`chatbot/analysis/attack_path.py`)
5. **Set up Docker** for deployment

See `docs/MVP_SPECIFICATION.md` for complete Phase 3 plan.

---

## Key Files Reference

### Implementation
- `chatbot/modules/mitre_embeddings.py` - Semantic search (450 lines)
- `chatbot/modules/llm_mitre_analyzer.py` - LLM analysis (550 lines)
- `chatbot/modules/agent.py` - Routing logic (150 lines)
- `chatbot/main.py` - CLI interface (180 lines)

### Testing
- `test_phase2_semantic_search.py` - Comprehensive test suite
- `test_openrouter.py` - API validation (from Phase 1)

### Documentation
- `docs/MVP_SPECIFICATION.md` - Complete product spec
- `docs/PROJECT_STRUCTURE.md` - Directory layout
- `IMPLEMENTATION_STATUS.md` - Phase tracking
- `CLAUDE.md` - Project instructions

### Data
- `chatbot/data/enterprise-attack.json` - MITRE ATT&CK data (~35 MB)
- `chatbot/data/technique_embeddings.json` - Embedding cache (~13 MB, generated)

---

## Questions?

- Check logs: Set `logging.basicConfig(level=logging.DEBUG)` for detailed output
- Review test results: `python test_phase2_semantic_search.py`
- Validate API: `python test_openrouter.py`

---

*Phase 2A: Semantic Search Engine - Complete ✅*  
*Ready for testing and validation before Phase 3 (Web API)*
