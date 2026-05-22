# LLM Configuration Update - MVP Specification

**Date:** 2026-05-22  
**Issue:** Hardcoded LLM model names in MVP_SPECIFICATION.md  
**Status:** ✅ Resolved

---

## Problem

MVP_SPECIFICATION.md contained hardcoded LLM model references that didn't reflect the actual `.env` configuration:

**Hardcoded references found:**
- "Gemma 4-26B" (incorrect model name)
- "Gemma → Nemotron → Bedrock" (not all models used)
- "Nemotron" for embeddings (correct but not explained)

**Issues:**
1. Specification didn't match actual configuration
2. No explanation of how to change LLM models
3. No reference to `.env` file for configuration
4. Model names inconsistent with actual models used

---

## Solution

### 1. Added Comprehensive LLM Configuration Section ✅

**New section in MVP_SPECIFICATION.md:**
- **Provider Architecture** - Multi-provider with fallback
- **Primary LLM** - Main analysis model (configurable)
- **Fallback LLM** - Automatic failover model
- **Verifier LLM** - Phase 3C validation model
- **Embedding Model** - Fixed semantic search model
- **Supported Providers** - All 5 providers listed
- **Fallback Chain** - How automatic failover works
- **Changing LLM Models** - Step-by-step guide
- **Model Selection Guidelines** - Recommendations
- **Cost Tracking** - How costs are tracked

### 2. Updated Hardcoded References ✅

**Before:**
```
[LLM Analyzer] (Gemma 4-26B)
```

**After:**
```
[LLM Analyzer] (Primary LLM from .env)

Note: Primary LLM configured via LLM_PROVIDER in .env
Default: nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free (OpenRouter)
Fallback: Claude Sonnet 4 (AWS Bedrock)
```

**Before:**
```
- ✅ Automatic fallback (Gemma → Nemotron → Bedrock)
```

**After:**
```
- ✅ Automatic fallback (Primary → Fallback providers, configured via .env)
```

### 3. Added Configuration Examples ✅

**Added .env configuration snippets:**

```bash
# Primary LLM
LLM_PROVIDER=openrouter
OPENROUTER_ACTIVE_MODELS=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free

# Fallback LLM
LLM_FALLBACK_PROVIDERS=bedrock
BEDROCK_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0

# Verifier LLM (Phase 3C)
LLM_VERIFIER_PROVIDER=bedrock
```

---

## Changes Made

### docs/specs/MVP_SPECIFICATION.md

**Added (Line ~226):**
- New section: "## LLM Configuration" (~200 lines)
  - Provider architecture explanation
  - Primary/Fallback/Verifier/Embedding model details
  - Configuration examples from .env
  - Supported providers list
  - Fallback chain explanation
  - Model changing guide
  - Model selection guidelines
  - Cost tracking information

**Updated (Lines 210, 228, 231, 725):**
- Replaced hardcoded "Gemma 4-26B" with "Primary LLM from .env"
- Replaced "Gemma → Nemotron → Bedrock" with "Primary → Fallback providers"
- Added .env configuration references
- Added default model specifications

**Updated (Line 240):**
- Added LLM Configuration subsection under Phase 1
- Listed all .env variables for LLM configuration
- Added configuration code block example

---

## Current LLM Configuration

### Actual Models Used (.env)

**Primary LLM (Analysis):**
- Provider: OpenRouter
- Model: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
- Cost: Free tier
- Use: Main threat analysis, attack path construction

**Fallback LLM (Reliability):**
- Provider: AWS Bedrock
- Model: `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Cost: Pay-per-use (~$0.05 per analysis)
- Use: Automatic failover when primary unavailable

**Verifier LLM (Phase 3C):**
- Provider: AWS Bedrock (same as fallback)
- Model: `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Cost: Pay-per-use (~$0.12 per validation)
- Use: LLM as Judge/Critic validation

**Embedding Model (Fixed):**
- Provider: OpenRouter
- Model: `nvidia/llama-nemotron-embed-vl-1b-v2:free`
- Dimensions: 2048
- Cost: Free tier
- Use: Semantic search (MITRE technique matching)

---

## How to Change LLM Models

### Change Primary Model

1. Edit `.env`:
   ```bash
   OPENROUTER_ACTIVE_MODELS=anthropic/claude-3.5-sonnet
   ```

2. Restart application

**No code changes needed!**

### Change Provider

1. Edit `.env`:
   ```bash
   LLM_PROVIDER=bedrock
   BEDROCK_MODEL=us.anthropic.claude-sonnet-4-20250514-v1:0
   ```

2. Configure provider credentials (AWS keys, etc.)

3. Restart application

### Disable Fallback

```bash
LLM_FALLBACK_PROVIDERS=
```

---

## Benefits

### Before Update ✗
- Hardcoded model names in spec
- No explanation of configuration
- Unclear how to change models
- Inconsistent with actual .env settings
- "Gemma 4-26B" mentioned (incorrect)

### After Update ✓
- References .env configuration
- Comprehensive LLM configuration section
- Step-by-step model changing guide
- Accurate model names
- All 5 providers documented
- Cost tracking explained
- Model selection guidelines provided

---

## Documentation

**Updated Files:**
- `docs/specs/MVP_SPECIFICATION.md` - Added LLM Configuration section
- `html/roadmap.html` - Regenerated with updates

**Related Documentation:**
- `.env.example` - Example configuration
- `agentic/llm_client.py` - Implementation
- `docs/implementation/llm_client/` - LLM client documentation

---

## Verification

```bash
# Check updated spec
grep -A 5 "LLM Configuration" docs/specs/MVP_SPECIFICATION.md

# Verify .env references
grep "\.env" docs/specs/MVP_SPECIFICATION.md | wc -l
# Output: 12 references (good!)

# Regenerate HTML
make docs

# View updated roadmap
open html/roadmap.html
```

---

## Summary

✅ **Resolved hardcoded LLM references**
✅ **Added comprehensive LLM configuration section**
✅ **Linked to .env configuration**
✅ **Documented all 5 providers**
✅ **Added model changing guide**
✅ **Explained fallback chain**
✅ **Added cost tracking info**
✅ **Regenerated HTML roadmap**

**Result:** MVP_SPECIFICATION.md now accurately reflects configurable LLM architecture with clear .env-based configuration.

---

**Status:** ✅ Complete  
**Date:** 2026-05-22  
**Regenerated HTML:** html/roadmap.html
