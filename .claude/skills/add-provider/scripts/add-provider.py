#!/usr/bin/env python3
"""
add-provider — Add a new LLM provider to ThreatAssessor.

Edits agentic/providers.PROVIDER_MANIFEST (single source of truth).
All elif chains in llm_client.py read from the manifest — no code changes needed.

Usage:
    python3 add-provider.py --list
    python3 add-provider.py --name doubleword --api-key-env DOUBLEWORD_API_KEY \
        --base-url https://api.doubleword.ai/v1 --model-prefix openai/ \
        --default-model openai/doubleword-v1
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

PROVIDERS_FILE = REPO / "agentic" / "providers.py"
ENV_EXAMPLE    = REPO / ".env.example"
LLM_CLIENT     = REPO / "agentic" / "llm_client.py"

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"


# ── List current providers ────────────────────────────────────────────────────

def list_providers() -> None:
    from agentic.providers import PROVIDER_MANIFEST
    print(f"\n{BOLD(CYAN('Provider Manifest'))} — {PROVIDERS_FILE.relative_to(REPO)}\n")
    print(f"  {'Name':<14} {'Active':<8} {'Prefix':<14} {'Key env var':<26} {'Base URL'}")
    print(f"  {'─'*14} {'─'*8} {'─'*14} {'─'*26} {'─'*40}")
    for name, m in PROVIDER_MANIFEST.items():
        active  = GREEN("✓ yes") if m.get("active") else DIM("– no")
        prefix  = m.get("model_prefix", "")
        key_env = m.get("api_key_env") or DIM("(none)")
        base    = m.get("base_url", "")[:40]
        print(f"  {BOLD(name):<14} {active:<8} {DIM(prefix):<14} {DIM(key_env):<26} {DIM(base)}")
    print()


# ── Validate a proposed manifest entry ───────────────────────────────────────

def validate_entry(name: str, entry: dict) -> list:
    errors = []
    if not name.isidentifier():
        errors.append("name must be a valid Python identifier")
    if not entry.get("model_prefix"):
        errors.append("model_prefix is required (e.g. 'openai/' or 'ollama/')")
    if not entry.get("models", {}).get("default"):
        errors.append("models.default is required")
    if not entry.get("base_url") and not entry.get("base_url_env"):
        errors.append("base_url or base_url_env is required")
    return errors


# ── Write manifest entry ──────────────────────────────────────────────────────

def _entry_to_python(name: str, entry: dict) -> str:
    """Render a manifest entry as a Python dict literal to insert into providers.py."""
    api_key_env  = f'"{entry["api_key_env"]}"' if entry.get("api_key_env") else "None"
    base_url_env = f'"{entry["base_url_env"]}"' if entry.get("base_url_env") else "None"
    region_env   = f'"{entry["region_env"]}"'   if entry.get("region_env")   else "None"
    models       = entry.get("models", {})
    default_m    = models.get("default", "")
    hq_m         = models.get("high_quality", default_m)
    fast_m       = models.get("fast", default_m)
    cost         = str(entry.get("cost_per_1k")) if entry.get("cost_per_1k") is not None else "None"
    active       = "True" if entry.get("active") else "False"
    env_ex       = entry.get("env_example", "").replace("\\n", "\n").replace('"', '\\"')

    return f'''
    "{name}": {{
        "model_prefix":  "{entry.get("model_prefix", "")}",
        "api_key_env":   {api_key_env},
        "base_url":      "{entry.get("base_url", "")}",
        "base_url_env":  {base_url_env},
        "region_env":    {region_env},
        "extra_headers": {{}},
        "litellm_kwargs": {{}},
        "models": {{
            "default":      "{default_m}",
            "high_quality": "{hq_m}",
            "fast":         "{fast_m}",
        }},
        "cost_per_1k": {cost},
        "active": {active},
        "env_example": (
            "# {name} provider\\n"
            "{entry.get('api_key_env', 'NO_KEY')}=your-key-here\\n"
        ),
    }},'''


def add_to_manifest(name: str, entry: dict) -> bool:
    """Insert the entry into providers.py before the inactive providers comment."""
    src = PROVIDERS_FILE.read_text(encoding="utf-8")

    if f'"{name}"' in src:
        print(AMBER(f"  Provider '{name}' already exists in the manifest."))
        # Just activate it if inactive
        if '"active": False' in src:
            updated = src.replace(
                f'"{name}": {{\n        "model_prefix"',
                f'"{name}": {{\n        "model_prefix"'
            )
        return False

    python_entry = _entry_to_python(name, entry)

    # Insert before the inactive providers comment block
    anchor = "    # ── Inactive providers"
    if anchor not in src:
        anchor = "}\n\n\n# -----------"  # fallback: before derived helpers

    updated = src.replace(anchor, python_entry + "\n\n" + anchor, 1)
    PROVIDERS_FILE.write_text(updated, encoding="utf-8")
    return True


def add_enum_value(name: str) -> bool:
    """Add the LLMProvider enum value to llm_client.py if not present."""
    src = LLM_CLIENT.read_text(encoding="utf-8")
    upper = name.upper()
    if upper in src:
        return False   # already present

    # Insert after last existing enum value
    m = re.search(r'(    [A-Z]+ = "[a-z]+")\n(    """|\n)', src)
    if not m:
        print(AMBER(f"  Could not auto-insert enum value {upper} — add manually to LLMProvider in agentic/llm_client.py"))
        return False

    insert_after = m.group(1)
    updated = src.replace(
        insert_after,
        insert_after + f'\n    {upper:<10} = "{name}"',
        1,
    )
    LLM_CLIENT.write_text(updated, encoding="utf-8")
    return True


def add_env_example(name: str, entry: dict) -> None:
    """Append the provider's env example block to .env.example."""
    if not ENV_EXAMPLE.exists():
        return
    env_ex = entry.get("env_example", "")
    if not env_ex:
        return
    current = ENV_EXAMPLE.read_text(encoding="utf-8")
    if entry.get("api_key_env", "") in current:
        return   # already present

    # Insert before the Configuration Profiles section
    anchor = "# ==============================================================================\n# Configuration Profiles"
    if anchor in current:
        block = f"\n# ── {name} ──\n{env_ex}\n"
        current = current.replace(anchor, block + anchor, 1)
        ENV_EXAMPLE.write_text(current, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Add a new LLM provider to ThreatAssessor")
    parser.add_argument("--list",          action="store_true",  help="List current providers")
    parser.add_argument("--name",                                help="Provider name (e.g. doubleword)")
    parser.add_argument("--api-key-env",                         help="Env var name for API key (e.g. DOUBLEWORD_API_KEY)")
    parser.add_argument("--no-key",        action="store_true",  help="No API key required (local providers)")
    parser.add_argument("--base-url",                            help="Provider base URL")
    parser.add_argument("--base-url-env",                        help="Env var to override base URL at runtime")
    parser.add_argument("--model-prefix",                        help="LiteLLM model prefix (e.g. openai/ or ollama/)")
    parser.add_argument("--default-model",                       help="Default model string")
    parser.add_argument("--cost-per-1k",   type=float,           help="Approximate cost USD per 1k tokens")
    parser.add_argument("--inactive",      action="store_true",  help="Add as inactive (active=False)")
    args = parser.parse_args()

    if args.list:
        list_providers()
        return

    if not args.name:
        parser.print_help()
        return

    name = args.name.lower().strip()
    entry = {
        "model_prefix":  args.model_prefix or "",
        "api_key_env":   None if args.no_key else args.api_key_env,
        "base_url":      args.base_url or "",
        "base_url_env":  args.base_url_env,
        "region_env":    None,
        "extra_headers": {},
        "litellm_kwargs": {},
        "models": {
            "default":      args.default_model or "",
            "high_quality": args.default_model or "",
            "fast":         args.default_model or "",
        },
        "cost_per_1k": args.cost_per_1k,
        "active":       not args.inactive,
        "env_example":  (
            f"# {name} provider\n"
            + (f"{args.api_key_env}=your-key-here\n" if args.api_key_env else "")
            + (f"# {args.base_url_env}={args.base_url}  # optional override\n" if args.base_url_env else "")
        ),
    }

    # Validate
    errors = validate_entry(name, entry)
    if errors:
        for e in errors:
            print(RED(f"  ✗ {e}"))
        sys.exit(1)

    # Preview
    print(f"\n{BOLD('Preview — manifest entry for')} {BOLD(CYAN(name))}:\n")
    print(_entry_to_python(name, entry))

    # Gate
    print(f"\n{BOLD('Actions:')} edit agentic/providers.py + add LLMProvider enum value + update .env.example")
    try:
        answer = input("\n  Proceed? [y/N]: ").strip().lower()
    except EOFError:
        answer = "n"
    if answer not in ("y", "yes"):
        print(DIM("  Aborted."))
        return

    # Apply
    manifest_changed = add_to_manifest(name, entry)
    if manifest_changed:
        print(GREEN(f"  ✓ Added '{name}' to agentic/providers.py"))

    enum_changed = add_enum_value(name)
    if enum_changed:
        print(GREEN(f"  ✓ Added {name.upper()} to LLMProvider enum in agentic/llm_client.py"))
    elif not args.inactive:
        print(AMBER(f"  ⚠ Add {name.upper()} = \"{name}\" to LLMProvider enum in agentic/llm_client.py manually"))

    add_env_example(name, entry)

    # Validate routing
    print(f"\n{BOLD('Validating routing...')}")
    import subprocess, sys as _sys
    result = subprocess.run(
        [_sys.executable,
         str(REPO / ".claude/skills/check-model-routing/scripts/check-model-routing.py"),
         "--errors-only"],
        cwd=REPO, capture_output=False,
    )

    print()
    print(f"  Next steps:")
    if entry.get("api_key_env"):
        print(f"  1. Add {entry['api_key_env']}=your-key-here to .env")
    print(f"  2. Set LLM_PROVIDER={name} in .env")
    print(f"  3. ./scripts/api/api_restart.sh")


if __name__ == "__main__":
    main()
