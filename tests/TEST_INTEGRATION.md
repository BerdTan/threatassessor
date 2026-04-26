# Integration Testing Guide

## Prerequisites Check

Your environment status:
- ✅ Python 3.12.3 installed
- ✅ .env file with OPENROUTER_API_KEY configured
- ✅ MITRE data present (44MB, 835 techniques)
- ✅ Rate limiter module working
- ✅ Virtual environment (.venv) exists

## Step 1: Install Dependencies

The test requires some packages. Install them:

```bash
# Activate virtual environment (if not already active)
source .venv/bin/activate

# Install from requirements.txt
pip install -r requirements.txt

# Install additional test dependencies
pip install numpy python-dotenv requests
```

**Verify installation:**
```bash
python3 << 'EOF'
import litellm
import numpy
from dotenv import load_dotenv
print("✅ All dependencies installed!")
EOF
```

## Step 2: Quick Component Tests

Test individual components before full integration:

### 2.1 Test Rate Limiter

```bash
python3 << 'EOF'
from chatbot.modules.rate_limiter import rate_limited, get_rate_limit_stats

# Check rate limiter
stats = get_rate_limit_stats()
print(f"✅ Rate limiter: {stats['recent_requests']}/{stats['max_requests']} requests")

# Test decorator
@rate_limited(max_retries=3, base_delay=1.0)
def test_function():
    print("✅ Rate limited function works!")
    return "success"

result = test_function()
print(f"✅ Result: {result}")
EOF
```

**Expected output:**
```
✅ Rate limiter: 0/20 requests
✅ Rate limited function works!
✅ Result: success
```

### 2.2 Test MITRE Data

```bash
python3 << 'EOF'
from chatbot.modules.mitre import MitreHelper

mitre = MitreHelper(use_local=True)
techniques = mitre.get_techniques()
tactics = mitre.get_tactics()

print(f"✅ Loaded {len(techniques)} techniques")
print(f"✅ Loaded {len(tactics)} tactics")

# Test finding a technique
tech = mitre.find_technique("T1059")
if tech:
    print(f"✅ Found: {tech.get('name')}")
EOF
```

**Expected output:**
```
✅ Loaded 835 techniques
✅ Loaded 14 tactics
✅ Found: Command and Scripting Interpreter
```

### 2.3 Test OpenRouter Connection

```bash
python3 << 'EOF'
import os
from dotenv import load_dotenv
import requests

load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")

if not api_key:
    print("❌ OPENROUTER_API_KEY not found")
    exit(1)

print(f"✅ API key loaded (length: {len(api_key)})")

# Test connection
response = requests.get(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=10
)

if response.status_code == 200:
    print("✅ OpenRouter API connection successful!")
else:
    print(f"❌ API error: {response.status_code}")
EOF
```

**Expected output:**
```
✅ API key loaded (length: 73)
✅ OpenRouter API connection successful!
```

## Step 3: Run Full Integration Test

Now run the comprehensive test suite:

```bash
python3 test_openrouter.py
```

### What the test does:

**Test 1:** Environment configuration  
**Test 2:** LiteLLM availability  
**Test 3:** OpenRouter embedding API (with rate limiting)  
**Test 4:** Batch embeddings (with rate limiting)  
**Test 5:** Cosine similarity  
**Test 6:** OpenRouter LLM API (with rate limiting)  
**Test 7:** LiteLLM routing  
**Test 8:** MITRE technique embeddings (with rate limiting)  
**Test 9:** Rate limit stress test (25 rapid requests)

### Expected duration:
- **Quick tests (1-8):** ~15-30 seconds
- **Stress test (9):** Optional, can skip with Ctrl+C

### Success indicators:
```
✅ All tests passed! Rate limiting is working correctly.

Key findings:
- OpenRouter free tier: 20 requests/minute confirmed
- Rate limiter: Automatic pacing and retry on 429 errors
- Exponential backoff: 2s, 4s, 8s, 16s, 32s delays on errors
```

## Step 4: Test Skills

Once integration tests pass, test the skills:

### 4.1 Test Quick Test Skill (NEW!)

```bash
# Fast 15-second check of all core components
/quick-test
```

This is perfect for:
- Starting a new session
- Quick sanity checks
- Verifying after small changes

### 4.2 Test Full Validation Skill

```bash
# Comprehensive integration tests (2-3 min)
/validate-integration
```

### 4.2 Test MITRE Update Skill (optional)

```bash
# Downloads latest MITRE data (safe, creates backup)
/update-mitre-data
```

**Note:** This will download ~44MB and back up your current file.

### 4.3 Test Embedding Cache Build (only if needed)

```bash
# Generates embedding cache (takes 10-15 min)
# Only run this if:
# - You don't have technique_embeddings.json
# - You updated MITRE data
# - Cache is corrupted

/build-embeddings-cache
```

## Troubleshooting

### Issue: "Module not found" errors

**Solution:**
```bash
# Make sure you're in the project directory
cd /mnt/c/BACKUP/DEV-TEST

# Activate virtual environment
source .venv/bin/activate

# Verify Python path
python3 -c "import sys; print(sys.path)"

# Install dependencies
pip install -r requirements.txt
```

### Issue: "OPENROUTER_API_KEY not found"

**Solution:**
```bash
# Check .env file exists
cat .env | grep OPENROUTER

# If not, create/edit .env:
echo "OPENROUTER_API_KEY=sk-or-v1-xxxxx" > .env
```

### Issue: Rate limit errors (429)

**Expected behavior:** Rate limiter should automatically retry with delays.

If you see:
```
⏱️  Rate limit: waiting 60.0s (max 20 req/60s)
⚠️  Rate limit hit! Waiting 60.0s... (retry 1/5)
```

This is **normal** and the rate limiter is working correctly!

### Issue: Tests take too long

**Normal timing:**
- Tests 1-8: 30-60 seconds
- Test 9 (stress test): Can skip with Ctrl+C after 5 seconds

**If longer than 5 minutes:**
- Check internet connection
- Verify OpenRouter service status: https://openrouter.ai/
- Check if you're hitting rate limits (expected on free tier)

## Quick Validation Commands

After running full tests, use these for quick checks:

```bash
# Check rate limiter module
python3 -c "from chatbot.modules.rate_limiter import get_rate_limit_stats; print(get_rate_limit_stats())"

# Check MITRE data
python3 -c "from chatbot.modules.mitre import MitreHelper; m = MitreHelper(use_local=True); print(f'{len(m.get_techniques())} techniques')"

# Check if embedding cache exists
ls -lh chatbot/data/technique_embeddings.json 2>/dev/null || echo "Cache not generated yet"
```

## Success Criteria

You know integration is working when:

✅ All 9 tests pass (or 8 if you skip stress test)  
✅ Rate limiter shows correct stats (X/20 requests)  
✅ MITRE data loads (835 techniques)  
✅ OpenRouter API responds successfully  
✅ No unexpected errors in logs  

## Next Steps

After successful integration testing:

1. **Optional:** Generate embedding cache
   ```bash
   /build-embeddings-cache  # Takes 10-15 min
   ```

2. **Start using:** You can now begin implementing Phase 1 modules
   - embeddings.py
   - mitre_embeddings.py
   - llm_mitre_analyzer.py

3. **Regular maintenance:** Use `/update-mitre-data` quarterly when MITRE releases updates

---

**Need help?** See:
- [QUICK_START.md](QUICK_START.md) - General quick start (same folder)
- [TESTING.md](TESTING.md) - Comprehensive testing guide
- [RATE_LIMITING.md](RATE_LIMITING.md) - Rate limiting details
