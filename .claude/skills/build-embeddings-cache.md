---
skill: build-embeddings-cache
description: Generate MITRE technique embedding cache (one-time setup, ~3 minutes)
---

# Build Embeddings Cache Skill

This skill generates the embedding cache for all MITRE ATT&CK techniques. This is a one-time operation that takes approximately 3 minutes due to API rate limits.

## Usage

When user asks to:
- "build the embedding cache"
- "generate embeddings"
- "create the technique embeddings"
- "rebuild the cache"

## Implementation

```bash
cd /mnt/c/BACKUP/DEV-TEST
python -c "from chatbot.modules.mitre_embeddings import build_technique_embeddings, save_embeddings_json; from chatbot.modules.mitre import MitreHelper; from chatbot.modules import embeddings; mitre = MitreHelper(use_local=True); cache = build_technique_embeddings(mitre, embeddings); save_embeddings_json(cache, 'chatbot/data/technique_embeddings.json')"
```

## Expected Output

Should show:
- Progress: Processing techniques in batches
- Time: ~192 seconds (3.2 minutes)
- API calls: ~274 requests
- Output file: chatbot/data/technique_embeddings.json (~6-8MB)

## Success Criteria

File created at chatbot/data/technique_embeddings.json with valid JSON containing 823 technique embeddings.

## When to Run

- Initial setup (required)
- After updating enterprise-attack.json
- After changing embedding model
- If cache file is corrupted or missing

## Failure Handling

If build fails:
1. Check OPENROUTER_API_KEY in .env
2. Verify internet connectivity
3. Wait for rate limits to reset (may hit temporary limits on free tier)
4. Check OpenRouter service status
5. Ensure chatbot/data/ directory exists
