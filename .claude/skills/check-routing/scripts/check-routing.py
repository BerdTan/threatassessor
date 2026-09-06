#!/usr/bin/env python3
"""
check-routing — Smart routing regression + live decision check.

Usage:
    python3 check-routing.py              # unit + integration tests
    python3 check-routing.py --live       # + live routing for all boxed arches
    python3 check-routing.py --live --show-policy  # + policy dump
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TEST_FILE = REPO_ROOT / "tests" / "unit" / "test_smart_router.py"
POLICY_PATH = REPO_ROOT / "policies" / "model_routing.yaml"
REPORT_DIR = REPO_ROOT / "report"

sys.path.insert(0, str(REPO_ROOT))


# ── Test runner ───────────────────────────────────────────────────────────────

def run_unit_tests() -> bool:
    venv_python = REPO_ROOT / ".venv" / "bin" / "python3"
    python = str(venv_python) if venv_python.exists() else sys.executable

    cmd = [python, "-m", "pytest", str(TEST_FILE), "-v", "--tb=short", "-q"]
    t0 = time.perf_counter()
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    output = result.stdout + result.stderr
    lines = output.splitlines()

    passed = failed = 0
    for line in lines:
        if " passed" in line:
            import re
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
        if " failed" in line:
            import re
            m = re.search(r"(\d+) failed", line)
            if m:
                failed = int(m.group(1))

    status = "✅ PASS" if result.returncode == 0 else "❌ FAIL"
    print(f"\n{status}  {passed} passed, {failed} failed  ({elapsed:.1f}s)")

    if result.returncode != 0:
        print("\n── Failures ──────────────────────────────────────────────")
        in_fail = False
        for line in lines:
            if line.startswith("FAILED") or line.startswith("ERROR"):
                in_fail = True
            if in_fail:
                print(" ", line)
            if line.startswith("=") and in_fail:
                in_fail = False

    return result.returncode == 0


# ── Policy check ──────────────────────────────────────────────────────────────

def check_policy(show: bool = False) -> bool:
    print("\n── model_routing.yaml ────────────────────────────────────────")
    if not POLICY_PATH.exists():
        print(f"  ❌ MISSING: {POLICY_PATH}")
        return False

    try:
        import yaml
        policy = yaml.safe_load(POLICY_PATH.read_text()) or {}
    except Exception as exc:
        print(f"  ❌ Parse error: {exc}")
        return False

    ok = True
    checks = [
        ("tiers.brain_fast.brain_vs_gold_delta_min", "tiers", "brain_fast", "brain_vs_gold_delta_min"),
        ("tiers.brain_fast.corpus_hits_min",         "tiers", "brain_fast", "corpus_hits_min"),
        ("tiers.api_only.brain_vs_gold_delta_min",   "tiers", "api_only",   "brain_vs_gold_delta_min"),
        ("tiers.api_only.corpus_hits_min",           "tiers", "api_only",   "corpus_hits_min"),
        ("overrides.aivss_composite_full_moe_threshold", "overrides", None, "aivss_composite_full_moe_threshold"),
    ]
    for label, *keys in checks:
        try:
            val = policy
            for k in keys:
                if k:
                    val = val[k]
            print(f"  ✅ {label} = {val}")
        except (KeyError, TypeError):
            print(f"  ❌ MISSING: {label}")
            ok = False

    if show:
        print("\n  Full policy:")
        for line in POLICY_PATH.read_text().splitlines():
            if not line.strip().startswith("#") and line.strip():
                print(f"    {line}")

    return ok


# ── Live routing decisions ────────────────────────────────────────────────────

def live_routing() -> None:
    print("\n── Live routing decisions ────────────────────────────────────")

    boxed = sorted(REPORT_DIR.glob("*/boxing_results.json"))
    if not boxed:
        print("  No boxing_results.json found — run /ta-boxing first")
        return

    # Filter out _boxing_bot dirs
    boxed = [p for p in boxed if "_boxing_bot" not in p.parent.name
             and "_boxing_deteng" not in p.parent.name]

    sys.path.insert(0, str(REPO_ROOT))
    try:
        from chatbot.harness.smart_router import select_mode
    except Exception as exc:
        print(f"  ❌ Could not import smart_router: {exc}")
        return

    col_w = 32
    print(f"  {'Architecture':<{col_w}} {'Mode':<12} {'Delta':>8}  {'Hits':>5}  Rationale")
    print("  " + "─" * 90)

    mode_counts: dict = {}
    for boxing_path in boxed:
        arch_name = boxing_path.parent.name
        try:
            d = select_mode(arch_name)
        except Exception as exc:
            print(f"  {arch_name:<{col_w}} {'ERROR':<12} — {exc}")
            continue

        delta_str = f"{d.brain_vs_gold_delta:+.3f}" if d.brain_vs_gold_delta is not None else "  n/a"
        hits_str  = str(d.corpus_hits) if d.corpus_hits is not None else "n/a"
        mode_icon = {"brain_fast": "🧠", "api_only": "⚙️ ", "full_moe": "🔬"}.get(d.mode, "?")
        short_rationale = d.rationale[:55] + "…" if len(d.rationale) > 55 else d.rationale

        print(f"  {arch_name:<{col_w}} {mode_icon} {d.mode:<10} {delta_str:>8}  {hits_str:>5}  {short_rationale}")
        mode_counts[d.mode] = mode_counts.get(d.mode, 0) + 1

    print()
    for mode, count in sorted(mode_counts.items()):
        print(f"  {mode}: {count} arch(s)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="check-routing — smart routing regression")
    ap.add_argument("--live",        action="store_true", help="Show live routing for all boxed arches")
    ap.add_argument("--show-policy", action="store_true", help="Dump full policy config")
    args = ap.parse_args()

    print("check-routing — smart routing regression")
    print(f"  Test file : {TEST_FILE.relative_to(REPO_ROOT)}")
    print(f"  Policy    : {POLICY_PATH.relative_to(REPO_ROOT)}")
    print(f"  Report dir: {REPORT_DIR.relative_to(REPO_ROOT)}")

    tests_ok  = run_unit_tests()
    policy_ok = check_policy(show=args.show_policy)

    if args.live:
        live_routing()

    overall = tests_ok and policy_ok
    print("\n" + ("✅ All checks passed" if overall else "❌ Some checks failed"))
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
