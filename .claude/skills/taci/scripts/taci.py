#!/usr/bin/env python3
"""
taci — ThreatAssessor CI workflow validator.

Runs the PR reviewer locally (no GitHub token needed) and validates
the workflow configuration for common issues.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

API_URL = os.environ.get("TA_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("API_KEY", "")

WORKFLOW_FILE = ROOT / ".github/workflows/ta-review.yml"
REVIEW_SCRIPT = ROOT / "scripts/ci/ta_pr_review.py"
API_SCRIPTS   = [
    ROOT / "scripts/api/api_start.sh",
    ROOT / "scripts/api/api_stop.sh",
    ROOT / "scripts/api/api_restart.sh",
    ROOT / "scripts/api/api_status.sh",
]

# ── Terminal helpers ──────────────────────────────────────────────────────────

def _c(code, text): return f"\033[{code}m{text}\033[0m"
OK   = lambda t: _c("32", f"✓ {t}")
FAIL = lambda t: _c("31", f"✗ {t}")
WARN = lambda t: _c("33", f"⚠ {t}")
BOLD = lambda t: _c("1", t)


# ── Workflow checks ───────────────────────────────────────────────────────────

def check_workflow() -> bool:
    print(f"\n{BOLD('── Workflow config checks ──────────────────────────────')}")
    ok = True

    # Workflow file exists
    if WORKFLOW_FILE.exists():
        print(OK(f"Workflow file exists: {WORKFLOW_FILE.relative_to(ROOT)}"))
    else:
        print(FAIL(f"Workflow file missing: {WORKFLOW_FILE.relative_to(ROOT)}"))
        ok = False
        return ok

    content = WORKFLOW_FILE.read_text()

    # Secrets referenced
    for secret in ("TA_API_KEY", "OPENROUTER_API_KEY"):
        if f"secrets.{secret}" in content:
            print(OK(f"Secret referenced: {secret}"))
        else:
            print(FAIL(f"Secret not referenced in workflow: {secret}"))
            ok = False

    # Venv step present
    if "python3 -m venv .venv" in content or ".venv/bin/pip" in content:
        print(OK("Venv creation step present"))
    else:
        print(FAIL("No venv creation step — api_start.sh requires .venv"))
        ok = False

    # .env write step present
    if "Write .env" in content or "cat > .env" in content:
        print(OK(".env write step present"))
    else:
        print(WARN(".env write step not found — API may not get secrets"))

    # Review script path correct
    if "scripts/ci/ta_pr_review.py" in content:
        print(OK("Review script path correct"))
    else:
        print(FAIL("scripts/ci/ta_pr_review.py not referenced in workflow"))
        ok = False

    # Review script exists
    if REVIEW_SCRIPT.exists():
        print(OK(f"Review script exists: {REVIEW_SCRIPT.relative_to(ROOT)}"))
    else:
        print(FAIL(f"Review script missing: {REVIEW_SCRIPT.relative_to(ROOT)}"))
        ok = False

    # API scripts executable
    for script in API_SCRIPTS:
        if script.exists() and os.access(script, os.X_OK):
            print(OK(f"Executable: {script.name}"))
        elif script.exists():
            print(FAIL(f"Not executable: {script.name} — run --fix-perms"))
            ok = False
        else:
            print(WARN(f"Script not found: {script.name}"))

    return ok


def fix_perms():
    print(f"\n{BOLD('── Fixing script permissions ────────────────────────────')}")
    for script in API_SCRIPTS:
        if script.exists():
            result = subprocess.run(
                ["git", "update-index", "--chmod=+x", str(script.relative_to(ROOT))],
                cwd=ROOT, capture_output=True, text=True
            )
            if result.returncode == 0:
                print(OK(f"Marked executable: {script.name}"))
            else:
                print(FAIL(f"Failed: {script.name} — {result.stderr.strip()}"))
    print("\nCommit the permission changes: git commit -m 'fix: mark API scripts executable'")


# ── API health check ──────────────────────────────────────────────────────────

def check_api() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{API_URL}/health", timeout=5) as r:
            import json
            data = json.loads(r.read())
            if data.get("status") == "healthy":
                print(OK(f"API healthy at {API_URL}"))
                return True
            else:
                print(FAIL(f"API unhealthy: {data.get('status')}"))
                return False
    except Exception as e:
        print(FAIL(f"API not reachable at {API_URL}: {e}"))
        print("  Start API: ./scripts/api/api_start.sh")
        return False


# ── Dry-run analysis ──────────────────────────────────────────────────────────

def run_dry(mmd_path: str | None, base_ref: str = "master"):
    print(f"\n{BOLD('── PR reviewer dry-run ─────────────────────────────────')}")

    env = {
        **os.environ,
        "TA_API_URL": API_URL,
        "TA_API_KEY": API_KEY,
        "BASE_REF": base_ref,
        # No GITHUB_TOKEN → comment prints to stdout
    }

    if mmd_path:
        env["TA_FORCE_MMD"] = str(Path(mmd_path).resolve())

    result = subprocess.run([sys.executable, str(REVIEW_SCRIPT)], cwd=ROOT, env=env)
    return result.returncode


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="taci — TA CI workflow validator")
    parser.add_argument("--dry-run", action="store_true", help="Run PR reviewer against changed .mmd files")
    parser.add_argument("--arch", metavar="FILE", help="Run against a specific .mmd file")
    parser.add_argument("--check-workflow", action="store_true", help="Check workflow config only (no API needed)")
    parser.add_argument("--fix-perms", action="store_true", help="Mark API scripts executable via git")
    parser.add_argument("--base-ref", default="master", help="Base branch for git diff (default: master)")
    args = parser.parse_args()

    # Default: do everything if no flags
    if not any([args.dry_run, args.arch, args.check_workflow, args.fix_perms]):
        args.check_workflow = True
        args.dry_run = True

    exit_code = 0

    if args.fix_perms:
        fix_perms()
        return 0

    if args.check_workflow:
        if not check_workflow():
            exit_code = 1

    if args.dry_run or args.arch:
        if not check_api():
            exit_code = 1
        else:
            rc = run_dry(args.arch, args.base_ref)
            if rc != 0:
                exit_code = rc

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
