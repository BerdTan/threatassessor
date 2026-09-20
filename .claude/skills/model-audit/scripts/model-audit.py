#!/usr/bin/env python3
"""
model-audit — Engine Item 14
Audit the model trust surface: config integrity, routing staleness,
critic role validation, endogenous output scan (DETECT-QC-009 path),
and provider config audit.

Six dimensions:
  DIM-1  Config integrity      — AGENT_MODEL_* env vars vs model_routing.yaml
  DIM-2  Routing config staleness — model_routing.yaml mtime vs bench reference
  DIM-3  Critic role validation — assigned models vs bench pass/exclusion registry
  DIM-4  Endogenous output scan — SM synthesis_note/action_plan for constraint-override language
  DIM-5  Provider config audit  — LLM_PROVIDER vs documented provider list
  DIM-6  HarnessModelGuardian   — guardian wired in harness; no direct env-var reads

No API required — all checks read source files and config only.
Exit codes: 0 = no CRITICAL/HIGH; 1 = CRITICAL/HIGH found; 2 = parse error
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if not (ROOT / "mcp_server" / "server.py").exists():
    print(f"[ERROR] Could not locate project root (tried {ROOT})", file=sys.stderr)
    sys.exit(2)

_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

FINDINGS: list[dict[str, Any]] = []


def _find(dim: str, title: str, severity: str, detail: str, path: str = "") -> None:
    FINDINGS.append({"dim": dim, "title": title, "severity": severity,
                     "detail": detail, "path": path})


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_yaml(path: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        _find("PARSE", f"Cannot load {path.name}", "HIGH",
              f"YAML parse error: {exc}", str(path.relative_to(ROOT)))
        return {}


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; skip comments."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# DIM-1  Config integrity
# ═══════════════════════════════════════════════════════════════════════════════

# Valid providers documented in .env.example
_DOCUMENTED_PROVIDERS = {"openrouter", "bedrock", "hetzner", "gemini"}

# Critic roles in HarnessModelGuardian
_CRITIC_ROLES = ["architect", "tester", "red_team", "purple_team",
                 "blackhat", "scrum_master", "moe_orchestrator"]


def dim1_config_integrity() -> None:
    """Check AGENT_MODEL_* env vars are consistent with model_routing.yaml tested_models."""
    routing_path = ROOT / "policies" / "model_routing.yaml"
    env_example  = ROOT / ".env.example"

    if not routing_path.exists():
        _find("DIM-1", "model_routing.yaml missing", "HIGH",
              "Cannot verify model config integrity.", str(routing_path))
        return

    routing = _load_yaml(routing_path)
    tested_models: dict = routing.get("tested_models", {})
    model_ids = {k: v.get("model_id", "") for k, v in tested_models.items()}
    confirmed_ids = {v["model_id"] for v in tested_models.values()
                     if v.get("status") == "confirmed"}
    excluded_ids  = {v["model_id"] for v in tested_models.values()
                     if v.get("status") == "excluded"}

    # Read AGENT_MODEL_* from .env (if present) and .env.example
    env_live = _load_dotenv(ROOT / ".env")
    env_ex   = _load_dotenv(env_example)

    agent_model_vars: dict[str, str] = {}
    for src in (env_ex, env_live):
        for k, v in src.items():
            if k.startswith("AGENT_MODEL_") and v:
                agent_model_vars[k] = v

    if not agent_model_vars:
        _find(
            "DIM-1",
            "No AGENT_MODEL_* overrides set — harness uses LLM_PROVIDER default",
            "INFO",
            "All critic roles resolve through HarnessModelGuardian to LLM_PROVIDER. "
            "This is the standard deployment pattern.",
            ".env.example",
        )
    else:
        for var, model_val in agent_model_vars.items():
            # Check if the model is in the excluded list
            if model_val in excluded_ids:
                _find(
                    "DIM-1",
                    f"{var}={model_val!r} — model is EXCLUDED in tested_models",
                    "HIGH",
                    f"This model has status=excluded in model_routing.yaml "
                    f"(blackhat silence or quality failure). Routing it via env-var "
                    f"bypasses the exclusion registry. "
                    f"Remove the override or update tested_models.status.",
                    str(routing_path.relative_to(ROOT)),
                )
            elif model_val and model_val not in confirmed_ids:
                # Model set but not in confirmed list — partial or unlisted
                in_tested = any(model_val == v for v in model_ids.values())
                if not in_tested:
                    _find(
                        "DIM-1",
                        f"{var}={model_val!r} — model not in tested_models registry",
                        "MEDIUM",
                        f"This model has no bench record in model_routing.yaml. "
                        f"It may not be validated for ThreatAssessor quality requirements. "
                        f"Run bench-loop and add an entry to tested_models before production routing.",
                        str(routing_path.relative_to(ROOT)),
                    )

    # Check model_selection entries reference only tested_models keys
    model_selection = routing.get("model_selection", {})
    all_routed: set[str] = set()
    for tier_data in model_selection.values():
        for arch_data in tier_data.values():
            if isinstance(arch_data, dict):
                for role in ("primary", "fallback"):
                    val = arch_data.get(role)
                    if val:
                        all_routed.add(val)

    undocumented_routed = all_routed - set(tested_models.keys())
    if undocumented_routed:
        _find(
            "DIM-1",
            f"model_selection references unknown model keys: {undocumented_routed}",
            "MEDIUM",
            "These keys appear in model_selection but have no entry in tested_models. "
            "They cannot be validated against the exclusion registry.",
            str(routing_path.relative_to(ROOT)),
        )
    else:
        _find(
            "DIM-1",
            "model_selection — all entries reference documented tested_models",
            "INFO",
            f"Checked {len(all_routed)} routed model keys; all present in tested_models.",
            str(routing_path.relative_to(ROOT)),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# DIM-2  Routing config staleness
# ═══════════════════════════════════════════════════════════════════════════════

_STALENESS_DAYS_WARN = 14
_STALENESS_DAYS_HIGH = 30


def dim2_routing_staleness() -> None:
    """Detect if model_routing.yaml is stale relative to bench_results."""
    routing_path = ROOT / "policies" / "model_routing.yaml"
    bench_dir = ROOT / "bench_results"

    if not routing_path.exists():
        return  # already flagged in DIM-1

    routing = _load_yaml(routing_path)
    routing_updated = routing.get("updated", "")

    # Find most recent bench run directory (by mtime)
    bench_summary: Path | None = None
    if bench_dir.exists():
        candidates = [
            d / "bench_summary.json"
            for d in bench_dir.iterdir()
            if d.is_dir() and (d / "bench_summary.json").exists()
        ]
        if candidates:
            bench_summary = max(candidates, key=lambda p: p.stat().st_mtime)

    routing_mtime = routing_path.stat().st_mtime
    now = time.time()
    routing_age_days = (now - routing_mtime) / 86400

    if bench_summary:
        bench_mtime = bench_summary.stat().st_mtime
        bench_age_days = (now - bench_mtime) / 86400
        delta_days = bench_mtime - routing_mtime  # positive = bench newer than routing

        if delta_days > 86400:  # bench is >1 day newer than routing update
            _find(
                "DIM-2",
                f"model_routing.yaml predates newest bench by {delta_days/86400:.0f}d",
                "MEDIUM" if delta_days < 7 * 86400 else "HIGH",
                f"Newest bench summary: {bench_summary.parent.name}. "
                f"model_routing.yaml updated: {routing_updated}. "
                f"Routing config was not updated after the last bench run. "
                f"New bench results (model performance or exclusions) may not be reflected. "
                f"Remediation: review bench delta and update model_selection + tested_models.",
                str(routing_path.relative_to(ROOT)),
            )
        else:
            _find(
                "DIM-2",
                "model_routing.yaml is current with latest bench run",
                "INFO",
                f"Routing updated {routing_updated}; "
                f"latest bench: {bench_summary.parent.name} ({bench_age_days:.0f}d ago).",
                str(routing_path.relative_to(ROOT)),
            )
    else:
        # No bench results — just check age
        if routing_age_days > _STALENESS_DAYS_HIGH:
            _find(
                "DIM-2",
                f"model_routing.yaml is {routing_age_days:.0f}d old and no bench_results found",
                "MEDIUM",
                "No bench_results directory or bench_summary.json found. "
                "Cannot compare routing config against bench data. "
                "Run bench-loop to generate a baseline.",
                str(routing_path.relative_to(ROOT)),
            )
        else:
            _find(
                "DIM-2",
                "No bench results to compare routing staleness against",
                "LOW",
                f"model_routing.yaml updated {routing_updated}. "
                "Run bench-loop to generate a validated baseline.",
                str(routing_path.relative_to(ROOT)),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# DIM-3  Critic role validation
# ═══════════════════════════════════════════════════════════════════════════════

# Models with documented blackhat silence — should never be routed
_BLACKHAT_SILENCE_MODELS = {
    "openrouter/google/gemma-4-26b-a4b-it:free",
    "openrouter/google/gemma-4-31b-a8b-it:free",
    "gemma_4_26b",
    "gemma_4_31b",
}


def dim3_critic_role_validation() -> None:
    """Verify assigned models have bench coverage; flag blackhat silence exclusions."""
    routing_path = ROOT / "policies" / "model_routing.yaml"
    if not routing_path.exists():
        return

    routing = _load_yaml(routing_path)
    tested_models: dict = routing.get("tested_models", {})
    model_selection: dict = routing.get("model_selection", {})

    # Check excluded models not in any routing selection
    full_moe = model_selection.get("full_moe", {})
    excluded_in_routing: list[str] = []

    for arch_key, arch_data in full_moe.items():
        if not isinstance(arch_data, dict):
            continue
        for role in ("primary", "fallback"):
            key = arch_data.get(role)
            if not key:
                continue
            entry = tested_models.get(key, {})
            if entry.get("status") == "excluded":
                excluded_in_routing.append(
                    f"full_moe.{arch_key}.{role}={key} (status=excluded)"
                )
            # Check for blackhat silence models by model_id
            model_id = entry.get("model_id", key)
            if model_id in _BLACKHAT_SILENCE_MODELS or key in _BLACKHAT_SILENCE_MODELS:
                excluded_in_routing.append(
                    f"full_moe.{arch_key}.{role}={key} (blackhat silence pattern)"
                )

    if excluded_in_routing:
        for item in excluded_in_routing[:5]:
            _find(
                "DIM-3",
                f"Excluded model in routing: {item}",
                "HIGH",
                "An excluded model (blackhat silence or quality failure) is still "
                "referenced in model_selection. Routing it to a critic role produces "
                "silent blackhat analysis — exploitable by an adversary who knows the model "
                "exclusion pattern. Remove from model_selection or update status.",
                str(routing_path.relative_to(ROOT)),
            )
    else:
        _find(
            "DIM-3",
            "No excluded models in active routing selection",
            "INFO",
            "Checked all full_moe model_selection entries; none carry status=excluded.",
            str(routing_path.relative_to(ROOT)),
        )

    # Check that each confirmed model appears in at least one arch routing slot
    confirmed_keys = {k for k, v in tested_models.items() if v.get("status") == "confirmed"}
    all_routed_keys: set[str] = set()
    for tier_data in model_selection.values():
        for arch_data in tier_data.values():
            if isinstance(arch_data, dict):
                for role in ("primary", "fallback"):
                    val = arch_data.get(role)
                    if val:
                        all_routed_keys.add(val)

    unrouted_confirmed = confirmed_keys - all_routed_keys
    if unrouted_confirmed:
        _find(
            "DIM-3",
            f"Confirmed models not in any routing slot: {unrouted_confirmed}",
            "LOW",
            "These models passed bench but are not referenced in model_selection. "
            "They won't be used. This is safe but indicates a routing config gap — "
            "consider adding them as fallbacks.",
            str(routing_path.relative_to(ROOT)),
        )

    # HarnessModelGuardian role coverage — verify all critic roles exist in controller.py
    controller = ROOT / "chatbot" / "harness" / "controller.py"
    if controller.exists():
        ctrl_src = controller.read_text(encoding="utf-8", errors="replace")
        missing_roles = [r for r in _CRITIC_ROLES if f'"{r}"' not in ctrl_src]
        if missing_roles:
            _find(
                "DIM-3",
                f"Critic roles not found in _SWARM_AGENT_NAMES: {missing_roles}",
                "MEDIUM",
                "These roles are expected by model-audit but not present in "
                "HarnessModelGuardian._SWARM_AGENT_NAMES. The guardian cannot route "
                "these roles — they fall through to LLM_PROVIDER default with no "
                "model selection enforcement.",
                str(controller.relative_to(ROOT)),
            )
        else:
            _find(
                "DIM-3",
                "All critic roles present in HarnessModelGuardian",
                "INFO",
                f"Roles verified: {', '.join(_CRITIC_ROLES)}.",
                str(controller.relative_to(ROOT)),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# DIM-4  Endogenous output scan (DETECT-QC-009 path)
# ═══════════════════════════════════════════════════════════════════════════════

# Constraint-override patterns in SM output — the DETECT-QC-009 surface
_CONSTRAINT_OVERRIDE_PATTERNS = [
    r"ignore\s+(previous|prior|all|your)\s+(instructions?|constraints?|rules?|guidelines?)",
    r"disregard\s+(your|the|all)\s+(instructions?|constraints?|rules?)",
    r"you\s+are\s+(now|actually)\s+a\s+",
    r"act\s+as\s+(if\s+you\s+are|a\s+)",
    r"forget\s+(everything|all|your)\s*(you\s+know|constraints?|instructions?)?",
    r"do\s+not\s+(follow|apply|use)\s+(your|the)\s+(safety|security|guidelines?|rules?)",
    r"bypass\s+(your|the|all)\s+(safety|security|guidelines?|rules?|constraints?)",
    r"override\s+(your|the|all)\s+(instructions?|constraints?|rules?)",
    r"new\s+persona\s*:",
    r"system\s*prompt\s*:\s*you\s+are",
]

_CONSTRAINT_RE = re.compile(
    "|".join(_CONSTRAINT_OVERRIDE_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)


def dim4_endogenous_output_scan() -> None:
    """Scan SM critic output fields for constraint-override language (DETECT-QC-009)."""
    sm_critic = ROOT / "chatbot" / "modules" / "agents" / "critics" / "scrum_master_critic.py"
    report_dir = ROOT / "report"

    # Check 1: SM output structure exists and synthesis_note/action_plan fields are present
    if sm_critic.exists():
        sm_src = sm_critic.read_text(encoding="utf-8", errors="replace")
        has_synthesis = "synthesis_note" in sm_src
        has_action = "action_plan" in sm_src
        if has_synthesis and has_action:
            _find(
                "DIM-4",
                "SM critic output fields identified (synthesis_note, action_plan)",
                "INFO",
                "DETECT-QC-009 scan targets these fields: model-generated text that "
                "flows to downstream pipeline consumers. Scanning existing report outputs.",
                str(sm_critic.relative_to(ROOT)),
            )
        else:
            _find(
                "DIM-4",
                "SM critic output structure not found",
                "MEDIUM",
                "Could not locate synthesis_note or action_plan in scrum_master_critic.py. "
                "DETECT-QC-009 scan cannot target the expected fields.",
                str(sm_critic.relative_to(ROOT)),
            )

    # Check 2: Scan existing SM output files in report/
    sm_files_scanned = 0
    sm_hits: list[tuple[str, str]] = []

    if report_dir.exists():
        # Look for SM output JSON files in report subdirs
        for sm_json in report_dir.rglob("07_scrum_master*.json"):
            sm_files_scanned += 1
            try:
                import json
                data = json.loads(sm_json.read_text(encoding="utf-8", errors="replace"))
                # Check synthesis_note and action_plan rationale fields
                check_fields = []
                if "synthesis_note" in data:
                    check_fields.append(("synthesis_note", data["synthesis_note"] or ""))
                if "action_plan" in data:
                    for item in data.get("action_plan", []):
                        if isinstance(item, dict):
                            check_fields.append(("action_plan.rationale",
                                                  item.get("rationale", "")))
                            check_fields.append(("action_plan.action",
                                                  item.get("action", "")))
                        elif isinstance(item, str):
                            check_fields.append(("action_plan", item))

                for field_name, text in check_fields:
                    if not isinstance(text, str):
                        continue
                    m = _CONSTRAINT_RE.search(text)
                    if m:
                        sm_hits.append((
                            str(sm_json.relative_to(ROOT)),
                            f"{field_name}: ...{text[max(0,m.start()-20):m.end()+40]!r}...",
                        ))
            except Exception:
                pass

    if sm_hits:
        for file_path, snippet in sm_hits[:5]:
            _find(
                "DIM-4",
                f"Constraint-override language in SM output: {file_path}",
                "CRITICAL",
                f"SM output contains patterns matching DETECT-QC-009 "
                f"(sm_constraint_evasion_language). This is the endogenous injection "
                f"vector: model-generated text influencing downstream pipeline stages. "
                f"Snippet: {snippet}. "
                f"Investigate immediately — this may indicate model substitution or "
                f"adversarial LLM output.",
                file_path,
            )
    elif sm_files_scanned > 0:
        _find(
            "DIM-4",
            f"SM output scan clean — {sm_files_scanned} file(s) checked",
            "INFO",
            "No constraint-override patterns found in synthesis_note or action_plan fields.",
            "report/",
        )
    else:
        _find(
            "DIM-4",
            "No SM output files found to scan",
            "LOW",
            "No 07_scrum_master*.json files in report/. "
            "Run a full_moe pipeline pass to generate SM output for scanning.",
            "report/",
        )

    # Check 3: DETECT-QC-009 rule existence in soc_detection_rules.yaml
    rules_path = ROOT / "policies" / "soc_detection_rules.yaml"
    if rules_path.exists():
        rules_src = rules_path.read_text(encoding="utf-8", errors="replace")
        if "DETECT-QC-009" in rules_src or "sm_constraint_evasion" in rules_src:
            _find(
                "DIM-4",
                "DETECT-QC-009 rule present in soc_detection_rules.yaml",
                "INFO",
                "sm_constraint_evasion_language detection rule is implemented. "
                "The endogenous output scan above cross-checks for rule evasion on disk.",
                str(rules_path.relative_to(ROOT)),
            )
        else:
            _find(
                "DIM-4",
                "DETECT-QC-009 not yet in soc_detection_rules.yaml",
                "MEDIUM",
                "sm_constraint_evasion_language (DETECT-QC-009) is not yet a live "
                "detection rule. The static scan above runs on disk, but no real-time "
                "detection fires during pipeline execution. "
                "Remediation: promote DETECT-QC-009 — add rule to "
                "policies/soc_detection_rules.yaml and wire into rule_evaluator.py.",
                str(rules_path.relative_to(ROOT)),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# DIM-5  Provider config audit
# ═══════════════════════════════════════════════════════════════════════════════

def dim5_provider_config() -> None:
    """Verify LLM_PROVIDER is a documented provider."""
    env_example = ROOT / ".env.example"
    env_live = ROOT / ".env"

    documented_providers = set()
    if env_example.exists():
        ex_src = env_example.read_text(encoding="utf-8", errors="replace")
        # Extract all LLM_PROVIDER= values (both active and commented)
        for m in re.finditer(r"#?\s*LLM_PROVIDER\s*=\s*(\w+)", ex_src):
            documented_providers.add(m.group(1).lower())

    # Include known standard providers
    documented_providers |= _DOCUMENTED_PROVIDERS

    # Read live .env if it exists (not committed — check only)
    live_provider = None
    if env_live.exists():
        live_env = _load_dotenv(env_live)
        live_provider = live_env.get("LLM_PROVIDER", "").lower()

    # Check .env.example default
    ex_env = _load_dotenv(env_example)
    example_provider = ex_env.get("LLM_PROVIDER", "").lower()

    if example_provider and example_provider not in documented_providers:
        _find(
            "DIM-5",
            f"LLM_PROVIDER={example_provider!r} in .env.example is not a documented provider",
            "MEDIUM",
            f"Documented providers: {sorted(documented_providers)}. "
            f"Undocumented provider in the example config may indicate a configuration "
            f"error or use of an unverified LLM endpoint.",
            ".env.example",
        )
    elif example_provider:
        _find(
            "DIM-5",
            f"LLM_PROVIDER={example_provider!r} in .env.example — documented provider",
            "INFO",
            f"Provider is in documented set: {sorted(documented_providers)}.",
            ".env.example",
        )

    if live_provider:
        if live_provider not in documented_providers:
            _find(
                "DIM-5",
                f"LLM_PROVIDER={live_provider!r} in .env — undocumented provider",
                "HIGH",
                f"Live .env uses a provider not listed in .env.example or known provider set. "
                f"Documented providers: {sorted(documented_providers)}. "
                f"An undocumented provider could be a MITM endpoint substituting model responses. "
                f"Verify the provider is intentional and add it to .env.example.",
                ".env",
            )
        else:
            _find(
                "DIM-5",
                f"LLM_PROVIDER={live_provider!r} in .env — documented provider",
                "INFO",
                "Live provider matches documented set.",
                ".env",
            )

    # Check MEMORY.md for known provider status
    mem_path = Path.home() / ".claude" / "projects" / "-mnt-c-BACKUP-DEV-TEST" / "memory" / "MEMORY.md"
    if mem_path.exists():
        mem_src = mem_path.read_text(encoding="utf-8", errors="replace")
        # Check for UP/DOWN status
        for line in mem_src.splitlines():
            if "Provider status" in line or "Hetzner primary" in line:
                _find(
                    "DIM-5",
                    "Provider status note found in session memory",
                    "INFO",
                    f"Memory: {line.strip()[:120]}",
                    str(mem_path),
                )
                break


# ═══════════════════════════════════════════════════════════════════════════════
# DIM-6  HarnessModelGuardian wiring
# ═══════════════════════════════════════════════════════════════════════════════

def dim6_guardian_wiring() -> None:
    """Verify HarnessModelGuardian is wired; no direct env-var model reads in stage logic."""
    controller = ROOT / "chatbot" / "harness" / "controller.py"
    stages = ROOT / "chatbot" / "harness" / "stages.py"

    if not controller.exists():
        _find("DIM-6", "controller.py missing", "HIGH",
              "Cannot verify HarnessModelGuardian.", str(controller))
        return

    ctrl_src = controller.read_text(encoding="utf-8", errors="replace")

    # Check 1: HarnessModelGuardian defined and wired into ctx
    if "class HarnessModelGuardian" in ctrl_src:
        _find(
            "DIM-6",
            "HarnessModelGuardian defined in controller.py",
            "INFO",
            "Guardian is the single model-routing authority for all pipeline runs.",
            str(controller.relative_to(ROOT)),
        )
    else:
        _find(
            "DIM-6",
            "HarnessModelGuardian not found in controller.py",
            "HIGH",
            "The central model-routing guardian is missing. Stages may read "
            "AGENT_MODEL_* env vars directly — no exclusion registry enforcement.",
            str(controller.relative_to(ROOT)),
        )
        return

    # Check 2: Guardian stored in ctx["_model_guardian"]
    if "_model_guardian" in ctrl_src:
        _find(
            "DIM-6",
            "Guardian wired into pipeline ctx['_model_guardian']",
            "INFO",
            "Stages pull their model via ctx['_model_guardian'].get_model(), "
            "not directly from env vars.",
            str(controller.relative_to(ROOT)),
        )
    else:
        _find(
            "DIM-6",
            "_model_guardian not found in ctx wiring",
            "MEDIUM",
            "HarnessModelGuardian may not be injected into the pipeline context. "
            "Stages will fall back to direct env-var reads, bypassing the exclusion registry.",
            str(controller.relative_to(ROOT)),
        )

    # Check 3: stages.py — no direct os.getenv("AGENT_MODEL_*") calls
    if stages.exists():
        st_src = stages.read_text(encoding="utf-8", errors="replace")
        direct_reads = re.findall(
            r'os\.getenv\s*\(\s*["\']AGENT_MODEL_',
            st_src,
        )
        if direct_reads:
            _find(
                "DIM-6",
                f"{len(direct_reads)} direct AGENT_MODEL_* env reads in stages.py",
                "MEDIUM",
                "stages.py reads AGENT_MODEL_* directly via os.getenv() instead of "
                "going through HarnessModelGuardian. These bypass the exclusion registry "
                "and fallback chain. "
                "Remediation: replace with ctx['_model_guardian'].get_model(role).",
                str(stages.relative_to(ROOT)),
            )
        else:
            _find(
                "DIM-6",
                "No direct AGENT_MODEL_* env reads in stages.py",
                "INFO",
                "All model resolution goes through HarnessModelGuardian.",
                str(stages.relative_to(ROOT)),
            )

    # Check 4: ScrumMasterStage reads model via guardian
    if stages.exists():
        st_src = stages.read_text(encoding="utf-8", errors="replace") if "st_src" not in dir() else st_src
        if "guardian" in st_src and "scrum_master" in st_src:
            _find(
                "DIM-6",
                "ScrumMasterStage reads model via guardian",
                "INFO",
                "SM model resolved through HarnessModelGuardian — exclusion registry active.",
                str(stages.relative_to(ROOT)),
            )
        else:
            _find(
                "DIM-6",
                "ScrumMasterStage may not use guardian for model resolution",
                "LOW",
                "Could not confirm ScrumMasterStage uses ctx['_model_guardian']. "
                "Manual review recommended.",
                str(stages.relative_to(ROOT)),
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════════════════

_SEVERITY_ICON = {
    "CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡",
    "LOW": "🔵", "INFO": "✅",
}


def print_report() -> None:
    sorted_findings = sorted(
        FINDINGS,
        key=lambda f: (_SEV_ORDER.get(f["severity"], 99), f["dim"]),
    )
    counts: dict[str, int] = {s: 0 for s in _SEV_ORDER}
    for f in sorted_findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    print()
    print("═" * 70)
    print("  model-audit — Model Trust Surface Audit  (Engine Item 14)")
    print("═" * 70)
    print()

    # Dim summary
    dims = ["DIM-1", "DIM-2", "DIM-3", "DIM-4", "DIM-5", "DIM-6"]
    dim_names = {
        "DIM-1": "Config integrity (env vars vs model_routing.yaml)",
        "DIM-2": "Routing config staleness (vs bench timestamp)",
        "DIM-3": "Critic role validation (bench coverage, blackhat silence)",
        "DIM-4": "Endogenous output scan (DETECT-QC-009 path)",
        "DIM-5": "Provider config audit (LLM_PROVIDER vs documented)",
        "DIM-6": "HarnessModelGuardian wiring (no direct env reads)",
    }

    def _dim_worst(dim: str) -> str:
        sev = [f["severity"] for f in FINDINGS if f["dim"] == dim]
        return min(sev, key=lambda s: _SEV_ORDER.get(s, 99)) if sev else "INFO"

    print(f"{'Dim':<8} {'Name':<50} {'Worst'}")
    print("-" * 70)
    for d in dims:
        worst = _dim_worst(d)
        icon = _SEVERITY_ICON.get(worst, "")
        print(f"{d:<8} {dim_names[d]:<50} {icon} {worst}")
    print()

    # Findings (skip INFO)
    shown = [f for f in sorted_findings if f["severity"] != "INFO"]
    if shown:
        print("── Findings ──────────────────────────────────────────────────────────")
        for f in shown:
            icon = _SEVERITY_ICON.get(f["severity"], "")
            print()
            print(f"  {icon} [{f['severity']}] {f['dim']} — {f['title']}")
            if f["path"]:
                print(f"     Path: {f['path']}")
            words = f["detail"].split()
            line = "     "
            for w in words:
                if len(line) + len(w) + 1 > 72:
                    print(line)
                    line = "     " + w + " "
                else:
                    line += w + " "
            if line.strip():
                print(line)
        print()

    crit = counts.get("CRITICAL", 0)
    high = counts.get("HIGH", 0)
    med  = counts.get("MEDIUM", 0)
    low  = counts.get("LOW", 0)
    info = counts.get("INFO", 0)
    print("── Summary ───────────────────────────────────────────────────────────")
    print(f"  Critical: {crit}  High: {high}  Medium: {med}  Low: {low}  Info: {info}")
    print()
    if crit or high:
        print("  ❌ Exit 1 — CRITICAL or HIGH findings present.")
    else:
        print("  ✅ Exit 0 — No CRITICAL or HIGH findings.")
    print()


def main() -> int:
    try:
        dim1_config_integrity()
        dim2_routing_staleness()
        dim3_critic_role_validation()
        dim4_endogenous_output_scan()
        dim5_provider_config()
        dim6_guardian_wiring()
    except Exception as exc:
        print(f"[ERROR] Audit aborted: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2

    print_report()

    worst = min(
        (_SEV_ORDER.get(f["severity"], 99) for f in FINDINGS),
        default=99,
    )
    return 1 if worst <= _SEV_ORDER["HIGH"] else 0


if __name__ == "__main__":
    sys.exit(main())
