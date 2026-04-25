# System Architecture

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

#### `embeddings.py` - OpenRouter Embedding Client (NEW)
- **Functions:**
  - `get_embedding(text, model="nvidia/llama-nemotron-embed-vl-1b-v2:free")` → List[float]
  - `get_embeddings_batch(texts, model)` → List[List[float]]
  - `cosine_similarity(emb1, emb2)` → float
- **API:** OpenRouter embeddings endpoint
- **Error Handling:** Retry logic, rate limit handling

#### `mitre_embeddings.py` - Semantic Search (NEW)
- **Cache Management:**
  - `build_technique_embeddings(mitre_helper, embeddings_module)` - One-time generation
  - `save_embeddings_json(embeddings, filepath)` - Store as JSON (~6-8MB)
  - `load_embeddings_json(filepath)` - Lazy load into memory
- **Search:**
  - `semantic_search_techniques(query, cache, embeddings_module, mitre_helper, top_k=10, threshold=0.5)`
  - Returns: `[(technique_id, technique_name, similarity_score), ...]`
- **Cache:** `chatbot/data/technique_embeddings.json`

#### `llm_mitre_analyzer.py` - LLM-Enhanced Analysis (NEW)
- **Functions:**
  - `analyze_threat_with_llm(user_input, top_candidates, mitre_helper)`
    - Input: User scenario + top 10 semantic matches
    - Output: 3-5 refined techniques with reasoning
  - `generate_mitigation_advice(user_input, technique_id, technique_info, mitre_helper)`
    - Input: User scenario + identified technique + MITRE data
    - Output: Contextual, actionable mitigation steps
- **LLM Model:** google/gemma-4-26b-a4b-it:free via OpenRouter

#### `mitre_template.py` - Keyword Fallback (EXISTING)
- **Function:** `build_threat_prompt(user_input, keywords, mitre_helper)`
- **Purpose:** Fallback when LLM/API unavailable
- **Mechanism:** Substring matching in technique names/descriptions
- **Keep as-is:** Minimal maintenance, only used for fallback

#### `rate_limiter.py` - API Rate Limiting (NEW)
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

#### `llm.py` - LLM Client (TO IMPLEMENT)
- **Current:** Empty placeholder
- **Target:**
  - `generate_response(prompt, model=None)` - Call OpenRouter via LiteLLM
  - Error handling and retry logic
  - Model: openrouter/google/gemma-4-26b-a4b-it:free
- **Pattern Reference:** `adk-basic.py` lines 24-51

#### `helper.py` - Utility Functions
- **Existing:**
  - `load_env()` - Load .env via python-dotenv
  - `get_openai_api_key()` - Returns OPENAI_API_KEY
  - `get_neo4j_import_dir()` - Returns NEO4J_IMPORT_DIR
  - `AgentCaller` class - Wrapper for ADK agent execution
- **To Add:**
  - `get_openrouter_api_key()` - Returns OPENROUTER_API_KEY

#### Other Agentic Files
- `agent_manager.py` - Agentic routing (future)
- `rag.py` - Retrieval-augmented generation (placeholder)
- `mcp.py` - Model Context Protocol (placeholder)
- `adk-basic.py` - Google ADK examples and patterns
- `neo4j_for_adk.py` - Neo4j wrapper for agents
- `tools.py` - Tool definitions for agents

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
- **Embedding Cache:** ~13MB in memory (2048-dim vectors)
- **MITRE Data:** ~39MB in memory
- **Total:** ~52MB (acceptable for modern systems)

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
