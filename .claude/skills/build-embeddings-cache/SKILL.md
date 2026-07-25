---
name: build-embeddings-cache
description: Generates the MITRE ATT&CK technique embedding cache (technique_embeddings.npz + technique_embeddings_meta.json). Required after updating enterprise-attack.json or if the cache is missing or corrupt. Takes ~3 minutes and makes ~274 API calls to OpenRouter. Run after /update-data completes a MITRE refresh.
allowed-tools: Bash(python3:*) Bash(ls:*) Read
compatibility: Requires OPENROUTER_API_KEY in .env and internet access. Verify the embedding model name is still a valid free-tier model on openrouter.ai before running.
---

# Build Embeddings Cache

Generates `chatbot/data/technique_embeddings.npz` (~3.3 MB, float16) + `technique_embeddings_meta.json` (~200 KB) from `chatbot/data/enterprise-attack.json`.

## Pre-flight

```bash
# Confirm MITRE data exists
ls -lh "$(git rev-parse --show-toplevel)/chatbot/data/enterprise-attack.json"

# Check current embedding model is still available on OpenRouter
# Free-tier models rotate — verify before running if it has been >30 days
grep -r "embed" "$(git rev-parse --show-toplevel)/chatbot/modules/mitre_embeddings.py" | grep "model"
```

## Run

```bash
cd "$(git rev-parse --show-toplevel)"
python3 -c "
from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json
from chatbot.modules.mitre import MitreHelper
mitre = MitreHelper(use_local=True)
cache = build_technique_embeddings(mitre)
save_embeddings_json(cache)
"
```

## Expected outcome

- Runtime: ~3 minutes (~274 requests, rate-limited)
- Output: `chatbot/data/technique_embeddings.npz` — should be ~3–4 MB (float16 compressed)
- Sidecar: `chatbot/data/technique_embeddings_meta.json` — ~200 KB
- Technique count: ≥835 embeddings

## Failure handling

| Symptom | Fix |
|---------|-----|
| `OPENROUTER_API_KEY` missing | Add to `.env` |
| Model 404 / not found | Update model name in `chatbot/modules/mitre_embeddings.py` |
| Rate limit errors | Wait and re-run — the script resumes from where it left off |
| Output file <1 MB | npz truncated; delete and re-run |
| Legacy `.json` still present | Safe to delete — `load_embeddings_json` prefers `.npz` automatically |
