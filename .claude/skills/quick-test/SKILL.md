---
name: quick-test
description: Runs a fast ~15 second integration sanity check — verifies dependencies, rate limiter, MITRE data load (≥835 techniques), OpenRouter API key, API connection, and one real embedding call. Use at session start or after installing dependencies to confirm everything is working before coding.
allowed-tools: Bash(python3:*) Bash(source:*)
compatibility: Requires OPENROUTER_API_KEY in .env and internet access. Makes 1 real API call (counts toward OpenRouter rate limit).
---

# Quick Test

```bash
cd "$(git rev-parse --show-toplevel)" && bash .claude/skills/quick-test/scripts/quick-test.sh
```

## What it tests

| Check | Pass criteria |
|-------|--------------|
| Dependencies | litellm, numpy, dotenv, requests importable |
| Rate limiter | Module loads, stats accessible |
| MITRE data | ≥835 techniques loaded from local file |
| API key | `OPENROUTER_API_KEY` set and >10 chars |
| OpenRouter connection | HTTP 200 on `/api/v1/models` |
| Embedding call | 200 response, dimensions > 0 |

## Failure fixes

| Error | Fix |
|-------|-----|
| Missing dep | `pip install litellm numpy python-dotenv requests` |
| API key missing | Add `OPENROUTER_API_KEY=sk-or-v1-...` to `.env` |
| MITRE not found | Run `/update-data` (section 1) |
| Embedding model error | Verify model name still valid on openrouter.ai; update in `chatbot/modules/mitre_embeddings.py` |
| Connection refused | Check internet; check OpenRouter status page |

## Related skills

- `/build-embeddings-cache` — regenerate embeddings after MITRE update
- `/check-deprecation` — deeper module import + deprecation check (~2 min)
- `/update-data` — refresh MITRE/ATLAS/SSP/ARC data files
