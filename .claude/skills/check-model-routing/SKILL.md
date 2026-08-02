---
name: check-model-routing
description: Validate LLM model routing without making any API calls. Shows resolved model for every agent (HarnessModelGuardian), the embedding model, the TATB labeller, and which provider each routes to. Flags misconfiguration (wrong prefix, missing key, provider/model mismatch). Use before switching providers (Bedrock → OpenRouter cutover), after editing .env or user_config.json, or to confirm a standby config is wired correctly.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# check-model-routing — LLM Routing Validator

Shows the resolved model string for every agent and special-purpose model in TA,
without making any API calls. Validates that provider prefixes match the configured
`LLM_PROVIDER`, that API keys are present for required providers, and that the TATB
labeller uses a different model family from the main pipeline.

## Run

```bash
# Full routing report
python3 .claude/skills/check-model-routing/scripts/check-model-routing.py

# Show only misconfigurations (silent if all ok)
python3 .claude/skills/check-model-routing/scripts/check-model-routing.py --errors-only
```

## What it checks

1. **HarnessModelGuardian** — all 10 swarm agents (architect, tester, red_team,
   purple_team, blackhat, storycaster, scrum_master, moe_orchestrator,
   threat_analyst, ta_wiz)
2. **TATB labeller** (`AGENT_MODEL_TATB_LABELLER`) and its fallback
3. **Event detector** (`AGENT_MODEL_EVENT_DETECTOR` if set)
4. **Embedding model** (`OPENROUTER_EMBED_MODEL` → `settings.embedding.model` → default)
5. **Provider consistency** — warns if model prefix (bedrock/, openrouter/, anthropic/)
   doesn't match `LLM_PROVIDER`
6. **API key presence** — checks that the required key env var is set (not the value)
7. **TATB independence** — warns if labeller model family matches main pipeline family
   (defeats the independent-verifier design)

## When to use

- Before Bedrock → OpenRouter cutover: run with OpenRouter vars uncommented to
  verify routing before restarting the API
- After any `.env` or `user_config.json` edit
- At session start when working on model routing or provider config
