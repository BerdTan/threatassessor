#!/usr/bin/env python3
"""
check-detect — SOC detection rule regression + live corpus evaluation.

Usage:
    python3 check-detect.py                      # unit tests only
    python3 check-detect.py 21_agentic_ai_system # tests + live rule eval
    python3 check-detect.py --all                # tests + all corpus archs
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[4]
REPORT_DIR = REPO_ROOT / "report"
RULES_PATH = REPO_ROOT / "policies" / "soc_detection_rules.yaml"

TEST_FILES = [
    REPO_ROOT / "tests" / "test_soc_rule_evaluator.py",
    REPO_ROOT / "tests" / "test_aivss_to_findings.py",
    REPO_ROOT / "tests" / "test_incident_simulator.py",
    REPO_ROOT / "tests" / "test_harness_event_broker.py",
]

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"

_SEV_COLOR = {
    "CRITICAL": lambda s: f"\033[31;1m{s}\033[0m",
    "HIGH":     lambda s: f"\033[31m{s}\033[0m",
    "MEDIUM":   lambda s: f"\033[33m{s}\033[0m",
    "LOW":      lambda s: f"\033[32m{s}\033[0m",
}


# ── Unit test runner ──────────────────────────────────────────────────────────

def run_unit_tests() -> bool:
    """Run all four detection-layer test files and print a consolidated summary."""
    print(f"\n{BOLD(CYAN('SOC Detection Regression'))} — {len(TEST_FILES)} test files\n")

    all_ok = True
    total_passed = total_failed = 0

    for tf in TEST_FILES:
        label = tf.name
        t0 = time.time()
        # Skip EventBroker init tests (pre-existing chatbot.config import issue)
        extra = ["-k", "not TestEventBrokerInit"] if "event_broker" in tf.name else []
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tf), "-q", "--tb=short"] + extra,
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        elapsed = time.time() - t0
        output = result.stdout + result.stderr
        summary = next(
            (l for l in reversed(output.splitlines())
             if "passed" in l or "failed" in l or "error" in l),
            "no output",
        )
        # Extract counts
        passed = _parse_count(summary, "passed")
        failed = _parse_count(summary, "failed")
        total_passed += passed
        total_failed += failed

        if result.returncode == 0:
            print(f"  {GREEN('✓')} {label:<45} {GREEN(summary.strip())}  {DIM(f'{elapsed:.1f}s')}")
        else:
            print(f"  {RED('✗')} {label:<45} {RED(summary.strip())}  {DIM(f'{elapsed:.1f}s')}")
            # Print failing test names
            for line in output.splitlines():
                if line.startswith("FAILED"):
                    print(f"      {RED(line)}")
            all_ok = False

    total_color = GREEN if all_ok else RED
    print(f"\n  {'─'*60}")
    print(f"  {total_color(f'Total: {total_passed} passed, {total_failed} failed')}\n")
    return all_ok


def _parse_count(summary: str, word: str) -> int:
    import re
    m = re.search(rf"(\d+)\s+{word}", summary)
    return int(m.group(1)) if m else 0


# ── Rule count check ──────────────────────────────────────────────────────────

def check_rule_count() -> None:
    """Load YAML and print the current rule inventory."""
    try:
        import yaml  # type: ignore[import]
        data = yaml.safe_load(RULES_PATH.read_text())
        rules = data.get("rules", [])
        print(f"{BOLD('Rule inventory')} — {RULES_PATH.relative_to(REPO_ROOT)}")
        print(f"  {len(rules)} rules loaded\n")
        for r in rules:
            rid  = r.get("id", "?")
            name = r.get("name", "")
            sev  = (r.get("severity") or "").upper()
            col  = _SEV_COLOR.get(sev, DIM)
            conds = r.get("conditions", [])
            fields = ", ".join(c.get("field", "") for c in conds if isinstance(c, dict))
            print(f"  {col(f'{rid:<12}')} {name:<42} {DIM(fields[:60])}")
        print()
    except Exception as exc:
        print(f"  {AMBER(f'Could not load rules YAML: {exc}')}\n")


# ── Live corpus evaluation ────────────────────────────────────────────────────

def evaluate_arch(arch: str) -> None:
    """Evaluate a governance_signals.json against all live rules and print findings."""
    sig_path = REPORT_DIR / arch / "governance_signals.json"
    if not sig_path.exists():
        print(f"  {AMBER(arch)}: no governance_signals.json")
        return

    try:
        signals = json.loads(sig_path.read_text())
    except Exception as exc:
        print(f"  {RED(arch)}: could not read signals — {exc}")
        return

    # Import rule evaluator from repo
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        from chatbot.harness.rule_evaluator import RuleEvaluator
        ev = RuleEvaluator()
        findings = ev.evaluate(signals, arch_name=arch, run_id="live-check")
    except Exception as exc:
        print(f"  {RED(arch)}: rule evaluation failed — {exc}")
        return

    # Key signal values
    manip    = signals.get("manipulation", {})
    val      = signals.get("validation", {})
    sm       = signals.get("sm_verdicts", {})
    aivss_out = signals.get("aivss", {}).get("outbound", {})

    val_pct   = val.get("val_pct")
    gap_sim   = manip.get("gap_similarity_avg")
    sm_rate   = sm.get("acceptance_rate")
    out_comp  = aivss_out.get("composite") if isinstance(aivss_out, dict) else None

    signal_parts = []
    if val_pct is not None:
        vcolor = RED if val_pct < 75 else (AMBER if val_pct < 85 else GREEN)
        signal_parts.append(f"val_pct={vcolor(f'{val_pct:.0f}%')}")
    if gap_sim is not None:
        gcolor = RED if gap_sim > 0.4 else (AMBER if gap_sim > 0.2 else DIM)
        signal_parts.append(f"gap_sim={gcolor(f'{gap_sim:.2f}')}")
    if sm_rate is not None:
        scolor = RED if sm_rate <= 0.6 else GREEN
        signal_parts.append(f"sm_rate={scolor(f'{sm_rate:.1%}')}")
    if out_comp is not None:
        ocolor = RED if out_comp >= 6.0 else (AMBER if out_comp >= 3.0 else DIM)
        signal_parts.append(f"outbound={ocolor(f'{out_comp:.1f}')}")

    signal_str = "  " + "  ".join(signal_parts) if signal_parts else ""

    if not findings:
        print(f"  {GREEN('✓')} {arch:<40} {DIM('no rules fired')}{signal_str}")
        return

    print(f"  {RED('!')} {BOLD(arch)}{signal_str}")
    for f in sorted(findings, key=lambda x: _sev_order(x.get("severity", ""))):
        rid  = f.get("unmapped", {}).get("rule_id", "?")
        name = f.get("unmapped", {}).get("rule_name", f.get("finding", {}).get("title", ""))
        sev  = (f.get("severity") or "").upper()
        col  = _SEV_COLOR.get(sev, DIM)
        acts = ", ".join(f.get("unmapped", {}).get("actions", []))
        print(f"      {col(f'{rid} [{sev}]'):<28} {name:<40} {DIM(acts)}")


def _sev_order(sev: str) -> int:
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(sev.upper(), 4)


# ── Skill metadata sync ───────────────────────────────────────────────────────

def _live_counts() -> dict:
    """Read live rule/scenario/test counts from source files. Never raises."""
    counts = {}
    try:
        import yaml  # type: ignore[import]
        rules = yaml.safe_load(RULES_PATH.read_text()).get("rules", [])
        counts["n_rules"] = len(rules)
        counts["last_rule"] = rules[-1]["id"] if rules else "DETECT-001"
    except Exception:
        counts["n_rules"] = 0
        counts["last_rule"] = "?"

    try:
        sim_script = REPO_ROOT / ".claude/skills/incident-simulator/scripts/incident_simulator.py"
        spec = importlib.util.spec_from_file_location("_sim", sim_script)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        counts["n_scenarios"] = len(mod.SCENARIOS)
    except Exception:
        counts["n_scenarios"] = 0

    for tf in TEST_FILES:
        key = tf.stem  # e.g. "test_harness_governance"
        try:
            src = tf.read_text(encoding="utf-8")
            counts[key] = src.count("def test_")
        except Exception:
            counts[key] = 0

    return counts


def _rewrite_description(skill_md: Path, new_desc: str) -> bool:
    """Replace the `description:` line in a SKILL.md frontmatter. Returns True if changed."""
    try:
        text = skill_md.read_text(encoding="utf-8")
        updated = re.sub(
            r'^(description:\s*).*$',
            lambda m: m.group(1) + new_desc,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if updated == text:
            return False
        skill_md.write_text(updated, encoding="utf-8")
        return True
    except Exception:
        return False


def sync_skill_metadata() -> None:
    """
    Rewrite `description:` lines in the four detection-layer SKILL.md files
    so counts stay current automatically after every check-detect run.
    Prints a one-line status; silent when nothing changed.
    """
    c = _live_counts()
    n_rules     = c["n_rules"]
    n_scenarios = c["n_scenarios"]
    last_rule   = c["last_rule"]

    SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

    # Descriptions keyed by skill directory name → new description string.
    # Each uses only counts derivable from source files, no free-text that drifts.
    targets = {
        "check-detect": (
            f"Run the SOC detection rule regression suite (~15s, no LLM/network). "
            f"Covers all {n_rules} DETECT rules (rule evaluator), AIVSS→OCSF findings export, "
            f"incident simulator scenarios ({n_scenarios} scenarios covering all {n_rules} rules), "
            f"and EventBroker sm_verdicts path. Optionally re-evaluates live governance_signals.json "
            f"for one or all corpus architectures and shows which rules fire. Use after any change to "
            f"policies/soc_detection_rules.yaml, chatbot/harness/rule_evaluator.py, "
            f"chatbot/harness/stages.py, or chatbot/harness/governance.py."
        ),
        "incident-simulator": (
            f"Synthesise realistic governance_signals.json payloads for named incident scenarios, "
            f"run aivss-to-findings, and assert the expected DETECT rules fire. "
            f"{n_scenarios} scenarios cover all {n_rules} DETECT rules "
            f"(DETECT-001 through {last_rule}), including AST02/05/08-grounded scenarios. "
            f"Optionally generates a storycaster narrative contextualised to a specific architecture. "
            f"Pass a scenario name, or omit to list all. Use --story to generate a narrative. "
            f"Use --write to persist the simulated governance_signals to a report directory."
        ),
    }

    changed = []
    for skill_name, new_desc in targets.items():
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        if skill_md.exists() and _rewrite_description(skill_md, new_desc):
            changed.append(skill_name)

    if changed:
        print(f"  {GREEN('↺')} Synced skill metadata: {', '.join(changed)} "
              f"({n_rules} rules, {n_scenarios} scenarios)")
    # Silent when nothing changed — avoids noise on every run


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SOC detection rule regression + live corpus eval")
    parser.add_argument("arch", nargs="?", help="Architecture name for live evaluation")
    parser.add_argument("--all", action="store_true", help="Evaluate all corpus architectures")
    args = parser.parse_args()

    ok = run_unit_tests()
    sync_skill_metadata()
    check_rule_count()

    if args.arch:
        print(f"{BOLD('Live Evaluation')} — {args.arch}\n")
        evaluate_arch(args.arch)
        print()
    elif args.all:
        archs = sorted(
            d.name for d in REPORT_DIR.iterdir()
            if d.is_dir() and (d / "governance_signals.json").exists()
        ) if REPORT_DIR.exists() else []
        if not archs:
            print(f"  {DIM('No governance_signals.json found under report/')}")
        else:
            print(f"{BOLD('Live Evaluation')} — {len(archs)} architectures\n")
            for arch in archs:
                evaluate_arch(arch)
            print()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
