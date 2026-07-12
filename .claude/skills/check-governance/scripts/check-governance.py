#!/usr/bin/env python3
"""
check-governance — Governance guardrail regression + live signal check.

Usage:
    python3 check-governance.py                  # unit tests only
    python3 check-governance.py 21_agentic_ai_system   # tests + live check
    python3 check-governance.py --all            # tests + all corpus archs
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[4]
REPORT_DIR = REPO_ROOT / "report"
TEST_FILE  = REPO_ROOT / "tests" / "test_harness_governance.py"

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"


# ── Unit test runner ──────────────────────────────────────────────────────────

def run_unit_tests() -> bool:
    print(f"\n{BOLD(CYAN('Governance Regression'))} — {DIM(str(TEST_FILE.relative_to(REPO_ROOT)))}")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TEST_FILE), "-v", "--tb=short", "-q"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    elapsed = time.time() - t0

    # Parse summary line
    output = result.stdout + result.stderr
    summary_line = next(
        (l for l in reversed(output.splitlines()) if "passed" in l or "failed" in l or "error" in l),
        ""
    )

    if result.returncode == 0:
        print(f"  {GREEN(summary_line.strip())}  ({elapsed:.1f}s)")
    else:
        print(f"  {RED(summary_line.strip())}  ({elapsed:.1f}s)")
        # Print failing test details
        in_fail = False
        for line in output.splitlines():
            if line.startswith("FAILED") or line.startswith("ERROR"):
                print(f"  {RED(line)}")
                in_fail = True
            elif in_fail and line.startswith("_"):
                print(f"  {DIM(line)}")
            elif in_fail and line.strip():
                print(f"    {line}")
            else:
                in_fail = False

    return result.returncode == 0


# ── Live signal checker ───────────────────────────────────────────────────────

def _sev_color(sev: str) -> str:
    s = (sev or "LOW").upper()
    if s == "CRITICAL": return RED(s)
    if s == "HIGH":     return RED(s)
    if s == "MEDIUM":   return AMBER(s)
    return GREEN(s)


def check_live_signals(arch: str) -> None:
    gs_path = REPORT_DIR / arch / "governance_signals.json"
    if not gs_path.exists():
        print(f"\n  {DIM(f'No governance_signals.json for {arch} — run analysis first')}")
        return

    with open(gs_path) as f:
        gs = json.load(f)

    print(f"\n{BOLD('Live Signal Check')} — {arch}")

    # Exploitation
    expl = gs.get("exploitation", {})
    sev  = expl.get("severity", "LOW")
    pats = expl.get("injection_patterns", [])
    cats = list(expl.get("injection_categories", {}).keys())
    blocked = expl.get("blocked", False)
    blocked_tag = f"  {RED('BLOCKED')}" if blocked else ""
    cat_tag = f"  cats={cats}" if cats else ""
    print(f"  exploitation:   {_sev_color(sev)}{blocked_tag}"
          + (f"  — {DIM(', '.join(pats[:3]))}" if pats else "  — no injection patterns")
          + DIM(cat_tag))

    # Leakage
    leak = gs.get("leakage", {})
    pii  = leak.get("pii_indicators", [])
    creds = leak.get("sensitive_keywords", [])
    leak_sev = "CRITICAL" if (pii and any("nric" in p.lower() for p in pii)) or creds \
               else "HIGH" if pii else "LOW"
    print(f"  leakage:        {_sev_color(leak_sev)}"
          + (f"  — PII: {DIM(str(pii[:2]))}" if pii else "  — no PII indicators")
          + (f"  creds: {DIM(str(creds[:1]))}" if creds else ""))

    # Manipulation
    manip = gs.get("manipulation", {})
    m_sev = manip.get("severity", "LOW")
    swing = manip.get("confidence_swing")
    div   = manip.get("critic_divergence_score")
    m_detail = []
    if swing is not None: m_detail.append(f"swing={swing:.2f}")
    if div   is not None: m_detail.append(f"divergence={div}")
    print(f"  manipulation:   {_sev_color(m_sev)}"
          + (f"  — {DIM(', '.join(m_detail))}" if m_detail else "  — no signals"))

    # Sovereignty
    sov   = gs.get("sovereignty", {})
    s_sev = sov.get("severity", "LOW")
    zdr   = sov.get("zdr_signals", [])
    xbnds = sov.get("cross_boundary_nodes", [])
    print(f"  sovereignty:    {_sev_color(s_sev)}"
          + (f"  — zdr_signals: {DIM(zdr[0][:60])}" if zdr else
             f"  — {DIM(str(xbnds[0][:50]))} " if xbnds else "  — no flags"))

    # Overall
    overall = gs.get("overall_risk_level") \
              or max([expl.get("severity","LOW"), leak_sev, m_sev, s_sev],
                     key=lambda x: ["LOW","MEDIUM","HIGH","CRITICAL"].index(x))
    print(f"  overall_risk:   {_sev_color(overall)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Governance guardrail regression + live check")
    parser.add_argument("arch", nargs="?", help="Architecture name to check live signals for")
    parser.add_argument("--all", action="store_true", help="Check all corpus architectures")
    args = parser.parse_args()

    ok = run_unit_tests()

    if args.arch:
        check_live_signals(args.arch)
    elif args.all:
        archs = sorted(
            d.name for d in REPORT_DIR.iterdir()
            if d.is_dir() and (d / "governance_signals.json").exists()
        )
        if not archs:
            print(f"\n  {DIM('No governance_signals.json files found under report/')}")
        else:
            print(f"\n{BOLD('Live Signal Check')} — {len(archs)} architectures")
            for arch in archs:
                check_live_signals(arch)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
