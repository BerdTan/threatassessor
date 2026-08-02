"""
Provider Manifest — single source of truth for all LLM providers in ThreatAssessor.

Adding a new provider requires editing ONLY this file:
  1. Add an entry to PROVIDER_MANIFEST
  2. Add the API key env var to .env.example
  3. Run: python3 .claude/skills/check-model-routing/scripts/check-model-routing.py

Everything else (LLMProvider enum, ProviderConfig.from_env(), validate(),
_call_litellm(), ProviderRegistry, check-model-routing) reads this manifest.

Manifest schema per entry:
  name          str   — provider key, matches LiteLLM model prefix (e.g. "openrouter")
  model_prefix  str   — prefix on model strings (e.g. "openrouter/"). Empty = no prefix (Bedrock SigV4).
  api_key_env   str|None — env var name for the API key. None = no key (GCP credentials, local).
  base_url      str   — default base URL for the provider API.
  base_url_env  str|None — env var that overrides base_url at runtime.
  region_env    str|None — env var for region (Bedrock / GCP).
  extra_headers dict  — additional HTTP headers to include in every call.
  litellm_kwargs dict — extra kwargs passed directly to litellm.completion().
  models        dict  — {quality_tier: model_string} (default/high_quality/fast).
  cost_per_1k   float|None — approximate cost USD per 1k tokens (for tracking).
  env_example   str   — comment block to add to .env.example when provider is added.
  active        bool  — False = defined but not yet enabled (no enum value created).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Provider manifest — the only place to edit when adding a new provider
# ---------------------------------------------------------------------------

PROVIDER_MANIFEST: Dict[str, Dict[str, Any]] = {

    "openrouter": {
        "model_prefix":  "openrouter/",
        "api_key_env":   "OPENROUTER_API_KEY",
        "base_url":      "https://openrouter.ai/api/v1",
        "base_url_env":  "OPENROUTER_BASE_URL",
        "region_env":    None,
        "extra_headers": {
            "HTTP-Referer": "http://localhost:8000",
            "X-Title":      "MITRE-ThreatModeling",
        },
        "litellm_kwargs": {},
        "models": {
            "default":      "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "high_quality": "openrouter/anthropic/claude-sonnet-4",
            "fast":         "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        },
        "cost_per_1k": None,   # varies by model
        "active": True,
        "env_example": (
            "# OpenRouter API key — https://openrouter.ai/keys\n"
            "OPENROUTER_API_KEY=sk-or-v1-your-key-here\n"
            "# Optional: override base URL for LiteLLM proxy\n"
            "# OPENROUTER_BASE_URL=http://localhost:4000\n"
        ),
    },

    "bedrock": {
        "model_prefix":  "bedrock/",
        "api_key_env":   "AWS_BEDROCK_API_KEY",
        "base_url":      "",           # SigV4 — LiteLLM handles endpoint internally
        "base_url_env":  None,
        "region_env":    "AWS_REGION",
        "extra_headers": {},
        "litellm_kwargs": {},          # aws_region_name added dynamically from region_env
        "models": {
            # Resolved at runtime from BEDROCK_MODEL / BEDROCK_MODEL_FAST env vars
            "default":      os.getenv("BEDROCK_MODEL",      "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
            "high_quality": os.getenv("BEDROCK_MODEL",      "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
            "fast":         os.getenv("BEDROCK_MODEL_FAST", "bedrock/us.anthropic.claude-haiku-4-20250514-v1:0"),
        },
        "cost_per_1k": 0.003,
        "active": True,
        "env_example": (
            "# AWS Bedrock — bearer token from AWS Console → Bedrock → API Keys\n"
            "AWS_BEDROCK_API_KEY=ABSK...\n"
            "AWS_REGION=us-east-1\n"
            "BEDROCK_MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0\n"
            "BEDROCK_MODEL_FAST=us.anthropic.claude-haiku-4-20250514-v1:0\n"
        ),
    },

    "anthropic": {
        "model_prefix":  "anthropic/",
        "api_key_env":   "ANTHROPIC_API_KEY",
        "base_url":      "https://api.anthropic.com",
        "base_url_env":  "ANTHROPIC_BASE_URL",
        "region_env":    None,
        "extra_headers": {},
        "litellm_kwargs": {},
        "models": {
            "default":      "anthropic/claude-sonnet-4-20250514",
            "high_quality": "anthropic/claude-opus-4-20250514",
            "fast":         "anthropic/claude-haiku-4-20250514",
        },
        "cost_per_1k": 0.003,
        "active": True,
        "env_example": (
            "# Anthropic direct API — https://console.anthropic.com/\n"
            "ANTHROPIC_API_KEY=sk-ant-...\n"
            "# ANTHROPIC_BASE_URL=https://api.anthropic.com  # optional override\n"
        ),
    },

    "azure": {
        "model_prefix":  "azure/",
        "api_key_env":   "AZURE_OPENAI_KEY",
        "base_url":      "",           # from AZURE_OPENAI_ENDPOINT env var
        "base_url_env":  "AZURE_OPENAI_ENDPOINT",
        "region_env":    None,
        "extra_headers": {},
        "litellm_kwargs": {},
        "models": {
            "default":      "azure/gpt-4",
            "high_quality": "azure/gpt-4-turbo",
            "fast":         "azure/gpt-35-turbo",
        },
        "cost_per_1k": 0.003,
        "active": True,
        "env_example": (
            "# Azure OpenAI — Azure Portal → OpenAI Service\n"
            "AZURE_OPENAI_KEY=your_azure_key_here\n"
            "AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/\n"
        ),
    },

    "vertex": {
        "model_prefix":  "vertex_ai/",
        "api_key_env":   None,         # uses GOOGLE_APPLICATION_CREDENTIALS
        "base_url":      "",
        "base_url_env":  None,
        "region_env":    "GCP_REGION",
        "extra_headers": {},
        "litellm_kwargs": {},
        "models": {
            "default":      "vertex_ai/claude-sonnet-4@20250514",
            "high_quality": "vertex_ai/claude-opus-4@20250514",
            "fast":         "vertex_ai/claude-haiku-4@20250514",
        },
        "cost_per_1k": 0.003,
        "active": True,
        "env_example": (
            "# Google Vertex AI — Google Cloud Console → Vertex AI\n"
            "GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json\n"
            "GCP_REGION=us-central1\n"
        ),
    },

    # ── Inactive providers — uncomment api_key_env + set active=True to enable ──

    "doubleword": {
        "model_prefix":  "openai/",    # OpenAI-compatible API
        "api_key_env":   "DOUBLEWORD_API_KEY",
        "base_url":      "https://api.doubleword.ai/v1",
        "base_url_env":  "DOUBLEWORD_BASE_URL",
        "region_env":    None,
        "extra_headers": {},
        "litellm_kwargs": {},
        "models": {
            "default":      "openai/doubleword-default",
            "high_quality": "openai/doubleword-default",
            "fast":         "openai/doubleword-default",
        },
        "cost_per_1k": None,
        "active": False,               # set True + add DOUBLEWORD_API_KEY to .env
        "env_example": (
            "# Doubleword — OpenAI-compatible endpoint\n"
            "DOUBLEWORD_API_KEY=your-key-here\n"
            "# DOUBLEWORD_BASE_URL=https://api.doubleword.ai/v1  # optional override\n"
        ),
    },

    "ollama": {
        "model_prefix":  "ollama/",
        "api_key_env":   None,         # no auth needed for local
        "base_url":      "http://localhost:11434/v1",
        "base_url_env":  "OLLAMA_BASE_URL",
        "region_env":    None,
        "extra_headers": {},
        "litellm_kwargs": {},
        "models": {
            "default":      "ollama/llama3.3",
            "high_quality": "ollama/llama3.3",
            "fast":         "ollama/llama3.2",
        },
        "cost_per_1k": 0.0,
        "active": False,               # set True to enable local Ollama
        "env_example": (
            "# Ollama local LLM — https://ollama.com\n"
            "# OLLAMA_BASE_URL=http://localhost:11434/v1  # optional override\n"
        ),
    },
}


# ---------------------------------------------------------------------------
# Derived helpers — consumed by llm_client.py, settings.py, check-model-routing
# ---------------------------------------------------------------------------

def active_providers() -> List[str]:
    """Return names of all active providers."""
    return [name for name, m in PROVIDER_MANIFEST.items() if m.get("active", False)]


def get_manifest(provider_name: str) -> Optional[Dict[str, Any]]:
    """Return manifest entry for a provider name (case-insensitive). None if not found."""
    return PROVIDER_MANIFEST.get(provider_name.lower())


def model_prefix_for(provider_name: str) -> str:
    m = get_manifest(provider_name)
    return m["model_prefix"] if m else ""


def api_key_env_for(provider_name: str) -> Optional[str]:
    m = get_manifest(provider_name)
    return m.get("api_key_env") if m else None


def base_url_for(provider_name: str) -> str:
    """Resolve base URL: base_url_env override → base_url default."""
    m = get_manifest(provider_name)
    if not m:
        return ""
    override_env = m.get("base_url_env")
    if override_env and os.getenv(override_env):
        return os.getenv(override_env).rstrip("/")
    return m.get("base_url", "").rstrip("/")


def resolve_api_key(provider_name: str) -> Optional[str]:
    """Return the API key value from the env var, or None."""
    key_env = api_key_env_for(provider_name)
    return os.getenv(key_env) if key_env else None


def infer_provider_from_model(model: str) -> Optional[str]:
    """Return provider name from model string prefix. Returns None if unrecognised."""
    if not model or model.startswith("${"):
        return None
    for name, m in PROVIDER_MANIFEST.items():
        prefix = m.get("model_prefix", "")
        if prefix and model.startswith(prefix):
            return name
    return None


def env_example_block() -> str:
    """Return the full .env.example content for all active providers."""
    lines = []
    for name, m in PROVIDER_MANIFEST.items():
        if m.get("active") and m.get("env_example"):
            lines.append(f"# ── {name} ──")
            lines.append(m["env_example"])
    return "\n".join(lines)
