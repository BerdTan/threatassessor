---
name: check-deprecation
description: Checks the codebase for deprecated imports, broken module imports, and common anti-patterns. Use after major refactoring, after adding new modules, or before committing large changes. Takes ~2 minutes. Non-destructive — read-only.
allowed-tools: Bash(python3:*) Bash(grep:*) Bash(pytest:*) Bash(source:*)
---

# Check Deprecation

Runs 5 checks in sequence. Exit code equals the number of issues found.

## Run

```bash
bash "$(git rev-parse --show-toplevel)/.claude/skills/check-deprecation/scripts/check-deprecation.sh
```

## What it checks

1. **Deprecated import patterns** — `from agentic.llm import *` (should be `from agentic.llm_client import LLMClient`)
2. **Module imports** — attempts `import <module>` for all tracked modules; reports failures
3. **Deprecation warnings** — runs key modules with `DeprecationWarning` as error
4. **Test suite** — runs `tests/unit/` with pytest
5. **Anti-patterns** — direct `litellm.completion()` calls; raw `os.getenv("OPENROUTER_API_KEY")` outside `helper.py`

## Tracked modules

Core: `chatbot.modules.ground_truth_generator`, `chatbot.modules.threat_analyst`, `chatbot.modules.threat_report`, `chatbot.modules.exhaustive_mitigation_mapper`, `chatbot.modules.self_validation`, `chatbot.modules.residual_risk`, `chatbot.modules.completeness_validator`, `chatbot.modules.mitre`, `chatbot.modules.mitre_embeddings`, `chatbot.modules.embeddings`, `chatbot.modules.rate_limiter`

Patterns: `chatbot.modules.patterns.ai_pattern`, `chatbot.modules.pattern_registry`

SSP: `chatbot.modules.ssp_mapper`

API: `chatbot.api.app`, `chatbot.api.routes.streaming`, `chatbot.api.routes.reports`

LLM: `agentic.llm_client`, `agentic.helper`

## Fix guide

```python
# Deprecated
from agentic.llm import generate_response

# Correct
from agentic.llm_client import LLMClient
client = LLMClient()
response = client.generate(prompt="...")
```
