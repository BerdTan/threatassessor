"""
TMeval — ThreatAssessor Red-Team Harness
========================================
Two-phase adversarial probe of the TA pipeline.

  Phase 1 (outside-in): POST adversarial MMDs to the live API, extract
    governance_signals from the SSE complete event, assert DETECT rules fired.

  Phase 2 (inside-out): Inject crafted governance_signals directly into
    RuleEvaluator and BouncerStage. No API needed.

Usage:
  python3 scripts/tmeval/tmeval_run.py --phase1 --api-url http://localhost:8000
  python3 scripts/tmeval/tmeval_run.py --phase2
  python3 scripts/tmeval/tmeval_run.py --all --api-url http://localhost:8000
  python3 scripts/tmeval/tmeval_run.py --phase1 --dry-run

Exit codes: 0 = all PASS, 1 = any FAIL or error.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

# ── Project root on sys.path ──────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TMEVAL_DIR = Path(__file__).resolve().parent
_CORPUS_DIR = _TMEVAL_DIR / "adversarial_corpus"
_CASES_DIR  = _TMEVAL_DIR / "cases"

# ANSI colours
_GRN = "\033[92m"
_RED = "\033[91m"
_YLW = "\033[93m"
_DIM = "\033[2m"
_RST = "\033[0m"
_BLD = "\033[1m"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _pass(msg: str) -> str:
    return f"{_GRN} PASS{_RST}  {msg}"


def _fail(msg: str) -> str:
    return f"{_RED} FAIL{_RST}  {msg}"


def _warn(msg: str) -> str:
    return f"{_YLW} WARN{_RST}  {msg}"


def _bar(n: int, total: int, width: int = 6) -> str:
    if total == 0:
        return "░" * width + "  0/0"
    filled = round(width * n / total)
    return "█" * filled + "░" * (width - filled) + f" {n}/{total}"


def _write_synthetic_queue(case_name: str, mmd_path: Path, missing_rules: List[str],
                            gov_signals: dict) -> Path:
    """Write a failed Phase 1 case to the synthetic queue for the brain flywheel."""
    report_dir = _ROOT / "report" / "brain" / "synthetic_queue"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = report_dir / f"tmeval_{ts}_{case_name}.mmd"

    header_lines = [f"%% TMeval FAIL: expected {r} not fired" for r in missing_rules]
    # Add signal hint for each missing rule
    for rule_id in missing_rules:
        # Minimal signal hint: show what the evaluator saw for key fields
        hint = f"%%   arch: {case_name} — {mmd_path.name}"
        header_lines.append(hint)

    mmd_content = mmd_path.read_text(encoding="utf-8")
    out.write_text("\n".join(header_lines) + "\n" + mmd_content, encoding="utf-8")
    return out


# ── Phase 1: outside-in REST probe ───────────────────────────────────────────

def _consume_sse(response) -> Tuple[Optional[dict], Optional[str]]:
    """
    Consume an SSE stream from a requests streaming response.
    Returns (governance_signals, error_message).
    """
    event_type = None
    data_buf: List[str] = []
    gov_signals = None
    error_msg = None

    for raw_line in response.iter_lines(decode_unicode=True):
        line = raw_line.strip() if raw_line else ""

        if not line:
            # Dispatch buffered event
            if event_type == "complete" and data_buf:
                data_str = " ".join(data_buf)
                try:
                    payload = json.loads(data_str)
                    gov_signals = payload.get("governance_signals")
                except json.JSONDecodeError:
                    error_msg = f"JSON decode failed on complete event: {data_str[:100]}"
            elif event_type == "error" and data_buf:
                data_str = " ".join(data_buf)
                try:
                    payload = json.loads(data_str)
                    error_msg = payload.get("error", data_str[:120])
                except json.JSONDecodeError:
                    error_msg = data_str[:120]
            event_type = None
            data_buf = []
            if gov_signals is not None or error_msg is not None:
                break
            continue

        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_buf.append(line[len("data:"):].strip())

    return gov_signals, error_msg


def run_phase1(api_url: str, dry_run: bool = False, timeout: int = 180) -> Tuple[int, int]:
    """
    Run Phase 1 outside-in cases.
    Returns (passed, total).
    """
    try:
        import requests
    except ImportError:
        print(f"{_RED}ERROR:{_RST} `requests` not installed — pip install requests")
        return 0, 0

    from chatbot.harness.rule_evaluator import RuleEvaluator

    cases_path = _CASES_DIR / "phase1_cases.yaml"
    cases = _load_yaml(cases_path).get("cases", [])

    api_key = os.getenv("TA_API_KEY", "dev-key-local")
    endpoint = f"{api_url.rstrip('/')}/api/v1/analyze-stream"

    # Collect total rules per domain for coverage matrix
    evaluator = RuleEvaluator()
    domain_total: Dict[str, int] = {}
    domain_tested: Dict[str, int] = {}
    for rule in evaluator._rules:
        d = rule.get("domain", "?")
        domain_total[d] = domain_total.get(d, 0) + 1

    passed = 0
    total = len(cases)
    failed_cases: List[str] = []

    _sep = "═" * 56
    print(f"\n{_BLD}TMeval — Phase 1: Outside-in adversarial probe{_RST}")
    print(_sep)

    if dry_run:
        print(f"{_YLW}[dry-run] validating cases only — no API calls{_RST}\n")
        for case in cases:
            mmd_path = _TMEVAL_DIR / case["file"]
            status = _pass(case["name"]) if mmd_path.exists() else _fail(f"{case['name']} — file not found: {mmd_path}")
            print(status)
        print(f"\n{total} cases validated (dry-run)\n")
        return total, total

    for case in cases:
        name        = case["name"]
        mmd_path    = _TMEVAL_DIR / case["file"]
        expected    = set(case.get("expected_rules", []))
        must_not    = set(case.get("must_not_fire", []))
        tags        = case.get("tags", [])

        if not mmd_path.exists():
            print(_fail(f"{name:<28} — corpus file missing: {mmd_path.name}"))
            failed_cases.append(name)
            continue

        # POST to API
        try:
            with mmd_path.open("rb") as f:
                resp = requests.post(
                    endpoint,
                    headers={"TA-API-KEY": api_key},
                    files={"architecture_file": (mmd_path.name, f, "text/plain")},
                    data={
                        "ssp_profile": "low_risk_cloud",
                        "enable_ssp": "true",
                        "include_validation": "true",
                    },
                    stream=True,
                    timeout=timeout,
                )
        except requests.exceptions.ConnectionError:
            print(_fail(f"{name:<28} — API unreachable at {api_url}"))
            failed_cases.append(name)
            continue
        except requests.exceptions.Timeout:
            print(_fail(f"{name:<28} — timeout after {timeout}s"))
            failed_cases.append(name)
            continue

        if resp.status_code != 200:
            print(_fail(f"{name:<28} — HTTP {resp.status_code}: {resp.text[:80]}"))
            failed_cases.append(name)
            continue

        gov_signals, err = _consume_sse(resp)
        if err:
            print(_fail(f"{name:<28} — SSE error: {err[:80]}"))
            failed_cases.append(name)
            continue
        if gov_signals is None:
            print(_fail(f"{name:<28} — no governance_signals in complete event"))
            failed_cases.append(name)
            continue

        # Evaluate rules against extracted signals
        findings = evaluator.evaluate(gov_signals, arch_name=name, run_id="tmeval-p1")
        fired_ids = {f["unmapped"]["rule_id"] for f in findings}

        missing   = expected - fired_ids
        fp_fired  = must_not & fired_ids
        extra     = fired_ids - expected - must_not

        # Domain coverage tracking
        for tag in tags:
            if tag not in ("FP_CHECK",):
                domain_tested[tag] = domain_tested.get(tag, 0) + (1 if not missing else 0)

        if not missing and not fp_fired:
            detail = ""
            if expected:
                detail = f"{', '.join(sorted(expected))} fired"
                if extra:
                    detail += f" (+{len(extra)} extra)"
            else:
                detail = f"0 rules fired (FP clean)"
            print(_pass(f"{name:<28} {_DIM}{detail}{_RST}"))
            passed += 1
        else:
            details = []
            if missing:
                details.append(f"expected not fired: {', '.join(sorted(missing))}")
            if fp_fired:
                details.append(f"FP fired: {', '.join(sorted(fp_fired))}")
            print(_fail(f"{name:<28} {', '.join(details)}"))
            failed_cases.append(name)

            # Write to synthetic queue
            if missing:
                q_path = _write_synthetic_queue(name, mmd_path, list(missing), gov_signals)
                print(f"         {_DIM}→ synthetic queue: {q_path.name}{_RST}")

    # Domain coverage matrix
    all_domains = sorted(domain_total.keys())
    print(f"\n{_DIM}Domain coverage (tested rules vs domain total):{_RST}")
    for d in all_domains:
        tested = domain_tested.get(d, 0)
        bar = _bar(tested, domain_total[d])
        print(f"  {d:<6} {bar}")

    if failed_cases:
        print(f"\n{_DIM}Failed: {', '.join(failed_cases)}{_RST}")
    print(f"\nPhase 1: {_GRN if passed == total else _RED}{passed}/{total} PASS{_RST}\n")

    return passed, total


# ── Phase 2: inside-out fault injection ──────────────────────────────────────

def run_phase2() -> Tuple[int, int]:
    """
    Run Phase 2 inside-out cases.
    Returns (passed, total).
    """
    from chatbot.harness.rule_evaluator import RuleEvaluator
    from chatbot.harness.controller import PipelineContext, BlockedPipelineError
    from chatbot.harness.stages import BouncerStage

    cases_path = _CASES_DIR / "phase2_cases.yaml"
    cases = _load_yaml(cases_path).get("cases", [])

    evaluator = RuleEvaluator()

    passed = 0
    total = len(cases)
    failed_cases: List[str] = []

    _sep = "═" * 56
    print(f"\n{_BLD}TMeval — Phase 2: Inside-out fault injection{_RST}")
    print(_sep)

    bouncer = BouncerStage()

    # Domain coverage
    domain_tested: Dict[str, int] = {}
    domain_total: Dict[str, int] = {}
    for rule in evaluator._rules:
        d = rule.get("domain", "?")
        domain_total[d] = domain_total.get(d, 0) + 1

    for case in cases:
        name             = case["name"]
        signals          = case.get("signals", {})
        expected         = set(case.get("expected_rules", []))
        expect_blocked   = bool(case.get("expected_blocked", False))
        tags             = case.get("tags", [])

        # ── Rule evaluation ───────────────────────────────────────────────────
        findings  = evaluator.evaluate(signals, arch_name=name, run_id="tmeval-p2")
        fired_ids = {f["unmapped"]["rule_id"] for f in findings}
        missing   = expected - fired_ids
        extra     = fired_ids - expected

        # ── Bouncer test ──────────────────────────────────────────────────────
        actual_blocked = False
        bouncer_error: Optional[str] = None
        if expect_blocked or any(tag == "BOUNCER" for tag in tags):
            ctx = PipelineContext({
                "governance_signals": signals,
                "_run_id":            "tmeval-p2",
                "architecture_name":  name,
                "_outbound_blocked":  False,
                "_preflight_blocked": False,
            })
            try:
                bouncer.run(ctx)
                actual_blocked = False
            except BlockedPipelineError:
                actual_blocked = True
            except Exception as exc:
                bouncer_error = str(exc)

        # ── Verdict ───────────────────────────────────────────────────────────
        rule_ok    = not missing
        blocker_ok = (expect_blocked == actual_blocked) if bouncer_error is None else False

        # Domain coverage
        for tag in tags:
            if tag not in ("FP_CHECK", "BOUNCER"):
                domain_tested[tag] = domain_tested.get(tag, 0) + (1 if rule_ok else 0)

        if rule_ok and blocker_ok:
            detail_parts = []
            if expected:
                detail_parts.append(f"{', '.join(sorted(expected))} fired")
            else:
                detail_parts.append("0 rules fired (clean)")
            if expect_blocked:
                detail_parts.append("pipeline blocked ✓")
            detail = "; ".join(detail_parts)
            print(_pass(f"{name:<36} {_DIM}{detail}{_RST}"))
            passed += 1
        else:
            details = []
            if missing:
                details.append(f"expected not fired: {', '.join(sorted(missing))}")
            if not blocker_ok:
                if bouncer_error:
                    details.append(f"bouncer error: {bouncer_error[:60]}")
                else:
                    details.append(
                        f"blocked={actual_blocked} (expected {expect_blocked})"
                    )
            print(_fail(f"{name:<36} {', '.join(details)}"))
            failed_cases.append(name)

    # Domain coverage matrix
    all_domains = sorted(domain_total.keys())
    print(f"\n{_DIM}Domain coverage (cases passing vs domain total rules):{_RST}")
    for d in all_domains:
        tested = domain_tested.get(d, 0)
        bar = _bar(tested, domain_total[d])
        print(f"  {d:<6} {bar}")

    if failed_cases:
        print(f"\n{_DIM}Failed: {', '.join(failed_cases)}{_RST}")
    print(f"\nPhase 2: {_GRN if passed == total else _RED}{passed}/{total} PASS{_RST}\n")

    return passed, total


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="TMeval — ThreatAssessor red-team harness (Phase 1 + Phase 2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--phase1",   action="store_true", help="Run Phase 1 (outside-in REST probe)")
    parser.add_argument("--phase2",   action="store_true", help="Run Phase 2 (inside-out fault injection)")
    parser.add_argument("--all",      action="store_true", help="Run both phases")
    parser.add_argument("--api-url",  default="http://localhost:8000", help="TA API base URL [%(default)s]")
    parser.add_argument("--dry-run",  action="store_true", help="Phase 1: validate cases only, no API calls")
    parser.add_argument("--timeout",  type=int, default=180, help="Phase 1 SSE timeout per case in seconds [%(default)s]")
    args = parser.parse_args()

    if not (args.phase1 or args.phase2 or args.all):
        parser.print_help()
        return 1

    run_p1 = args.phase1 or args.all
    run_p2 = args.phase2 or args.all

    total_passed = 0
    total_cases  = 0

    if run_p1:
        p, t = run_phase1(args.api_url, dry_run=args.dry_run, timeout=args.timeout)
        total_passed += p
        total_cases  += t

    if run_p2:
        p, t = run_phase2()
        total_passed += p
        total_cases  += t

    if total_cases > 0:
        colour = _GRN if total_passed == total_cases else _RED
        print(f"{_BLD}Overall: {colour}{total_passed}/{total_cases} PASS{_RST}\n")

    return 0 if total_passed == total_cases else 1


if __name__ == "__main__":
    sys.exit(main())
