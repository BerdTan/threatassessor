# System Architecture

**Last Updated:** 2026-05-01  
**Status:** Phase 2A Complete (Semantic Search + LLM Analysis)  
**Next:** Architecture Analysis Integration (threatassessor features)

---

## Current Implementation Status

### ✅ Complete (Production-Ready)
- **Phase 1:** Foundation & Configuration
  - OpenRouter API integration (embeddings + LLM)
  - Rate limiting (20 req/min)
  - Environment management
- **Phase 2A:** Semantic Search + LLM Analysis
  - Embedding cache generation (45MB, 823 techniques)
  - Semantic search with cosine similarity
  - LLM-enhanced refinement and ranking
  - Attack path generation
  - Contextual mitigation advice
  - Agent routing with keyword fallback

### 🔄 In Progress (Testing Phase)
- **Test Infrastructure:** Setup complete (2026-05-01)
  - 109 test queries copied
  - Production data fixtures configured
  - Evaluation utilities available
- **Validation:** Creating semantic search accuracy tests
- **Documentation:** Organized in `docs/testing/`

### 📋 Future (Backlog)
- **Architecture Analysis:** From threatassessor-master
  - Mermaid diagram parsing
  - Attack path visualization
  - STRIDE/PASTA framework validation
- **Gaps to Close:**
  - Confidence scoring for attack paths
  - Mermaid diagram output generation

**See:** `STATUS_AND_PLAN.md` for detailed roadmap and action plan

---

## High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                     User Input                              │
│     "We allow RDP access for remote IT support"             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────────┐
         │     AgentManager                  │
         │  (chatbot/modules/agent.py)       │
         │  - Routes requests                │
         │  - Coordinates LLM + fallback     │
         └───────────┬──────────┬────────────┘
                     │          │
          ┌──────────▼──┐     ┌─▼──────────────┐
          │ LLM Path    │     │ Fallback Path  │
          │ (Primary)   │     │ (Keyword)      │
          └──────┬──────┘     └────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │  Semantic Search                   │
    │  (mitre_embeddings.py)             │
    │  - Embed query via OpenRouter      │
    │  - Compare with cached embeddings  │
    │  - Return top 10 candidates        │
    └────────────┬───────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │  LLM Refinement                    │
    │  (llm_mitre_analyzer.py)           │
    │  - Gemma analyzes candidates       │
    │  - Selects 3-5 most relevant       │
    │  - Explains WHY relevant           │
    └────────────┬───────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │  Mitigation Advice Generation      │
    │  (llm_mitre_analyzer.py)           │
    │  - Gemma generates contextual      │
    │    mitigation advice               │
    │  - Includes MITRE official         │
    │    mitigations as reference        │
    └────────────┬───────────────────────┘
                 │
                 ▼
    ┌────────────────────────────────────┐
    │  Formatted Response                │
    │  - Technique IDs + confidence      │
    │  - LLM reasoning                   │
    │  - Actionable mitigation steps     │
    └────────────────────────────────────┘
```

## Technology Stack

**LLM Services (via OpenRouter):**
- **Embeddings:** nvidia/llama-nemotron-embed-vl-1b-v2:free
  - 2048 dimensions (validated)
  - ~1.2s per request
  - $0 cost (confirmed)
- **Language Model:** google/gemma-4-26b-a4b-it:free
  - ~3.8s response time
  - $0 cost (confirmed)
  - Good quality output (tested with MITRE scenarios)
- **API Integration:** LiteLLM 1.73.6 (already in requirements.txt, validated)

**MITRE ATT&CK Data:**
- **Source:** Local `enterprise-attack.json` (~39MB, 823 techniques)
- **Format:** STIX 2.1 JSON
- **Components:** Techniques, tactics, mitigations, relationships

**Python Stack:**
- google-adk==1.5.0 (ADK framework)
- litellm==1.73.6 (unified LLM API)
- neo4j==5.28.1 (graph database for agentic features)

## Data Files

### Production Data (`chatbot/data/`)

#### `enterprise-attack.json` (44MB)
- **Source:** MITRE ATT&CK official dataset via internal lib
- **Content:** Full STIX 2.1 JSON with ~823 techniques
- **Format:** Validated MITRE ATT&CK Enterprise dataset
- **Usage:** All tests and production code use this file
- **Update Frequency:** Quarterly (manual download from MITRE)

#### `technique_embeddings.json` (45MB)
- **Source:** Generated using nvidia/llama-nemotron-embed-vl-1b-v2
- **Content:** Pre-computed embeddings for all 823 techniques
- **Dimensions:** 2048 per technique
- **Generation Time:** 10-15 minutes (one-time with rate limiting)
- **Usage:** Semantic search (offline tests use this cache)
- **Regenerate:** After MITRE data updates

### Test Data (`tests/data/`)

#### Test Queries (`tests/data/generated/`)
- **Source:** Generated from MITRE dataset (imported from threatassessor)
- **Total:** 109 test queries across 8 datasets
- **Format:** JSONL (JSON Lines)
- **Purpose:** Validate semantic search accuracy
- **Datasets:**
  - `technique_canonical.jsonl` (24) - Exact names/IDs
  - `technique_paraphrase.jsonl` (24) - Real-world phrasings
  - `tactic_queries.jsonl` (15) - Tactic-level searches
  - `robustness_mutations.jsonl` (24) - Case/whitespace variations
  - `platform_queries.jsonl` (6) - Platform-specific queries
  - `benign_admin_queries.jsonl` (12) - False positive tests
  - `hard_negative_queries.jsonl` (3) - Disambiguation
  - `multi_step_chain_queries.jsonl` (1) - Attack chains

**See:** `docs/testing/DATA_STRATEGY.md` for testing approach

---

## Module Structure

### Core Modules (`chatbot/modules/`)

#### `agent.py` - Request Router
- **Class:** `AgentManager`
- **Key Methods:**
  - `handle_input(user_input)` - Main entry point
  - `threat_assessment(user_input, keywords)` - Routes to LLM or fallback
  - `extract_keywords(user_input)` - Legacy keyword extraction (fallback only)
- **Responsibilities:**
  - Coordinate LLM-based and keyword-based search paths
  - Handle errors and fallback logic
  - Maintain backward compatibility

#### `mitre.py` - MITRE Data Access
- **Class:** `MitreHelper`
- **Data Loaded:**
  - 823 attack-pattern objects (techniques)
  - 14 x-mitre-tactic objects
  - 268 course-of-action objects (mitigations)
  - 20,411 relationship objects
- **Key Methods:**
  - `find_technique(name_or_id)` - Exact match lookup
  - `get_technique_summary(name_or_id)` - Formatted summary
  - `get_mitigation_advice(technique_id)` - Find related mitigations
- **Note:** Currently uses string search in descriptions for mitigations; should use relationship objects

#### `embeddings.py` - OpenRouter Embedding Client ✅
**Status:** Implemented (Phase 1)
- **Functions:**
  - `get_embedding(text, model="nvidia/llama-nemotron-embed-vl-1b-v2:free")` → List[float]
  - `get_embeddings_batch(texts, model)` → List[List[float]]
  - `cosine_similarity(emb1, emb2)` → float
- **API:** OpenRouter embeddings endpoint
- **Error Handling:** Retry logic, rate limit handling via `@rate_limited`

#### `mitre_embeddings.py` - Semantic Search ✅
**Status:** Implemented (Phase 2A)
- **Cache Management:**
  - `build_technique_embeddings(mitre_helper, embeddings_module)` - One-time generation
  - `save_embeddings_json(embeddings, filepath)` - Store as JSON (~45MB)
  - `load_embeddings_json(filepath)` - Lazy load into memory
- **Search:**
  - `search_techniques(query, mitre_helper, top_k=10)` - High-level API
  - `semantic_search(query_embedding, cache, top_k, min_score)` - Low-level
  - Returns: List[Dict] with external_id, name, similarity_score, tactics
- **Cache:** `chatbot/data/technique_embeddings.json` (45MB, 823 techniques)

#### `llm_mitre_analyzer.py` - LLM-Enhanced Analysis ✅
**Status:** Implemented (Phase 2A)
- **Functions:**
  - `refine_technique_matches(user_input, initial_matches)` - LLM-based ranking
  - `generate_attack_path(user_input, techniques)` - Attack chain construction
  - `generate_mitigation_advice(user_input, techniques)` - Contextual mitigations
  - `analyze_scenario(user_input)` - Complete end-to-end analysis
- **LLM Model:** google/gemma-4-26b-a4b-it:free via OpenRouter
- **System Prompts:** Three specialized prompts for refinement, paths, mitigations

#### `mitre_template.py` - Keyword Fallback ✅
**Status:** Existing (Maintained for resilience)
- **Function:** `build_threat_prompt(user_input, keywords, mitre_helper)`
- **Purpose:** Fallback when LLM/API unavailable
- **Mechanism:** Substring matching in technique names/descriptions
- **Usage:** Automatically activated on API failures

#### `rate_limiter.py` - API Rate Limiting ✅
**Status:** Implemented (Phase 1)
- **Class:** `RateLimiter`
- **Decorator:** `@rate_limited(max_retries=5, base_delay=2.0)`
- **Free Tier Limit:** 20 requests per minute
- **Features:**
  - Sliding window algorithm
  - Automatic retry with exponential backoff
  - Special handling for 429 (rate limit) and 5xx errors
  - Progress reporting for batch operations
- **Usage:** Wraps all OpenRouter API calls
- **See:** [docs/RATE_LIMITING.md](RATE_LIMITING.md) for detailed documentation

### Agentic Modules (`agentic/`)

#### `llm.py` - LLM Client ✅
**Status:** Implemented (Phase 1)
- **Functions:**
  - `call_llm(prompt, model=None, system_prompt=None)` - Call OpenRouter via LiteLLM
  - `call_llm_with_json(prompt, model=None)` - Force JSON output
- **Features:**
  - Error handling and retry logic via `@rate_limited`
  - Model: google/gemma-4-26b-a4b-it:free (default)
  - Supports custom system prompts
  - JSON mode for structured outputs

#### `helper.py` - Utility Functions ✅
**Status:** Enhanced (Phase 1)
- **Environment Management:**
  - `load_env()` - Load .env via python-dotenv
  - `get_openai_api_key()` - Returns OPENAI_API_KEY
  - `get_openrouter_api_key()` - Returns OPENROUTER_API_KEY ✅ Added
  - `get_neo4j_import_dir()` - Returns NEO4J_IMPORT_DIR
- **Agent Support:**
  - `AgentCaller` class - Wrapper for ADK agent execution
- **Note:** Lazy imports for Google ADK (performance optimization)

#### Other Agentic Files
- `agent_manager.py` - Agentic routing (archived - future consideration)
- `rag.py` - Retrieval-augmented generation (archived - future consideration)
- `mcp.py` - Model Context Protocol (archived - future consideration)
- `adk-basic.py` - Google ADK examples and patterns (reference)
- `neo4j_for_adk.py` - Neo4j wrapper for agents (available, not in use)
- `tools.py` - Tool definitions for agents (reference)

**Note:** Agentic features are available but not currently integrated. See `archive/` for unused modules.

---

## Testing Infrastructure

### Test Fixtures (`tests/conftest.py`) ✅
**Status:** Implemented (2026-05-01)
- **Strategy:** Use production data instead of copying fixtures
- **Key Fixtures:**
  - `production_mitre()` - Uses `chatbot/data/enterprise-attack.json`
  - `production_embeddings()` - Uses `chatbot/data/technique_embeddings.json`
  - `has_embedding_cache` - Check if cache available
  - `test_queries_dir()` - Path to test query datasets

### Evaluation Utilities (`tests/eval_utils.py`) ✅
**Status:** Imported from threatassessor
- **Functions:**
  - `load_jsonl(path)` - Load test query datasets
  - `evaluate_records(records, search_fn)` - Batch evaluation
  - `top_k_hit(record, results, k)` - Check if expected technique in top-k
  - `recall_at_k(record, results, k)` - Calculate recall
  - `tactic_match(record, results, k)` - Check tactic alignment

### Pytest Markers
- `@pytest.mark.offline` - Tests without API calls (use production cache)
- `@pytest.mark.online` - Tests requiring API access
- `@pytest.mark.slow` - Tests taking >5 seconds
- `@pytest.mark.requires_cache` - Tests needing embedding cache

### Auto-Skip Logic
- Online tests skipped if `OPENROUTER_API_KEY` not set
- Cache-requiring tests skipped if `technique_embeddings.json` missing

**See:** `docs/testing/` for comprehensive testing documentation

## Key Design Decisions

### 1. OpenRouter for Everything
**Why:** 
- Free tier for both embeddings and LLM
- No local model storage (space-efficient)
- Unified API via LiteLLM
- Easy to swap models

**Trade-offs:**
- Requires internet connection
- API rate limits during embedding generation
- Need fallback for offline scenarios

**Mitigation:**
- Cache embeddings (only generate once)
- Keyword search fallback
- Retry logic with exponential backoff

### 2. JSON for Embedding Cache
**Why:**
- Human-readable for debugging
- Easy to inspect and validate
- Portable across systems

**Trade-offs:**
- Larger file size (~6-8MB vs ~2MB binary)
- Slightly slower load time

**Alternatives Considered:**
- Pickle: Not human-readable, version-dependent
- NumPy .npy: Requires NumPy, not easily inspectable
- SQLite: Overkill for read-only cache

### 3. Two-Stage Search (Embeddings → LLM)
**Why:**
- Embeddings: Fast, broad retrieval (top 10 candidates)
- LLM: Contextual refinement and reasoning
- Best of both worlds: speed + intelligence

**Why Not Direct LLM Search:**
- Can't fit all 823 technique descriptions in context
- Would require chunking and multiple API calls
- More expensive and slower

### 4. Keep Keyword Fallback
**Why:**
- Resilience to API failures
- Works offline
- No external dependencies
- Zero cost

**When Used:**
- OpenRouter API down
- Rate limit exceeded
- Embedding cache missing
- Network unavailable

## Performance Expectations

### Embedding Generation (One-Time) - VALIDATED ✅

**Important:** OpenRouter free tier has a hard limit of **20 requests/minute**

**Time Estimates:**
- **Optimistic (no rate limits):** 3-5 minutes
- **Realistic (with rate limits):** 10-15 minutes
- **With retries:** 15-20 minutes

**Calculation:**
- 823 techniques ÷ 3 per batch = 274 requests
- 274 requests ÷ 20 req/min = 13.7 minutes minimum
- Plus API response time: ~1s/request = 4.5 minutes
- **Total realistic time: 10-15 minutes (one-time setup)**

**Retry Strategy:**
- Exponential backoff: 2s, 4s, 8s, 16s, 32s
- Rate limit errors (429): Wait 60s minimum
- Server errors (5xx): Standard exponential backoff
- Max retries: 5 attempts

**Performance Metrics:**
- Single request: ~1.2s (measured)
- Batch request: ~1.1s for 3 texts (measured)
- Rate limiter overhead: <100ms per request

### Query Performance - VALIDATED ✅
- **Embedding API Call:** ~1.2s (measured, includes rate limit check)
- **LLM Refinement:** ~3.8s (measured with Gemma, includes rate limit check)
- **Total Response:** ~5s (embedding + LLM + processing)
- **Fallback (Keyword):** <50ms (local search, no API calls)
- **Rate Limiter Overhead:** <100ms per query (negligible for user experience)

### Memory Usage
- **Embedding Cache:** ~45MB on disk, ~45MB in memory (2048-dim vectors × 823 techniques)
- **MITRE Data:** ~44MB on disk, ~44MB in memory
- **Total Runtime Memory:** ~89MB (acceptable for modern systems)
- **Test Memory:** Same as runtime (tests use production data)

## Known Limitations

### Current Implementation
1. **Mitigation Lookup:** Uses string search instead of MITRE relationship objects
   - **Impact:** May miss some mitigations
   - **Fix:** Use `relationship.type == "mitigates"` queries

2. **No Attack Chain Analysis:** Only single-technique identification
   - **Impact:** Doesn't show technique progression
   - **Future:** Multi-technique attack paths

3. **No Tactic Filtering:** Can't query "show me all Persistence techniques"
   - **Impact:** Limited exploratory queries
   - **Future:** Add tactic-based filtering

4. **No Platform Awareness:** Doesn't filter by OS/environment
   - **Impact:** May suggest Windows techniques for Linux scenario
   - **Future:** Extract platform from user input, filter accordingly

### LLM Limitations
1. **Free Tier Rate Limits:** 20 requests/minute hard limit
   - **Impact:** Cache generation takes 10-15 minutes instead of 3-5 minutes
   - **Mitigation:** Rate limiter with automatic pacing and retry logic
   - **One-time cost:** Only affects initial cache generation
2. **Model Hallucination:** LLM may invent technique IDs (mitigated by candidate list)
3. **Context Length:** Limited to ~8K tokens for Gemma
4. **Response Variability:** Same query may get slightly different results
