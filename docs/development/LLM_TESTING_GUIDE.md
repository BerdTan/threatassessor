# LLM Provider Testing Guide

**Quick reference for testing multi-provider LLM functionality.**

---

## Prerequisites

### 1. Install Dependencies

```bash
pip install litellm boto3 anthropic
```

### 2. Configure Provider (Option 1: AWS Bedrock - Recommended)

**Get AWS Bedrock API Key:**
1. AWS Console → Amazon Bedrock
2. Click "API Keys" in left sidebar
3. "Create API Key" → Copy key (format: `AKabcdef123...`)
4. Enable Model Access: Anthropic Claude models in your region

**Update `.env`:**
```env
LLM_PROVIDER=bedrock
AWS_REGION=us-east-1
AWS_BEDROCK_API_KEY=AKabcdef123...
```

### 3. Configure Provider (Option 2: OpenRouter - Free Tier)

**Get OpenRouter API Key:**
1. Visit https://openrouter.ai/keys
2. Sign up / Log in
3. Create API key → Copy

**Update `.env`:**
```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
```

---

## Running Tests

### Quick Validation (All Providers)

```bash
# Activate virtual environment
source .venv/bin/activate

# Run test script
python3 scripts/test_llm_providers.py
```

**Expected output:**
```
============================================================
LLM Provider Test Suite
============================================================
Testing providers: ['bedrock']

✅ bedrock configuration valid
✅ bedrock generation successful
   Tokens: 15, Cost: $0.0001, Latency: 1.23s
✅ bedrock MITRE prompt successful
✅ Cost tracking successful
   Requests: 3, Tokens: 250, Cost: $0.0008

============================================================
Test Summary
============================================================
Total: 5 tests
Passed: 5 ✅
Failed: 0 ❌

🎉 All tests passed!

Results exported to: test_results_llm_providers.json
```

### Test Specific Provider

```bash
# Test only Bedrock
python3 scripts/test_llm_providers.py --provider bedrock

# Test only OpenRouter
python3 scripts/test_llm_providers.py --provider openrouter
```

### Test LLM as Judge (Verification Mode)

**Configure two providers in `.env`:**
```env
# Primary (cheap/fast for analysis)
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...

# Verifier (high-quality for verification)
LLM_VERIFIER_PROVIDER=bedrock
AWS_BEDROCK_API_KEY=AKabcdef123...
AWS_REGION=us-east-1
```

**Run verification test:**
```bash
python3 scripts/test_llm_providers.py --test-verify
```

**Expected output:**
```
============================================================
LLM as Judge Verification Test
============================================================
Primary: openrouter, Verifier: bedrock
Generating analysis...
Analysis generated (450 chars)
Running verification...
✅ Verification completed
   Analysis: openrouter (120 tokens, $0.0002)
   Verification: bedrock (85 tokens, $0.0003)
   Total cost: $0.0005
```

### Verbose Mode (Show Full Responses)

```bash
python3 scripts/test_llm_providers.py -v
```

---

## Test Coverage

The test script validates:

| Test | Description | Pass Criteria |
|------|-------------|---------------|
| **Provider Config** | Validates API keys, regions, endpoints | Config valid + credentials present |
| **Basic Generation** | Simple prompt ("Hello, World!") | Response length > 0 |
| **MITRE Prompt** | Threat modeling context (T1190) | Response contains "T1190" or "exploit" + "application" |
| **Cost Tracking** | Token usage and cost calculation | 3 requests tracked, tokens > 0 |
| **Fallback Mechanism** | Multi-provider graceful degradation | Falls back to secondary provider on failure |
| **LLM as Judge** | Two-model verification workflow | Analysis + verification both succeed |

---

## Troubleshooting

### Error: "Configuration validation failed"

**Problem:** Missing or invalid API key

**Solution:**
```bash
# Check .env file
cat .env | grep -E "(BEDROCK|OPENROUTER)_API_KEY"

# Verify key format
# Bedrock: AKabcdef123...
# OpenRouter: sk-or-v1-...
```

### Error: "Provider bedrock failed: AuthenticationError"

**Problem:** Bedrock API key invalid or expired

**Solution:**
1. AWS Console → Bedrock → API Keys
2. Check key status (Active / Expired)
3. Verify region matches `.env` (AWS_REGION)
4. Regenerate key if needed

### Error: "Model access denied"

**Problem:** Bedrock model not enabled in region

**Solution:**
1. AWS Console → Bedrock → Model Access
2. Select your region (top-right dropdown)
3. Enable "Anthropic Claude 4.x" models
4. Wait 2-5 minutes for activation

### Error: "LLM_VERIFIER_PROVIDER not configured"

**Problem:** Verification test requires two providers

**Solution:**
```env
# Add to .env
LLM_VERIFIER_PROVIDER=bedrock
AWS_BEDROCK_API_KEY=AKabcdef123...
```

### Verbose Debugging

```bash
# Enable debug logging
python3 scripts/test_llm_providers.py -v 2>&1 | tee test_debug.log

# Check LiteLLM logs
grep -i error test_debug.log
grep -i bedrock test_debug.log
```

---

## Test Results JSON

The script exports detailed results to `test_results_llm_providers.json`:

```json
{
  "total_tests": 5,
  "passed": 5,
  "failed": 0,
  "results": [
    {
      "test_name": "generate_bedrock",
      "passed": true,
      "duration": 1.23,
      "error": null,
      "details": {
        "provider": "bedrock",
        "model": "bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
        "tokens": 15,
        "cost": 0.00015,
        "latency": 1.21,
        "content_length": 14
      }
    }
  ]
}
```

**Use cases:**
- CI/CD integration (check `passed` count)
- Cost monitoring (sum `cost` across tests)
- Performance benchmarking (compare `latency` across providers)

---

## Integration with Architecture Analysis

### Test Before Running Ground Truth Generator

```bash
# 1. Validate LLM provider
python3 scripts/test_llm_providers.py --provider bedrock

# 2. If tests pass, run architecture analysis
python3 -m chatbot.main --gen-arch-truth tests/data/architectures/02_minimal_defended.mmd
```

### Cost Estimation

**Average costs (per request):**
- OpenRouter (Gemma 4): ~$0.0001 (free tier)
- AWS Bedrock (Claude Sonnet 4): ~$0.003
- Anthropic Direct (Claude Sonnet 4): ~$0.003

**Full architecture analysis:**
- Primary analysis (OpenRouter): ~$0.01
- Verification (Bedrock): ~$0.05
- **Total per architecture: ~$0.06**

Compare to:
- Pure Bedrock (no verification): ~$0.08
- Pure OpenRouter (no verification): ~$0.01 (lower quality)

---

## Next Steps

1. **Configure your provider** → Update `.env` with API keys
2. **Run basic test** → `python3 scripts/test_llm_providers.py`
3. **Test verification** → `python3 scripts/test_llm_providers.py --test-verify`
4. **Run architecture analysis** → See `README.md` for full workflow

---

## References

- **AWS Bedrock API Keys**: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html
- **OpenRouter Documentation**: https://openrouter.ai/docs
- **LiteLLM Provider List**: https://docs.litellm.ai/docs/providers
- **Architecture Document**: `docs/LLM_PROVIDER_ARCHITECTURE.md`

---

**Document Version:** 1.0  
**Date:** 2026-05-09  
**Status:** Testing Guide Complete
