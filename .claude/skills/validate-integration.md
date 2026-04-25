---
skill: validate-integration
description: Run OpenRouter integration tests to validate API connectivity, embeddings, LLM, and MITRE integration
---

# Validate Integration Skill

This skill runs the comprehensive integration test suite to validate:
- OpenRouter API connectivity
- Embedding generation (nvidia/llama-nemotron-embed-vl-1b-v2:free)
- LLM responses (google/gemma-4-26b-a4b-it:free)
- MITRE data loading
- Semantic search functionality

## Usage

When user asks to:
- "validate the setup"
- "test the integration"
- "check if everything works"
- "verify OpenRouter connection"
- "run integration tests"

## Implementation

```bash
cd /mnt/c/BACKUP/DEV-TEST
python test_openrouter.py
```

## Expected Output

Should show:
- ✅ Environment configuration validated
- ✅ OpenRouter API key working
- ✅ Embedding API functional (response time, dimensions, cost)
- ✅ LLM API functional (response time, quality check)
- ✅ MITRE integration (823 techniques loaded)
- ✅ Semantic search working

## Success Criteria

All checks pass with ✅ marks.
Report confidence level at end (should be 95%+).

## Failure Handling

If any checks fail:
1. Check .env file has OPENROUTER_API_KEY
2. Verify internet connectivity
3. Check OpenRouter service status
4. See docs/OPERATIONS.md troubleshooting section
