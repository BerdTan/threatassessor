# Rate Limiting Quick Start

## The Problem

OpenRouter free tier: **20 requests per minute** (hard limit)  
Building embedding cache: **274 requests** needed  
Without rate limiting: ❌ **High risk of 429 errors and build failure**

## The Solution

All API calls now use `@rate_limited` decorator with:
- ✅ Automatic retry on 429 and 5xx errors
- ✅ Exponential backoff (2s, 4s, 8s, 16s, 32s)
- ✅ Smart pacing to stay under 20 req/min
- ✅ Real-time progress reporting

## Quick Usage

### Import
```python
from chatbot.modules.rate_limiter import rate_limited, get_rate_limit_stats
```

### Basic Pattern
```python
@rate_limited(max_retries=5, base_delay=2.0)
def call_api(text: str):
    response = requests.post(URL, json={"input": text})
    if response.status_code != 200:
        raise Exception(f"{response.status_code}: {response.text}")
    return response.json()

# Automatically handles rate limiting and retries
result = call_api("test")
```

### Check Stats
```python
stats = get_rate_limit_stats()
print(f"Used: {stats['recent_requests']}/{stats['max_requests']}")
```

## Testing

```bash
# Run full test suite (includes rate limit stress test)
python test_openrouter.py
```

Test 9 will send 25 rapid requests to verify rate limiting works correctly.

## Expected Timings

| Operation | Time |
|-----------|------|
| Single query | ~5s (no change) |
| Embedding cache generation | 10-15 min (was 3-5 min) |
| Rate limiter overhead | <100ms (negligible) |

## Key Rules

1. ⚠️  **ALL OpenRouter calls MUST use `@rate_limited`**
2. ⚠️  **Use batch processing (3-5 items) for embeddings**
3. ⚠️  **Raise exceptions on non-200 status codes**
4. ⚠️  **Don't catch exceptions inside decorated functions**

## Example Implementation

```python
import requests
from chatbot.modules.rate_limiter import rate_limited

EMBEDDING_URL = "https://openrouter.ai/api/v1/embeddings"
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"

@rate_limited(max_retries=5, base_delay=2.0)
def get_embeddings_batch(texts: list, api_key: str) -> list:
    """Get embeddings for batch of texts with rate limiting."""
    response = requests.post(
        EMBEDDING_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": EMBEDDING_MODEL,
            "input": texts
        },
        timeout=60
    )
    
    # Important: Raise exception for non-200 (triggers retry logic)
    if response.status_code != 200:
        raise Exception(f"{response.status_code}: {response.text}")
    
    return [item['embedding'] for item in response.json()['data']]

# Use it
texts = ["text1", "text2", "text3"]
embeddings = get_embeddings_batch(texts, api_key)  # Automatically rate-limited
```

## What Happens on Error

```
Request → 429 Rate Limit
  ↓
Wait 60s (minimum for rate limits)
  ↓
Retry (attempt 2/5)
  ↓
Success → Return result

OR

Request → 503 Server Error
  ↓
Wait 2s (exponential backoff)
  ↓
Retry (attempt 2/5) → 503 again
  ↓
Wait 4s
  ↓
Retry (attempt 3/5) → Success
  ↓
Return result
```

## Troubleshooting

**Still getting 429 errors?**
- Check you're using the global `openrouter_limiter` instance
- Verify all API calls use `@rate_limited` decorator
- Run test suite to verify setup

**Taking too long?**
- Cache generation: 10-15 min is expected (one-time)
- Check for server errors causing retries
- Verify batch size is 3-5 (not 1)

## More Information

See [RATE_LIMITING.md](RATE_LIMITING.md) for:
- Detailed implementation details
- Advanced usage patterns
- Performance optimization tips
- Complete troubleshooting guide
