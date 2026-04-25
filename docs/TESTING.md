# Testing Guide

## Testing Strategy

### Unit Tests
- `chatbot/modules/test_mitre.py` - MITRE helper functions
- Need to add:
  - `test_embeddings.py` - OpenRouter embedding client
  - `test_mitre_embeddings.py` - Semantic search
  - `test_llm_mitre_analyzer.py` - LLM integration

### Integration Tests
- End-to-end flow: user input → semantic search → LLM → output
- Fallback behavior: API failure → keyword search
- Cache loading: JSON → memory

## Test Scenarios

### 1. PowerShell Remote Execution
```
Input: "PowerShell remote execution"
Expected: T1059.001 (PowerShell)
Confidence: >0.8
```

### 2. Browser Password Stealing
```
Input: "Stealing passwords from browsers"
Expected: T1555.003 (Credentials from Web Browsers)
Confidence: >0.7
```

### 3. RDP Access
```
Input: "RDP access for IT support"
Expected: T1021.001 (Remote Desktop Protocol)
Confidence: >0.8
```

### 4. API Failure Simulation
```
Test: Disconnect network
Expected Behavior:
- Verify keyword fallback works
- Verify user sees "Using fallback search" message
```

### 5. Rate Limit Handling
```
Test: Send 25 rapid API requests (Test 9 in test_openrouter.py)
Expected Behavior:
- Automatic pacing to stay under 20 req/min
- No 429 errors with rate limiter enabled
- Automatic retry on 429 errors
- Exponential backoff on repeated failures
- Progress reporting showing rate limit stats
```

## Validation Results

### Integration Test Summary (2026-04-25)

**Test Script:** `test_openrouter.py`

**Results:**
- ✅ Environment configuration validated
- ✅ OpenRouter API key working (length: 73 chars)
- ✅ LiteLLM 1.73.6 installed and functional
- ✅ Embedding API: nvidia/llama-nemotron-embed-vl-1b-v2:free
  - Response time: 1.21s
  - Dimension: 2048
  - Cost: $0 (confirmed)
- ✅ Batch embeddings: 3 texts in 1.06s
- ✅ Cosine similarity: Working (1.0 for identical, 0.2037 for related)
- ✅ LLM API: google/gemma-4-26b-a4b-it:free
  - Response time: 3.85s
  - Cost: $0 (confirmed)
  - Quality: Correctly identified T1059.001 (PowerShell)
- ✅ LiteLLM routing: Working (1.26s response)
- ✅ MITRE integration: 823 techniques loaded
- ✅ Real technique embeddings: 5 samples in 1.17s
- ✅ Semantic search: Working with cosine similarity
- ✅ Rate limiting: Automatic pacing at 20 req/min
  - Tested with 25 rapid requests
  - Automatic retry on 429 errors
  - Exponential backoff working

**Sample LLM Output:**
```
Scenario: "We allow employees to use PowerShell scripts for automation tasks."

LLM Response:
1. T1059.001 (Command and Scripting Interpreter: PowerShell)
   - Attackers frequently use PowerShell to execute malicious commands
2. T1027 (Obfuscated Files or Information)
   - PowerShell allows complex encoding to bypass detection
```

**Performance Estimates (Validated):**
- Full cache generation: 
  - Optimistic (no rate limits): 3-5 minutes
  - **Realistic (with rate limits): 10-15 minutes**
  - Calculation: 274 batches ÷ 20 req/min = 13.7 min minimum
- Per-query latency: ~5s (acceptable for security analysis)
- Rate limiter overhead: <100ms per request (negligible)

**Rate Limiting (CRITICAL):**
- **Free tier limit:** 20 requests per minute (hard limit)
- **Enforcement:** `@rate_limited` decorator on all API calls
- **Retry strategy:** Exponential backoff (2s, 4s, 8s, 16s, 32s)
- **429 errors:** Minimum 60s wait before retry
- **Max retries:** 5 attempts before failure

**Confidence Level: 95%+**

All models confirmed working with `:free` suffix. Rate limiting tested and validated. Ready for Phase 1 implementation.

## Running Tests

### Quick Validation
```bash
python test_openrouter.py
```

### Unit Tests
```bash
pytest chatbot/modules/test_mitre.py -v
```

### Integration Tests (Future)
```bash
pytest tests/integration/ -v
```
