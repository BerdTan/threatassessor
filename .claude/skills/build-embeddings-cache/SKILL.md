---
name: build-embeddings-cache
description: Generates the MITRE ATT&CK technique embedding cache (technique_embeddings.json). Required after updating enterprise-attack.json or if the cache is missing or corrupt. Takes ~3 minutes and makes ~274 API calls to OpenRouter. Run after /update-data completes a MITRE refresh.
allowed-tools: Bash(python3:*) Bash(ls:*) Read
compatibility: Requires OPENROUTER_API_KEY in .env and internet access. Verify the embedding model name is still a valid free-tier model on openrouter.ai before running.
---

# Build Embeddings Cache

Generates `chatbot/data/technique_embeddings.json` (~45 MB) from `chatbot/data/enterprise-attack.json`.

## Pre-flight

```bash
# Confirm MITRE data exists
ls -lh /mnt/c/BACKUP/DEV-TEST/chatbot/data/enterprise-attack.json

# Check current embedding model is still available on OpenRouter
# Visit https://openrouter.ai/models and search for the model name below
# Free-tier models rotate — verify before running if it has been >30 days
grep -r "embed" /mnt/c/BACKUP/DEV-TEST/chatbot/modules/mitre_embeddings.py | grep "model"
```

## Run

```bash
cd /mnt/c/BACKUP/DEV-TEST
python3 -c "
from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json
from chatbot.modules.mitre import MitreHelper
from chatbot.modules import embeddings
mitre = MitreHelper(use_local=True)
cache = build_technique_embeddings(mitre, embeddings)
save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')
"
```

## Expected outcome

- Runtime: ~3 minutes (~274 requests, rate-limited)
- Output: `chatbot/data/technique_embeddings.json` — should be ≥40 MB
- Technique count: ≥835 embeddings

## Failure handling

| Symptom | Fix |
|---------|-----|
| `OPENROUTER_API_KEY` missing | Add to `.env` |
| Model 404 / not found | Update model name in `chatbot/modules/mitre_embeddings.py` |
| Rate limit errors | Wait and re-run — the script resumes from where it left off |
| Output file <10 MB | JSON truncated; delete and re-run |
