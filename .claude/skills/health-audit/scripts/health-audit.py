#!/usr/bin/env python3
"""
health-audit — structural health audit for ThreatAssessor.

Catches orphaned code, broken seams, and coverage gaps without needing the API.

Usage:
    python3 health-audit.py           # full audit, findings table
    python3 health-audit.py --fix     # (future) auto-fix safe items
    python3 health-audit.py --check routes   # single check only
    python3 health-audit.py --check detect
    python3 health-audit.py --check fixtures
    python3 health-audit.py --check env
    python3 health-audit.py --check skills
    python3 health-audit.py --check adapters
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/health-audit/scripts/ -> ROOT


# ── helpers ──────────────────────────────────────────────────────────────────

def _red(s): return f"\033[31m{s}\033[0m"
def _yellow(s): return f"\033[33m{s}\033[0m"
def _green(s): return f"\033[32m{s}\033[0m"
def _bold(s): return f"\033[1m{s}\033[0m"


FINDINGS: list[tuple[str, str, str, str]] = []  # (area, item, status, action)


def finding(area: str, item: str, status: str, action: str) -> None:
    FINDINGS.append((area, item, status, action))


# ── Check 1: DETECT rule / test-scenario coverage gap ───────────────────────

def check_detect_coverage() -> int:
    """Rules in soc_detection_rules.yaml with no scenario in test_incident_simulator.py."""
    rules_file = ROOT / "policies" / "soc_detection_rules.yaml"
    sim_file   = ROOT / "tests" / "test_incident_simulator.py"

    if not rules_file.exists():
        finding("detect-coverage", "soc_detection_rules.yaml missing", "❌", "restore file")
        return 1
    if not sim_file.exists():
        finding("detect-coverage", "test_incident_simulator.py missing", "❌", "restore file")
        return 1

    # Extract unique live rule IDs (not legacy_id lines)
    # Lines look like: "- id: DETECT-QC-001" or "  - id: DETECT-QC-001"
    live_ids: set[str] = set()
    for line in rules_file.read_text().splitlines():
        if "legacy_id" in line:
            continue
        m = re.search(r"\bid:\s+(DETECT-[A-Z]+-\d+)", line)
        if m:
            live_ids.add(m.group(1))

    # IDs referenced in simulator
    sim_text = sim_file.read_text()
    covered = set(re.findall(r"DETECT-[A-Z]+-\d+", sim_text))

    uncovered = sorted(live_ids - covered)
    if uncovered:
        for rid in uncovered:
            finding(
                "detect-coverage",
                f"{rid} — no test scenario",
                "⚠",
                "add scenario to test_incident_simulator.py",
            )
    else:
        finding("detect-coverage", f"all {len(live_ids)} rules covered", "✅", "—")

    return len(uncovered)


# ── Check 2: FastAPI routes vs openapi.yaml drift ────────────────────────────

def check_route_openapi_drift() -> int:
    """Endpoints registered in routes/ but absent from openapi.yaml, and vice versa."""
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        finding("route-drift", "PyYAML not installed — skipped", "⚠", "pip install pyyaml")
        return 0

    openapi_file = ROOT / "openapi.yaml"
    routes_dir   = ROOT / "chatbot" / "api" / "routes"

    if not openapi_file.exists():
        finding("route-drift", "openapi.yaml missing", "❌", "restore file")
        return 1

    # Parse OpenAPI paths (normalize trailing slash, lowercase)
    oa_data   = yaml.safe_load(openapi_file.read_text())
    oa_paths  = {p.rstrip("/").lower() for p in oa_data.get("paths", {}).keys()}

    # Extract FastAPI route paths from decorator lines, add /api/v1 prefix
    # Pattern: @router.METHOD("path") — capture the first string argument
    route_pat = re.compile(r'@router\.\w+\(\s*["\']([^"\']*)["\']')
    prefix_pat = re.compile(r'APIRouter\(.*?prefix=["\']([^"\']+)["\']')

    fa_paths: set[str] = set()
    for f in sorted(routes_dir.glob("*.py")):
        text = f.read_text()
        # Detect this file's router prefix (default /api/v1)
        pm = prefix_pat.search(text)
        prefix = pm.group(1).rstrip("/") if pm else "/api/v1"

        for m in route_pat.finditer(text):
            raw = m.group(1)
            # Skip health/root endpoints that live outside /api/v1
            if raw.startswith("http"):
                continue
            full = (prefix + "/" + raw.lstrip("/")).rstrip("/").lower()
            fa_paths.add(full)

    # Exclude root / utility paths that are never in openapi.yaml
    _exclude = {"/", "/health", "/dashboard", "/docs", "/redoc", "/openapi.json"}

    in_fa_not_oa = sorted((fa_paths - oa_paths) - _exclude)
    in_oa_not_fa = sorted(oa_paths - fa_paths)

    issues = 0
    for p in in_fa_not_oa:
        finding("route-drift", f"{p} — in code, missing from openapi.yaml", "⚠",
                "add to openapi.yaml or remove endpoint")
        issues += 1
    for p in in_oa_not_fa:
        if p in _exclude or p in {"", "/docs", "/openapi.json", "/redoc"}:
            continue
        finding("route-drift", f"{p} — in openapi.yaml, missing from routes/", "⚠",
                "add route or remove from openapi.yaml")
        issues += 1

    if issues == 0:
        finding("route-drift", "routes and openapi.yaml in sync", "✅", "—")

    return issues


# ── Check 3: Orphaned test fixtures ─────────────────────────────────────────

def check_orphaned_fixtures() -> int:
    """MMD files in tests/data/architectures/ not referenced in any test file."""
    arch_dir  = ROOT / "tests" / "data" / "architectures"
    tests_dir = ROOT / "tests"

    if not arch_dir.exists():
        finding("fixtures", "tests/data/architectures/ missing", "❌", "restore directory")
        return 1

    mmd_files = sorted(arch_dir.glob("*.mmd"))

    # Build a text corpus of all test files + scripts + skills + CLAUDE.md + README
    corpus_files = list(tests_dir.glob("*.py")) + [
        ROOT / "CLAUDE.md",
        ROOT / "README.md",
    ]
    # Also scan scripts/ and .claude/skills/ — they reference arch names without .mmd extension
    for d in [ROOT / "scripts", ROOT / ".claude" / "skills"]:
        if d.exists():
            corpus_files.extend(d.rglob("*.py"))
            corpus_files.extend(d.rglob("*.sh"))
    corpus = "\n".join(
        f.read_text(errors="ignore") for f in corpus_files if f.exists()
    )

    orphans = []
    for mmd in mmd_files:
        stem = mmd.stem   # e.g. "00_serviceentry"
        name = mmd.name   # e.g. "00_serviceentry.mmd"
        if stem not in corpus and name not in corpus:
            orphans.append(mmd.name)

    if orphans:
        for o in orphans:
            finding("fixtures", f"{o} — not referenced in any test", "⚠",
                    "add to a test suite or remove")
    else:
        finding("fixtures", f"all {len(mmd_files)} MMD fixtures referenced", "✅", "—")

    return len(orphans)


# ── Check 4: .env.example drift ──────────────────────────────────────────────

def check_env_vars() -> int:
    """Keys in .env.example not read in Python; os.getenv calls with no .env.example entry."""
    env_example = ROOT / ".env.example"
    if not env_example.exists():
        finding("env-vars", ".env.example missing", "❌", "restore .env.example")
        return 1

    # Keys declared in .env.example — both active lines and commented-out vars
    # Commented vars (# KEY=value) are intentional documentation of optional keys
    declared: set[str] = set()
    for line in env_example.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading comment marker for commented-out key lines
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        key = line.split("=", 1)[0].strip()
        if re.match(r"^[A-Z_][A-Z0-9_]*$", key):
            declared.add(key)

    # Keys consumed in Python files
    py_files = list(ROOT.rglob("*.py"))
    # Exclude venv, node_modules, hidden dirs
    py_files = [
        f for f in py_files
        if ".venv" not in f.parts
        and "node_modules" not in f.parts
        and not any(p.startswith(".") and p not in (".claude",) for p in f.parts[len(ROOT.parts):])
    ]

    consumed: set[str] = set()
    # Pattern 1: os.getenv("KEY") / os.environ.get("KEY") / os.environ["KEY"]
    env_get_pat = re.compile(r'os\.(?:getenv|environ\.get)\(["\']([A-Z_][A-Z0-9_]*)["\']')
    env_brk_pat = re.compile(r'os\.environ\[["\']([A-Z_][A-Z0-9_]*)["\']')
    # Pattern 2: dict-based provider config — "api_key_env": "KEY" / "base_url_env": "KEY" / etc.
    env_dict_pat = re.compile(r'"(?:api_key_env|base_url_env|env_var|key_env|env_key|region_env)"\s*:\s*"([A-Z_][A-Z0-9_]*)"')
    for f in py_files:
        text = f.read_text(errors="ignore")
        consumed.update(env_get_pat.findall(text))
        consumed.update(env_brk_pat.findall(text))
        consumed.update(env_dict_pat.findall(text))

    # Pattern 3: ${KEY} substitution in JSON/YAML config files
    config_var_pat = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)\}')
    for config_dir in [ROOT / "chatbot" / "config"]:
        if config_dir.exists():
            for cf in config_dir.rglob("*.json"):
                consumed.update(config_var_pat.findall(cf.read_text(errors="ignore")))
            for cf in config_dir.rglob("*.yaml"):
                consumed.update(config_var_pat.findall(cf.read_text(errors="ignore")))

    # Skip well-known framework/system vars that don't belong in .env.example
    framework_vars = {
        # OS / shell
        "PATH", "HOME", "USER", "SHELL", "PWD", "TMPDIR", "TERM", "EDITOR",
        # Python / venv
        "PYTHONPATH", "VIRTUAL_ENV",
        # GitHub Actions / CI
        "CI", "GITHUB_TOKEN", "GITHUB_REF", "GITHUB_REPOSITORY",
        "GITHUB_SHA", "GITHUB_WORKSPACE", "GITHUB_EVENT_NAME",
        "PR_NUMBER", "REPO", "BASE_REF",
        # GCP / cloud credential conventions (standard SDK vars, not TA-specific)
        "GOOGLE_APPLICATION_CREDENTIALS", "GCP_REGION",
        # TA CI script vars (not the main service config)
        "TA_API_KEY", "TA_API_URL",
        # Client-side connector vars (set in the caller's env, not the TA server)
        "TA_API_BASE_URL", "TM_API_BASE_URL",
    }
    consumed -= framework_vars

    # Also exclude from both directions: GCP/cloud SDK vars, client-side connector vars,
    # and vars explicitly documented in .env.example as reserved/future (not yet wired)
    both_exclude = framework_vars | {
        "GOOGLE_APPLICATION_CREDENTIALS", "GCP_REGION",
        "TA_API_BASE_URL", "TM_API_BASE_URL", "TM_API_KEY",
        "TM_MCP_KEY", "TM_PICKLE_KEY",
        # TACO mini vars — reserved for Phase 3/4; documented ahead of implementation
        "AGENT_MODEL_TACO_BRAIN", "AGENT_MODEL_TACO_HARNESS",
        "AGENT_MODEL_TACO_RAG", "AGENT_MODEL_TACO_CRITIC",
    }
    orphaned_keys = sorted((declared - consumed) - both_exclude)
    # Filter noise: single-word vars ≤3 chars are example-code artefacts, not real config
    undocumented  = sorted(
        k for k in (consumed - declared) - framework_vars
        if len(k) > 3
    )

    issues = 0
    for k in orphaned_keys:
        finding("env-vars", f"{k} — in .env.example, never read in Python", "⚠",
                "remove from .env.example or add usage")
        issues += 1
    for k in undocumented:
        finding("env-vars", f"{k} — read in Python, not in .env.example", "⚠",
                "add to .env.example with description")
        issues += 1

    if issues == 0:
        finding("env-vars",
                f".env.example and Python os.getenv calls in sync ({len(declared)} keys)",
                "✅", "—")

    return issues


# ── Check 5: Orphaned skill directories ──────────────────────────────────────

def check_orphaned_skills() -> int:
    """Skill dirs in .claude/skills/ that are structurally incomplete (no runnable entry point)."""
    skills_dir = ROOT / ".claude" / "skills"

    if not skills_dir.exists():
        finding("skills", ".claude/skills/ missing", "❌", "restore directory")
        return 1

    incomplete = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name

        # A skill is "runnable" if it has scripts/*.py or scripts/*.sh or a top-level *.md
        scripts_dir = skill_dir / "scripts"
        has_script = (
            scripts_dir.exists()
            and any(scripts_dir.glob("*.py")) or any(scripts_dir.glob("*.sh"))
            if scripts_dir.exists() else False
        )
        has_md = any(skill_dir.glob("*.md"))

        if not has_script and not has_md:
            incomplete.append(name)

    if incomplete:
        for name in incomplete:
            finding("skills", f"{name} — no script or definition file", "⚠",
                    "add scripts/<name>.py or <name>.md, or remove dir")
    else:
        total = sum(1 for d in skills_dir.iterdir() if d.is_dir())
        finding("skills", f"all {total} skill dirs have entry points", "✅", "—")

    return len(incomplete)


# ── Check 6: Adapter class usage ─────────────────────────────────────────────

def check_adapter_usage() -> int:
    """Adapter classes in chatbot/adapters/ not imported anywhere in the API layer."""
    adapters_dir = ROOT / "chatbot" / "adapters"
    if not adapters_dir.exists():
        finding("adapters", "chatbot/adapters/ missing", "❌", "restore directory")
        return 1

    # Find all concrete adapter class names (non-Base, non-Abstract)
    adapter_classes: dict[str, Path] = {}
    class_pat = re.compile(r"^class (\w+Adapter)\b")
    for f in adapters_dir.glob("*.py"):
        for line in f.read_text().splitlines():
            m = class_pat.match(line)
            if m:
                cls = m.group(1)
                if cls not in ("BaseAdapter",):
                    adapter_classes[cls] = f

    # Search the entire codebase for each class name
    search_dirs = [
        ROOT / "chatbot" / "api",
        ROOT / "taclaw",
        ROOT / "mcp_server",
        ROOT / "mcp_connector",
        ROOT / "scripts",
    ]
    all_py = []
    for d in search_dirs:
        if d.exists():
            all_py.extend(d.rglob("*.py"))

    corpus = "\n".join(f.read_text(errors="ignore") for f in all_py)

    orphaned = []
    for cls in sorted(adapter_classes):
        if cls not in corpus:
            orphaned.append(cls)

    if orphaned:
        for cls in orphaned:
            finding("adapters", f"{cls} — defined but never imported outside adapters/", "⚠",
                    "check if still needed; remove if dead")
    else:
        finding("adapters", f"all {len(adapter_classes)} adapter classes imported", "✅", "—")

    return len(orphaned)


# ── Check 7: JSON schema files referenced ────────────────────────────────────

def check_schema_references() -> int:
    """JSON schemas in chatbot/schemas/ not referenced in Python or OpenAPI."""
    schemas_dir = ROOT / "chatbot" / "schemas"
    if not schemas_dir.exists():
        finding("schemas", "chatbot/schemas/ missing (or moved)", "⚠",
                "update check if schemas moved")
        return 0

    schema_files = sorted(schemas_dir.glob("*.json"))
    if not schema_files:
        finding("schemas", "no JSON schemas found", "⚠", "verify schemas dir")
        return 0

    # Search Python + YAML + openapi.yaml for each schema filename
    py_files = list(ROOT.rglob("*.py"))
    py_files = [f for f in py_files if ".venv" not in f.parts]
    corpus_files = py_files + [ROOT / "openapi.yaml"]
    corpus = "\n".join(
        f.read_text(errors="ignore") for f in corpus_files if f.exists()
    )

    orphaned = []
    for sf in schema_files:
        if sf.stem not in corpus and sf.name not in corpus:
            orphaned.append(sf.name)

    if orphaned:
        for o in orphaned:
            finding("schemas", f"{o} — not referenced in code or openapi.yaml", "⚠",
                    "reference in route or remove")
    else:
        finding("schemas", f"all {len(schema_files)} schema files referenced", "✅", "—")

    return len(orphaned)


# ── output ────────────────────────────────────────────────────────────────────

def print_table() -> None:
    if not FINDINGS:
        print(_green("No findings."))
        return

    col_w = [6, 58, 6, 46]
    header = ["Area", "Item", "Status", "Proposed Action"]
    sep    = "  ".join("-" * w for w in col_w)

    print()
    print(_bold("  ".join(f"{h:<{w}}" for h, w in zip(header, col_w))))
    print(sep)
    for area, item, status, action in FINDINGS:
        row = f"{area:<{col_w[0]}}  {item:<{col_w[1]}}  {status:<{col_w[2]}}  {action:<{col_w[3]}}"
        if "❌" in status:
            print(_red(row))
        elif "⚠" in status:
            print(_yellow(row))
        else:
            print(_green(row))
    print()

    issues   = sum(1 for _, _, s, _ in FINDINGS if s in ("❌", "⚠"))
    clean    = sum(1 for _, _, s, _ in FINDINGS if s == "✅")
    print(f"  {_bold(str(issues))} issue(s)   {_green(str(clean))} clean")
    print()


# ── main ─────────────────────────────────────────────────────────────────────

CHECKS = {
    "detect":   check_detect_coverage,
    "routes":   check_route_openapi_drift,
    "fixtures": check_orphaned_fixtures,
    "env":      check_env_vars,
    "skills":   check_orphaned_skills,
    "adapters": check_adapter_usage,
    "schemas":  check_schema_references,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="ThreatAssessor structural health audit")
    parser.add_argument("--check", choices=list(CHECKS), help="Run a single check")
    args = parser.parse_args()

    checks = {args.check: CHECKS[args.check]} if args.check else CHECKS

    total_issues = 0
    for name, fn in checks.items():
        print(f"  checking {name}...", end="\r")
        total_issues += fn()

    print(" " * 40, end="\r")  # clear progress line
    print_table()

    return 1 if total_issues > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
