"""
Configuration API Routes

All three endpoints require TM-API-KEY authentication — configuration data
(even tunable thresholds) should not be publicly readable as it reveals
internal scoring logic that could assist reverse-engineering.

GET  /api/v1/config        — authenticated, returns live config + provider chain status
PUT  /api/v1/config        — authenticated, live-updates the singleton
POST /api/v1/config/reset  — authenticated, restores all defaults
"""

import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from chatbot.api.dependencies import verify_api_key
from chatbot.config.settings import (
    USER_CONFIG_PATH,
    get_settings,
    load_settings,
    update_settings,
)
from chatbot.config.patterns_catalog import AVAILABLE_PATTERNS

router = APIRouter(prefix="/api/v1", tags=["config"])


def _patterns_catalog_status() -> dict:
    """Return AVAILABLE_PATTERNS enriched with whether each pattern is currently enabled."""
    enabled = get_settings().patterns.enabled_patterns
    result = {}
    for pid, meta in AVAILABLE_PATTERNS.items():
        result[pid] = {**meta, "enabled": pid in enabled}
    return result


def _provider_chain_status() -> dict:
    """
    Return the resolved LLM provider chain as a human-readable status block.

    Layout: primary → fallback(s) → verifier (optional).
    AWS_BEDROCK_API_KEY is the bearer token used when any step in the chain
    resolves to the 'bedrock' provider.  Never returns key values.
    """
    def _flag(key: str) -> str:
        return "set" if os.getenv(key) else "not_set"

    primary  = os.getenv("LLM_PROVIDER", "openrouter")
    fallback = os.getenv("LLM_FALLBACK_PROVIDERS", "")
    verifier = os.getenv("LLM_VERIFIER_PROVIDER", "")

    # Build a plain-English chain description, e.g. "openrouter → bedrock"
    chain_parts = [primary]
    if fallback:
        chain_parts += [p.strip() for p in fallback.split(",") if p.strip()]
    chain_str = " → ".join(chain_parts)

    # Which credential keys are relevant
    needs_openrouter = any("openrouter" in p for p in chain_parts)
    needs_bedrock    = any("bedrock"    in p for p in chain_parts) or "bedrock" in verifier
    needs_anthropic  = any("anthropic"  in p for p in chain_parts) or "anthropic" in verifier

    return {
        "provider_chain": chain_str,
        "verifier_provider": verifier or "(not set — uses primary)",
        "credentials": {
            "OPENROUTER_API_KEY": _flag("OPENROUTER_API_KEY") if needs_openrouter else "not_used",
            "AWS_BEDROCK_API_KEY": _flag("AWS_BEDROCK_API_KEY") if needs_bedrock else "not_used",
            "ANTHROPIC_API_KEY": _flag("ANTHROPIC_API_KEY") if needs_anthropic else "not_used",
            "API_KEY": _flag("API_KEY"),
        },
        "notes": {
            "AWS_BEDROCK_API_KEY": "Bearer token for AWS Bedrock — used when any provider in the chain is 'bedrock'",
            "LLM_FALLBACK_PROVIDERS": f"'{fallback}' — called automatically if primary fails or rate-limits",
        }
    }


@router.get("/config")
async def get_config(_: str = Depends(verify_api_key)):
    """
    Return the current runtime configuration (authenticated).

    Requires TM-API-KEY. Returns tunable parameters with their live values
    plus a provider chain status block. Key values are never returned.
    """
    data = get_settings().model_dump()
    data["_provider_chain"] = _provider_chain_status()
    data["_patterns_catalog"] = _patterns_catalog_status()
    return data


@router.put("/config")
async def put_config(payload: dict, _: str = Depends(verify_api_key)):
    """
    Update one or more configuration sections (authenticated).

    Accepts a partial dict. Validates, persists to user_config.json, and
    reloads the singleton — takes effect on the next analysis request.
    Strips _provider_chain silently (read-only).
    """
    payload.pop("_provider_chain", None)
    payload.pop("_secrets", None)
    try:
        new_settings = update_settings(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=exc.errors())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=str(exc))
    result = new_settings.model_dump()
    result["_provider_chain"] = _provider_chain_status()
    return {"status": "ok", "config": result}


@router.post("/config/reset")
async def reset_config(_: str = Depends(verify_api_key)):
    """
    Reset all configuration to built-in defaults (authenticated).

    Deletes user_config.json and reloads the singleton from scratch.
    """
    USER_CONFIG_PATH.unlink(missing_ok=True)
    settings = load_settings()
    result = settings.model_dump()
    result["_provider_chain"] = _provider_chain_status()
    return {"status": "ok", "config": result}
