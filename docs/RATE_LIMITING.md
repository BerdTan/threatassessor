# Rate Limiting Strategy

## OpenRouter Free Tier Limits

**Hard Limit:** 20 requests per minute  
**Consequence:** 429 "Too Many Requests" error if exceeded  
**Impact:** Critical for embedding cache generation (~274 requests for 823 techniques)

## Implementation

### Module: `chatbot/modules/rate_limiter.py`

Provides rate limiting utilities using token bucket algorithm with sliding window.

### Key Components

#### 1. RateLimiter Class
```python
from chatbot.modules.rate_limiter import RateLimiter

limiter = RateLimiter(max_requests=20, time_window=60)
limiter.wait_if_needed()  # Blocks if rate limit would be exceeded
```

**Features:**
- Sliding window algorithm
- Automatic delay calculation
- Thread-safe (for single-threaded apps)
- Real-time statistics

#### 2. @rate_limited Decorator
```python
from chatbot.modules.rate_limiter import rate_limited

@rate_limited(max_retries=5, base_delay=2.0)
def api_call():
    # Your API call here
    response = requests.post(...)
    if response.status_code != 200:
        raise Exception(f"{response.status_code}: {response.text}")
    return response.json()
```

**Features:**
- Automatic retry on 429 (rate limit) and 5xx (server) errors
- Exponential backoff: 2s, 4s, 8s, 16s, 32s
- Extended delay for rate limits (minimum 60s)
- Non-retryable errors fail fast (4xx except 429)

#### 3. Batch Processing Helper
```python
from chatbot.modules.rate_limiter import batch_with_rate_limit

def process_batch(batch):
    # Process batch of items
    return results

results = batch_with_rate_limit(
    items=all_items,
    batch_size=3,
    process_fn=process_batch
)
```

**Features:**
- Automatic batching
- Rate limiting between batches
- Progress reporting
- Conservative pacing (0.5s between batches)

## Usage Patterns

### Pattern 1: Single API Call
```python
from chatbot.modules.rate_limiter import rate_limited

@rate_limited(max_retries=5, base_delay=2.0)
def get_embedding(text: str):
    response = requests.post(EMBEDDING_URL, json={"input": text})
    if response.status_code != 200:
        raise Exception(f"{response.status_code}: {response.text}")
    return response.json()

# Automatically rate-limited and retries on errors
embedding = get_embedding("test query")
```

### Pattern 2: Batch Processing (Recommended for Embeddings)
```python
from chatbot.modules.rate_limiter import rate_limited

@rate_limited(max_retries=5, base_delay=2.0)
def get_embeddings_batch(texts: list):
    # OpenRouter supports batching
    response = requests.post(EMBEDDING_URL, json={"input": texts})
    if response.status_code != 200:
        raise Exception(f"{response.status_code}: {response.text}")
    return [item['embedding'] for item in response.json()['data']]

# Process 823 techniques in batches of 3
all_embeddings = []
batch_size = 3

for i in range(0, 823, batch_size):
    batch = technique_texts[i:i + batch_size]
    batch_embeddings = get_embeddings_batch(batch)
    all_embeddings.extend(batch_embeddings)
    
    # Progress reporting
    print(f"Progress: {i + len(batch)}/823")
```

### Pattern 3: Manual Rate Limiting
```python
from chatbot.modules.rate_limiter import openrouter_limiter

# Manual control when needed
openrouter_limiter.wait_if_needed()
response = requests.post(...)  # Your API call

# Check stats
stats = openrouter_limiter.get_stats()
print(f"Used: {stats['recent_requests']}/{stats['max_requests']}")
```

## Error Handling

### Retryable Errors
- **429 (Rate Limit):** Wait 60s minimum, then retry
- **500-504 (Server Errors):** Exponential backoff, then retry
- **Max retries:** 5 attempts by default

### Non-Retryable Errors
- **400-499 (except 429):** Client errors, fail immediately
- **Authentication errors:** Fail immediately
- **Invalid model errors:** Fail immediately

### Example Error Flow
```
Attempt 1: 429 Rate Limit → Wait 60s → Retry
Attempt 2: 429 Rate Limit → Wait 60s → Retry
Attempt 3: Success → Return result

OR

Attempt 1: 503 Server Error → Wait 2s → Retry
Attempt 2: 503 Server Error → Wait 4s → Retry
Attempt 3: 503 Server Error → Wait 8s → Retry
Attempt 4: Success → Return result
```

## Performance Expectations

### Embedding Cache Generation (823 Techniques)

**Batch Strategy:**
- Batch size: 3 techniques per request
- Total batches: ~274 requests
- Rate limit: 20 requests/minute

**Time Estimates:**

| Scenario | Time |
|----------|------|
| No rate limiting (optimistic) | 3-5 minutes |
| With rate limiting (realistic) | 10-15 minutes |
| With retries due to errors | 15-20 minutes |

**Calculation:**
```
274 requests ÷ 20 req/min = 13.7 minutes minimum
Plus API response time: ~1s per request = ~4.5 minutes
Total realistic time: 10-15 minutes
```

### Query Performance

**Single query:**
- Embedding: 1-2s (includes rate limit check)
- LLM refinement: 3-5s (includes rate limit check)
- Total: 4-7s per query

**Impact:** Minimal - rate limiter adds <100ms overhead for single queries

## Best Practices

### 1. Always Use Decorators
```python
# ✅ Good - automatic retry and rate limiting
@rate_limited(max_retries=5, base_delay=2.0)
def api_call():
    ...

# ❌ Bad - no protection
def api_call():
    response = requests.post(...)  # Can hit rate limit!
```

### 2. Use Batching for Embeddings
```python
# ✅ Good - 3 embeddings in 1 request
embeddings = get_embeddings_batch(["text1", "text2", "text3"])

# ❌ Bad - 3 requests used
emb1 = get_embedding("text1")
emb2 = get_embedding("text2")
emb3 = get_embedding("text3")
```

### 3. Check Rate Limit Stats
```python
from chatbot.modules.rate_limiter import get_rate_limit_stats

stats = get_rate_limit_stats()
if stats['remaining'] < 5:
    print("⚠️  Approaching rate limit, slow down!")
```

### 4. Handle Errors Gracefully
```python
try:
    result = api_call()
except Exception as e:
    if "429" in str(e):
        print("Rate limit exceeded even after retries")
        # Fall back to keyword search
    else:
        raise
```

### 5. Progress Reporting for Long Operations
```python
for i in range(0, 823, batch_size):
    batch = items[i:i + batch_size]
    results = process_batch(batch)
    
    # Show progress
    progress = (i + len(batch)) / 823 * 100
    print(f"Progress: {progress:.1f}% ({i + len(batch)}/823)")
    
    # Show rate limit stats
    stats = get_rate_limit_stats()
    print(f"Rate limit: {stats['recent_requests']}/{stats['max_requests']}")
```

## Testing

### Unit Test
```bash
python chatbot/modules/rate_limiter.py
```

### Integration Test
```bash
python test_openrouter.py
```

**Test 9 - Stress Test:**
- Sends 25 rapid requests
- Verifies automatic pacing
- Confirms no 429 errors with rate limiter

## Monitoring

### Real-Time Stats
```python
from chatbot.modules.rate_limiter import get_rate_limit_stats

stats = get_rate_limit_stats()
print(f"""
Max: {stats['max_requests']} req/{stats['time_window']}s
Used: {stats['recent_requests']}
Remaining: {stats['remaining']}
""")
```

### Logging
Rate limiter logs to standard Python logging:
```python
import logging
logging.basicConfig(level=logging.INFO)

# Will see rate limit warnings in logs
# [INFO] Rate limit approaching. Waiting 45.2s...
```

## Troubleshooting

### Issue: Still Getting 429 Errors

**Cause:** Multiple rate limiters or external API calls  
**Solution:**
```python
# Use the global limiter instance
from chatbot.modules.rate_limiter import openrouter_limiter

# Don't create new instances
# ❌ Bad
my_limiter = RateLimiter(20, 60)  # Separate tracking!

# ✅ Good
openrouter_limiter.wait_if_needed()
```

### Issue: Cache Generation Taking Too Long

**Expected:** 10-15 minutes for 823 techniques  
**If longer:** Check for repeated retries due to server errors

**Solution:**
```bash
# Check logs for retry patterns
python build_cache.py 2>&1 | grep "retry\|waiting"

# If many retries, try later when OpenRouter is less loaded
```

### Issue: Tests Timing Out

**Cause:** Aggressive rate limiting triggering waits  
**Solution:**
```python
# Increase timeout for batch operations
response = requests.post(..., timeout=120)  # 2 minutes
```

## Future Improvements

1. **Redis-based Rate Limiting:** Share rate limit state across processes
2. **Per-Model Limits:** Different limits for embedding vs LLM endpoints
3. **Adaptive Backoff:** Learn optimal delays from response times
4. **Queue System:** Background job queue for large batches
5. **Cost Tracking:** Monitor API usage and estimated costs

---

*Last Updated: 2026-04-25*  
*Module: chatbot/modules/rate_limiter.py*  
*Status: Implemented and Tested*
