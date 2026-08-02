#!/usr/bin/env python3
"""
check-model-routing — Validate LLM model routing without API calls.

Shows resolved model for every agent, embedding, and TATB labeller.
Flags provider/key/family mismatches.

Usage:
    python3 check-model-routing.py
    python3 check-model-routing.py --errors-only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"

# ── Provider detection ────────────────────────────────────────────────────────

def _provider_from_model(model: Optional[str]) -> str:
    if not model:
        return "env_default"
    # Use manifest for prefix matching — auto-covers new providers
    try:
        from agentic.providers import infer_provider_from_model
        result = infer_provider_from_model(model)
        if result:
            return result
    except Exception:
        pass
    # Fallbacks for known patterns not in manifest prefix
    m = model.lower()
    if m.startswith("us.") or m.startswith("bedrock/"):
        return "bedrock"
    return "unknown"


def _family_from_model(model: Optional[str]) -> str:
    """Extract the model family for independence checks."""
    if not model:
        return "unknown"
    m = model.lower()
    if "claude" in m:      return "claude"
    if "nova" in m:        return "amazon_nova"
    if "gemini" in m:      return "gemini"
    if "gpt" in m:         return "openai"
    if "llama" in m:       return "llama"
    if "nemotron" in m:    return "nvidia"
    if "mistral" in m:     return "mistral"
    return "other"


def _build_provider_keys() -> dict:
    """Build provider → api_key_env_var map from the manifest. Auto-extends when new providers added."""
    try:
        from agentic.providers import PROVIDER_MANIFEST
        return {
            name: m["api_key_env"]
            for name, m in PROVIDER_MANIFEST.items()
            if m.get("api_key_env")
        }
    except Exception:
        return {"bedrock": "AWS_BEDROCK_API_KEY", "openrouter": "OPENROUTER_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY", "azure": "AZURE_OPENAI_KEY"}

_PROVIDER_KEYS = _build_provider_keys()

def _key_present(provider: str) -> Optional[bool]:
    """True = set, False = missing, None = no key required (ollama, env_default)."""
    key_var = _PROVIDER_KEYS.get(provider)
    if not key_var:
        return None
    return bool(os.getenv(key_var))


# ── Routing resolution ────────────────────────────────────────────────────────

def _resolve_guardian_models() -> dict:
    """Return {agent_name: model_string} from HarnessModelGuardian."""
    try:
        from chatbot.harness.controller import HarnessModelGuardian, _SWARM_AGENT_NAMES
        guardian = HarnessModelGuardian()
        result = {}
        for name in _SWARM_AGENT_NAMES:
            m = guardian.get_model(name)
            result[name] = m  # None = falls through to env_default
        return result
    except Exception as exc:
        return {"_error": str(exc)}


def _resolve_embedding_model() -> str:
    try:
        from chatbot.modules.embeddings import _default_embedding_model
        return _default_embedding_model()
    except Exception:
        return os.getenv("OPENROUTER_EMBED_MODEL",
               os.getenv("settings_default", "nvidia/llama-nemotron-embed-vl-1b-v2:free"))


def _resolve_tatb_labeller() -> tuple[str, str]:
    """Returns (model, fallback)."""
    try:
        import importlib.util
        script = REPO / ".claude/skills/tatb-corpus/scripts/tatb-corpus.py"
        spec = importlib.util.spec_from_file_location("tc", script)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._resolve_labeller_model(), mod._labeller_fallback()
    except Exception:
        primary  = os.getenv("AGENT_MODEL_TATB_LABELLER",  "bedrock/us.amazon.nova-pro-v1:0")
        fallback = os.getenv("AGENT_MODEL_TATB_LABELLER_FALLBACK",
                             "bedrock/us.anthropic.claude-haiku-4-20250514-v1:0")
        return primary, fallback


def _resolve_event_detector() -> Optional[str]:
    return os.getenv("AGENT_MODEL_EVENT_DETECTOR") or None


# ── Validation ────────────────────────────────────────────────────────────────

class Finding:
    def __init__(self, level: str, agent: str, message: str):
        self.level   = level   # ok | warn | error
        self.agent   = agent
        self.message = message


def _check_model(agent: str, model: Optional[str], primary_provider: str,
                 findings: list) -> str:
    """Validate a single model string, append findings, return display string."""
    if not model:
        findings.append(Finding("ok", agent, f"no per-agent config — uses {primary_provider} default"))
        return DIM(f"(provider default: {primary_provider})")

    # Unresolved ${VAR} placeholder — user_config.json loaded without env interpolation
    if model.startswith("${") and model.endswith("}"):
        var_name = model[2:-1]
        if os.getenv(var_name):
            findings.append(Finding("warn", agent,
                f"{model} present in env but user_config.json is not interpolated — "
                f"model resolves to literal string, not {os.getenv(var_name)!r}. "
                f"Set agent_models.{agent}.model directly in user_config.json or settings.yaml"))
        else:
            findings.append(Finding("warn", agent,
                f"{model} is an unresolved placeholder — env var not set and "
                f"user_config.json is not interpolated. Agent uses {primary_provider} default."))
        return AMBER(model)

    provider = _provider_from_model(model)
    key_ok   = _key_present(provider)

    # Provider consistency
    if provider not in ("env_default", "unknown") and provider != primary_provider:
        findings.append(Finding("warn", agent,
            f"model prefix '{provider}' differs from LLM_PROVIDER='{primary_provider}' — "
            f"LiteLLM will use the model prefix, not LLM_PROVIDER"))

    # Key presence
    if key_ok is False:
        findings.append(Finding("error", agent,
            f"provider '{provider}' requires {_PROVIDER_KEYS[provider]} but it is not set"))

    col = GREEN if key_ok is not False else RED
    return col(model)


# ── Main display ──────────────────────────────────────────────────────────────

def run(errors_only: bool = False) -> bool:
    try:
        from agentic.helper import load_env
        load_env()
    except Exception:
        pass

    primary_provider = os.getenv("LLM_PROVIDER", "bedrock").lower()
    findings: list = []

    # ── Guardian agents ───────────────────────────────────────────────────────
    guardian_models = _resolve_guardian_models()

    if not errors_only:
        print(f"\n{BOLD(CYAN('check-model-routing'))} — LLM routing validation\n")
        print(f"  {BOLD('LLM_PROVIDER')} = {BOLD(primary_provider)}\n")
        print(f"  {'Agent':<22} {'Model':<55} {'Provider':<12} Key")
        print(f"  {'─'*22} {'─'*55} {'─'*12} {'─'*3}")

    if "_error" in guardian_models:
        findings.append(Finding("error", "guardian", guardian_models["_error"]))
    else:
        for agent, model in guardian_models.items():
            display  = _check_model(agent, model, primary_provider, findings)
            provider = _provider_from_model(model) if model else primary_provider
            key_ok   = _key_present(provider)
            key_str  = GREEN("✓") if key_ok else (DIM("–") if key_ok is None else RED("✗"))
            if not errors_only:
                print(f"  {DIM(f'{agent:<22}')} {display:<55} {DIM(f'{provider:<12}')} {key_str}")

    # ── TATB labeller ─────────────────────────────────────────────────────────
    tatb_primary, tatb_fallback = _resolve_tatb_labeller()
    tatb_display  = _check_model("tatb_labeller", tatb_primary,  primary_provider, findings)
    fb_display    = _check_model("tatb_labeller↩", tatb_fallback, primary_provider, findings)

    # Independence check — labeller must not be same family as main pipeline agents
    main_family    = _family_from_model(guardian_models.get("architect"))
    labeller_family = _family_from_model(tatb_primary)
    if main_family and labeller_family and main_family == labeller_family and main_family != "unknown":
        findings.append(Finding("warn", "tatb_labeller",
            f"labeller family '{labeller_family}' matches pipeline family '{main_family}' — "
            f"defeats independent-verifier design (use a different model family)"))

    if not errors_only:
        print(f"\n  {'─'*22} {'─'*55}")
        tatb_prov = _provider_from_model(tatb_primary)
        tatb_key  = _key_present(tatb_prov)
        print(f"  {DIM('tatb_labeller'    + ' (independent)'):>22} "
              f"{tatb_display:<55} {DIM(f'{tatb_prov:<12}')} "
              f"{GREEN('✓') if tatb_key else (DIM('–') if tatb_key is None else RED('✗'))}")
        fb_prov = _provider_from_model(tatb_fallback)
        fb_key  = _key_present(fb_prov)
        print(f"  {DIM('  └─ fallback'):>22} {fb_display:<55} "
              f"{DIM(f'{fb_prov:<12}')} "
              f"{GREEN('✓') if fb_key else (DIM('–') if fb_key is None else RED('✗'))}")

        # ── Event detector ────────────────────────────────────────────────────
        ed_model = _resolve_event_detector()
        if ed_model:
            ed_display = _check_model("event_detector", ed_model, primary_provider, findings)
            ed_prov    = _provider_from_model(ed_model)
            ed_key     = _key_present(ed_prov)
            print(f"  {DIM('event_detector'):>22} {ed_display:<55} "
                  f"{DIM(f'{ed_prov:<12}')} "
                  f"{GREEN('✓') if ed_key else (DIM('–') if ed_key is None else RED('✗'))}")
        else:
            print(f"  {DIM('event_detector'):>22} {DIM('(provider default)')}")

        # ── Embedding ─────────────────────────────────────────────────────────
        embed_model  = _resolve_embedding_model()
        embed_prov   = _provider_from_model(embed_model)
        # Embedding goes direct to OpenRouter /embeddings endpoint, not LiteLLM prefix routing.
        # A bare model ID (no prefix) is always OpenRouter for embeddings.
        embed_prov_display = "openrouter" if embed_prov == "unknown" else embed_prov
        embed_key    = _key_present("openrouter")   # always needs OPENROUTER_API_KEY
        embed_source = "(OPENROUTER_EMBED_MODEL)" if os.getenv("OPENROUTER_EMBED_MODEL") \
                  else "(settings.embedding.model)"
        print(f"  {DIM('embedding'):>22} {GREEN(embed_model):<55} "
              f"{DIM(f'{embed_prov_display:<12}')} "
              f"{GREEN('✓') if embed_key else RED('✗')}  "
              f"{DIM(embed_source)}")

    # ── Findings summary ──────────────────────────────────────────────────────
    errors = [f for f in findings if f.level == "error"]
    warns  = [f for f in findings if f.level == "warn"]

    if not errors_only or errors or warns:
        print()

    if errors:
        print(f"  {RED('Errors:')}")
        for f in errors:
            print(f"    {RED('✗')} {f.agent}: {f.message}")

    if warns:
        print(f"  {AMBER('Warnings:')}")
        for f in warns:
            print(f"    {AMBER('⚠')} {f.agent}: {f.message}")

    if not errors and not warns:
        if not errors_only:
            print(f"  {GREEN('✓ All routing checks passed')}\n")
        return True

    if not errors_only:
        print()
    return len(errors) == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM model routing validator")
    parser.add_argument("--errors-only", action="store_true",
                        help="Print only errors and warnings, silent if all ok")
    args = parser.parse_args()

    ok = run(errors_only=args.errors_only)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
