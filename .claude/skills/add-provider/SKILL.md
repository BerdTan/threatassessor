---
name: add-provider
description: Add a new LLM provider to ThreatAssessor by editing agentic/providers.py (the single source of truth). Validates the manifest entry is complete, adds the LLMProvider enum value if needed, appends the .env.example block, and runs /check-model-routing to confirm routing resolves correctly. No elif chains to touch — all config flows from the manifest. Pass provider name, API key env var, base URL, and a test model string.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# add-provider — Add a New LLM Provider

Adds a new provider to ThreatAssessor. All provider config lives in
`agentic/providers.PROVIDER_MANIFEST` — this skill edits that one file,
validates the entry, and confirms routing works.

## What "adding a provider" means

In TA, a provider is an LLM API endpoint accessible via LiteLLM. The manifest
entry defines: model prefix, API key env var, base URL, override env var,
default models (default/high_quality/fast), and cost estimate.

After adding to the manifest:
- `LLMClient.from_env()` and `validate()` work automatically
- `_call_litellm()` routes correctly via `api_base` and `extra_headers`
- `ProviderRegistry` (for embeddings) includes it
- `check-model-routing` validates the API key is present

## Run

```bash
# Show current providers and manifest
python3 .claude/skills/add-provider/scripts/add-provider.py --list

# Add a new provider (interactive — shows entry before writing)
python3 .claude/skills/add-provider/scripts/add-provider.py \
  --name doubleword \
  --api-key-env DOUBLEWORD_API_KEY \
  --base-url https://api.doubleword.ai/v1 \
  --model-prefix openai/ \
  --default-model openai/doubleword-v1

# Add Ollama (no API key, local endpoint)
python3 .claude/skills/add-provider/scripts/add-provider.py \
  --name ollama \
  --base-url http://localhost:11434/v1 \
  --model-prefix ollama/ \
  --default-model ollama/llama3.3 \
  --no-key
```

## After adding

1. Add the LLMProvider enum value to `agentic/llm_client.py` (one line)
2. Set the API key env var in `.env`
3. Set `LLM_PROVIDER=<name>` in `.env`
4. Run: `python3 .claude/skills/check-model-routing/scripts/check-model-routing.py`
5. Restart API: `./scripts/api/api_restart.sh`
