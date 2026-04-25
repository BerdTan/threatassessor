---
skill: quick-test
description: Run quick integration test to verify core components (rate limiter, MITRE data, OpenRouter API)
---

# Quick Test Skill

This skill runs a fast integration test (~15 seconds) to verify all core components are working correctly without running the full 2-3 minute test suite.

## Usage

When user asks to:
- "run quick test"
- "quick check"
- "verify setup"
- "test the basics"
- "sanity check"

## What This Tests

1. ✅ Dependencies installed (litellm, numpy, dotenv, requests)
2. ✅ Rate limiter module loads and works
3. ✅ MITRE data loads (technique count)
4. ✅ OpenRouter API key configured
5. ✅ OpenRouter API connection working
6. ✅ Real API call with rate limiting (embedding request)

## Implementation

```bash
#!/bin/bash
set -e

cd /mnt/c/BACKUP/DEV-TEST

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║              QUICK INTEGRATION TEST                                   ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""

# Activate virtual environment if exists
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

echo "🔍 Step 1: Check Dependencies"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 << 'PYEOF'
import sys
deps = ['litellm', 'numpy', 'dotenv', 'requests']
missing = []
for dep in deps:
    try:
        if dep == 'dotenv':
            __import__('dotenv')
        else:
            __import__(dep)
        print(f"✅ {dep}")
    except ImportError:
        print(f"❌ {dep} - MISSING")
        missing.append(dep)

if missing:
    print(f"\n⚠️  Run: pip install {' '.join(missing)}")
    sys.exit(1)
PYEOF

echo ""
echo "🧪 Step 2: Test Core Components"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Testing rate limiter..."
python3 << 'PYEOF'
from chatbot.modules.rate_limiter import get_rate_limit_stats
stats = get_rate_limit_stats()
print(f"✅ Rate limiter: {stats['recent_requests']}/{stats['max_requests']} requests")
PYEOF

echo ""
echo "Testing MITRE data..."
python3 << 'PYEOF'
from chatbot.modules.mitre import MitreHelper
m = MitreHelper(use_local=True)
techs = m.get_techniques()
tactics = m.get_tactics()
print(f"✅ Loaded {len(techs)} techniques, {len(tactics)} tactics")
PYEOF

echo ""
echo "Testing OpenRouter API key..."
python3 << 'PYEOF'
import os
import sys

if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

key = os.getenv("OPENROUTER_API_KEY")
if key and len(key) > 10:
    print(f"✅ API key configured ({len(key)} chars)")
else:
    print("❌ API key not found or invalid")
    sys.exit(1)
PYEOF

echo ""
echo "Testing API connection..."
python3 << 'PYEOF'
import os
import requests
import sys

if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

api_key = os.getenv("OPENROUTER_API_KEY")
response = requests.get(
    "https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=10
)

if response.status_code == 200:
    models = len(response.json().get('data', []))
    print(f"✅ Connected to OpenRouter ({models} models available)")
else:
    print(f"❌ API error: {response.status_code}")
    sys.exit(1)
PYEOF

echo ""
echo "🚀 Step 3: Test Rate Limiter with Real API Call"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 << 'PYEOF'
import os
import sys
import time

sys.path.insert(0, '.')

if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#') and '=' in line:
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

from chatbot.modules.rate_limiter import rate_limited, get_rate_limit_stats
import requests

api_key = os.getenv("OPENROUTER_API_KEY")

@rate_limited(max_retries=3, base_delay=2.0)
def test_embedding():
    response = requests.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "nvidia/llama-nemotron-embed-vl-1b-v2:free",
            "input": "test query"
        },
        timeout=30
    )
    
    if response.status_code != 200:
        raise Exception(f"{response.status_code}: {response.text[:100]}")
    
    return response.json()

try:
    start = time.time()
    result = test_embedding()
    elapsed = time.time() - start
    
    embedding = result['data'][0]['embedding']
    stats = get_rate_limit_stats()
    
    print(f"✅ Embedding API call successful")
    print(f"   Response time: {elapsed:.2f}s")
    print(f"   Dimensions: {len(embedding)}")
    print(f"   Rate limit: {stats['recent_requests']}/{stats['max_requests']} requests")
    
except Exception as e:
    print(f"❌ API call failed: {e}")
    sys.exit(1)
PYEOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ QUICK TEST COMPLETE - ALL SYSTEMS OPERATIONAL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Verified:"
echo "  ✓ Dependencies installed"
echo "  ✓ Rate limiter working (with real API call)"
echo "  ✓ MITRE data loaded"
echo "  ✓ OpenRouter API connected"
echo ""
echo "Next steps:"
echo "  • Run full test:     python3 test_openrouter.py"
echo "  • Try other skills:  /validate-integration"
echo "  • Start coding:      Ready for Phase 1 implementation"
echo ""
```

## Expected Output

```
╔═══════════════════════════════════════════════════════════════════════╗
║              QUICK INTEGRATION TEST                                   ║
╚═══════════════════════════════════════════════════════════════════════╝

🔍 Step 1: Check Dependencies
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ litellm
✅ numpy
✅ dotenv
✅ requests

🧪 Step 2: Test Core Components
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Testing rate limiter...
✅ Rate limiter: 0/20 requests

Testing MITRE data...
✅ Loaded 835 techniques, 14 tactics

Testing OpenRouter API key...
✅ API key configured (73 chars)

Testing API connection...
✅ Connected to OpenRouter (355 models available)

🚀 Step 3: Test Rate Limiter with Real API Call
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Embedding API call successful
   Response time: 0.91s
   Dimensions: 2048
   Rate limit: 1/20 requests

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ QUICK TEST COMPLETE - ALL SYSTEMS OPERATIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Verified:
  ✓ Dependencies installed
  ✓ Rate limiter working (with real API call)
  ✓ MITRE data loaded
  ✓ OpenRouter API connected

Next steps:
  • Run full test:     python3 test_openrouter.py
  • Try other skills:  /validate-integration
  • Start coding:      Ready for Phase 1 implementation
```

## Success Criteria

All checks pass:
- ✅ Dependencies installed
- ✅ Rate limiter module loads
- ✅ MITRE data loads (835 techniques)
- ✅ API key configured
- ✅ OpenRouter connection works
- ✅ Rate-limited API call succeeds

## Timing

- **Expected:** ~15 seconds
- Much faster than full test (2-3 minutes)
- Makes one real API call (embedding request)

## When to Use

**Use quick-test when:**
- ✅ Starting a new session (verify everything works)
- ✅ After installing dependencies
- ✅ After updating MITRE data
- ✅ Before starting development
- ✅ Quick sanity check

**Use full test (validate-integration) when:**
- 🧪 Running comprehensive validation
- 🧪 Before deployment
- 🧪 After major changes
- 🧪 Testing rate limit stress scenarios

## Failure Handling

**Dependencies missing:**
```bash
pip install litellm numpy python-dotenv requests
```

**API key not found:**
```bash
# Check .env file
cat .env | grep OPENROUTER_API_KEY

# If missing, add it:
echo "OPENROUTER_API_KEY=sk-or-v1-xxxxx" >> .env
```

**MITRE data missing:**
```bash
# Update MITRE data
/update-mitre-data
```

**API connection fails:**
- Check internet connectivity
- Verify OpenRouter service: https://openrouter.ai/
- Check API key is valid

## Comparison with Other Skills

| Skill | Time | Tests | Use Case |
|-------|------|-------|----------|
| `/quick-test` | ~15s | Basic + 1 API call | Quick validation |
| `/validate-integration` | 2-3min | Full suite (9 tests) | Comprehensive check |
| `/build-embeddings-cache` | 10-15min | Cache generation | After MITRE update |
| `/update-mitre-data` | ~30s | MITRE download | Quarterly update |

## Notes

- Makes **1 real API call** (counts toward 20 req/min limit)
- Tests actual rate limiter behavior
- Faster feedback than full test suite
- Good for rapid iteration during development
