#!/usr/bin/env python3
"""
TAclaw Test Suite MVP

Runs structural, quality, and regression assertions against a live TA instance.
Designed for external developers validating their TAclaw deployment.

Usage:
    python tests/taclaw/run_suite.py                     # full suite
    python tests/taclaw/run_suite.py --smoke             # simple_webapp only
    python tests/taclaw/run_suite.py --eval-only         # re-eval cached outputs
    python tests/taclaw/run_suite.py --update-baseline   # accept current output as baseline

Flags:
    --api-url URL         TA API base URL (default: $TA_API_URL or http://localhost:8000)
    --api-key KEY         TM-API-KEY (default: $API_KEY)
    --timeout SECS        Per-fixture timeout in seconds (default: 300)
    --output-dir DIR      Directory to write cached results (default: tests/data/taclaw/<fixture>/)

Exit codes:
    0   All structural assertions pass
    1   One or more structural assertions failed or a fixture job errored
    2   Configuration error (missing API key, bad URL)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    print("httpx required: pip install httpx", file=sys.stderr)
    sys.exit(2)

# ── paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "tests" / "data" / "taclaw"

# ── fixture definitions ───────────────────────────────────────────────────────

FIXTURES: list[dict] = [
    {
        "name":               "simple_webapp",
        "path":               DATA_DIR / "simple_webapp",
        "target_type":        "directory",
        "expected_gate":      "PASS",
        "gate_is_hard":       False,        # gate depends on LLM; advisory only
        "min_techniques":     3,
        "required_techniques": ["T1190"],   # Exploit Public-Facing Application
        "aivss_range":        (2.0, 8.0),
        "expected_detect_min": 0,
        "adapter_hint":       "TerraformAdapter",
    },
    {
        "name":               "mixed_iac",
        "path":               DATA_DIR / "mixed_iac",
        "target_type":        "directory",
        "expected_gate":      "PASS",
        "gate_is_hard":       False,
        "min_techniques":     3,
        "required_techniques": [],
        "aivss_range":        (2.0, 9.0),
        "expected_detect_min": 0,
        "adapter_hint":       "multi-adapter",
    },
    {
        "name":               "high_risk",
        "path":               DATA_DIR / "high_risk",
        "target_type":        "directory",
        "expected_gate":      "BLOCK",
        "gate_is_hard":       False,        # depends on model; advisory
        "min_techniques":     5,
        "required_techniques": ["T1059"],   # Command and Scripting Interpreter (exec)
        "aivss_range":        (6.0, 10.0),
        "expected_detect_min": 1,
        "adapter_hint":       "MermaidAdapter",
    },
    {
        "name":               "ecommerce_api",
        "path":               DATA_DIR / "ecommerce_api",
        "target_type":        "directory",
        "expected_gate":      "PASS",
        "gate_is_hard":       False,
        "min_techniques":     3,
        "required_techniques": ["T1552"],   # Unsecured Credentials (card data in request)
        "aivss_range":        (3.0, 8.0),
        "expected_detect_min": 0,
        "adapter_hint":       "OpenAPIAdapter",
    },
]

# ── HTTP client ───────────────────────────────────────────────────────────────

class TAClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 300):
        self.base = base_url.rstrip("/")
        self.headers = {"TM-API-KEY": api_key}
        self.timeout = timeout

    def post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=self.timeout) as c:
            r = c.post(f"{self.base}{path}", json=body, headers=self.headers)
            r.raise_for_status()
            return r.json()

    def get(self, path: str) -> dict:
        with httpx.Client(timeout=60) as c:
            r = c.get(f"{self.base}{path}", headers=self.headers)
            r.raise_for_status()
            return r.json()

    def poll_job(self, job_id: str, timeout: int) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.get(f"/api/v1/taclaw/jobs/{job_id}")
            state = status.get("status", "")
            if state in ("completed", "failed", "blocked"):
                return status
            time.sleep(4)
        raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


# ── structural assertions ─────────────────────────────────────────────────────

REQUIRED_EXPORT_KEYS = ["gate", "assessment", "detect_findings", "otm", "tatb",
                        "brain_quality", "governance"]

def _structural(result: dict, fixture: dict) -> list[tuple[str, bool, str]]:
    """Return list of (assertion_label, passed, detail)."""
    checks: list[tuple[str, bool, str]] = []
    export = result.get("export", {})

    def ok(label: str, cond: bool, detail: str = "") -> None:
        checks.append((label, cond, detail))

    ok("job_completed", result.get("status") == "completed" or "gate" in result,
       f"status={result.get('status')}")

    ok("no_error", not result.get("error"), result.get("error", ""))

    ok("gate_present", "gate" in result or "gate" in export,
       "gate field missing from result and export")

    if fixture["gate_is_hard"]:
        actual_gate = result.get("gate") or export.get("gate", {}).get("result", "")
        ok("gate_matches", actual_gate == fixture["expected_gate"],
           f"expected={fixture['expected_gate']} got={actual_gate}")

    for key in REQUIRED_EXPORT_KEYS:
        ok(f"export.{key}_present", key in export and export[key] is not None,
           f"export.{key} missing")

    ok("routing_mode_present",
       bool(result.get("routing_mode")),
       f"routing_mode={result.get('routing_mode')!r}")

    ok("passport_present",
       bool(export.get("provenance", {}).get("agent_passport")),
       "export.provenance.agent_passport missing")

    ok("artifacts_found",
       (result.get("artifacts_found") or 0) >= 1,
       f"artifacts_found={result.get('artifacts_found')}")

    return checks


# ── quality eval ──────────────────────────────────────────────────────────────

def _quality(result: dict, fixture: dict) -> dict[str, int]:
    export = result.get("export", {})
    assessment = export.get("assessment", {})
    governance = export.get("governance", {})
    scores: dict[str, int] = {}

    # threat_coverage
    techniques = assessment.get("mitre_techniques", [])
    mn = fixture["min_techniques"]
    scores["threat_coverage"] = min(100, int(len(techniques) / mn * 100)) if mn else 100

    # key_techniques_present
    required = fixture.get("required_techniques", [])
    if required:
        present = [t for t in required if t in techniques]
        scores["key_techniques_present"] = int(len(present) / len(required) * 100)
    else:
        scores["key_techniques_present"] = 100

    # aivss_in_range
    aivss = governance.get("aivss_composite")
    lo, hi = fixture["aivss_range"]
    if aivss is not None:
        mid = (lo + hi) / 2
        scores["aivss_in_range"] = 100 if lo <= aivss <= hi else max(0, 100 - int(abs(aivss - mid) * 15))
    else:
        scores["aivss_in_range"] = 0

    # fidelity_adequate
    af = (result.get("adapter_metadata") or {}).get("adapters_fidelity", [])
    if af:
        adequate = sum(1 for f in af if f.get("node_coverage", 0) >= 0.7)
        scores["fidelity_adequate"] = int(adequate / len(af) * 100)
    else:
        scores["fidelity_adequate"] = 50

    # brain_quality_calibrated
    bq = export.get("brain_quality", {})
    bc = bq.get("brier_combined") if bq else None
    if bc is not None:
        scores["brain_quality_calibrated"] = 100 if bc < 0.3 else max(0, int((0.5 - min(bc, 0.5)) / 0.5 * 100))
    else:
        scores["brain_quality_calibrated"] = 50

    # detect_signal
    detect = export.get("detect_findings", [])
    emin = fixture["expected_detect_min"]
    scores["detect_signal"] = 100 if len(detect) >= emin else (
        int(len(detect) / max(emin, 1) * 100)
    )

    return scores


def _quality_score(scores: dict[str, int]) -> int:
    if not scores:
        return 0
    return round(sum(scores.values()) / len(scores))


# ── regression ───────────────────────────────────────────────────────────────

def _baseline_path(fixture: dict) -> Path:
    return fixture["path"] / "baseline.json"


def _load_baseline(fixture: dict) -> dict | None:
    bp = _baseline_path(fixture)
    if bp.exists():
        try:
            return json.loads(bp.read_text())
        except Exception:
            pass
    return None


def _save_baseline(fixture: dict, result: dict) -> None:
    export = result.get("export", {})
    assessment = export.get("assessment", {})
    baseline = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "gate": result.get("gate") or export.get("gate", {}).get("result"),
        "routing_mode": result.get("routing_mode"),
        "techniques": sorted(assessment.get("mitre_techniques", [])),
        "aivss_composite": export.get("governance", {}).get("aivss_composite"),
        "artifacts_found": result.get("artifacts_found"),
    }
    _baseline_path(fixture).write_text(json.dumps(baseline, indent=2))


def _regression(result: dict, fixture: dict) -> tuple[str, list[str], list[str]]:
    """Returns (status, regressions, additions). status ∈ {no_delta, +N techniques, -N techniques, no_baseline}."""
    baseline = _load_baseline(fixture)
    if not baseline:
        return "no_baseline", [], []

    export = result.get("export", {})
    current_techs = set(export.get("assessment", {}).get("mitre_techniques", []))
    baseline_techs = set(baseline.get("techniques", []))

    regressions = sorted(baseline_techs - current_techs)
    additions   = sorted(current_techs - baseline_techs)

    if regressions:
        status = f"-{len(regressions)} techniques"
    elif additions:
        status = f"+{len(additions)} techniques"
    else:
        status = "no delta"

    return status, regressions, additions


# ── job submission + result loading ──────────────────────────────────────────

def _cache_path(fixture: dict, output_dir: Path | None) -> Path:
    d = output_dir or fixture["path"]
    return d / "last_result.json"


def _run_fixture(fixture: dict, client: TAClient, output_dir: Path | None,
                 timeout: int) -> dict:
    payload: dict[str, Any] = {
        "target":      str(fixture["path"].resolve()),
        "target_type": fixture["target_type"],
        "arch_name":   fixture["name"],
        "ssp_profile": "low_risk_cloud",
    }
    queued = client.post("/api/v1/taclaw/run", payload)
    job_id = queued["job_id"]
    print(f"  → queued job_id={job_id} passport={queued.get('passport_id', '?')}")

    status = client.poll_job(job_id, timeout)
    result = status.get("result") or status
    result["status"] = status.get("status", "completed")
    result["error"]  = status.get("error")

    cp = _cache_path(fixture, output_dir)
    try:
        cp.write_text(json.dumps(result, indent=2))
    except Exception:
        pass

    return result


def _load_cached(fixture: dict, output_dir: Path | None) -> dict | None:
    cp = _cache_path(fixture, output_dir)
    if cp.exists():
        try:
            return json.loads(cp.read_text())
        except Exception:
            pass
    return None


# ── scorecard rendering ───────────────────────────────────────────────────────

def _gate_display(result: dict, fixture: dict) -> str:
    export = result.get("export", {})
    gate = result.get("gate") or export.get("gate", {}).get("result", "?")
    expected = fixture["expected_gate"]
    if gate == expected:
        return gate
    return f"{gate}(expected {expected})"


def _render_scorecard(rows: list[dict], api_url: str) -> None:
    print()
    print(f"TAclaw Test Suite — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"API: {api_url}")
    print()
    hdr = f"{'Fixture':<22} {'Gate':<14} {'Structural':<16} {'Quality':<12} {'Regression'}"
    print(hdr)
    print("-" * len(hdr))

    total = len(rows)
    passed = sum(1 for r in rows if r["structural_ok"])
    regressions = sum(1 for r in rows if r["regression"][1])  # has regressions list

    for r in rows:
        s_checks = r["structural_checks"]
        s_pass   = sum(1 for _, ok, _ in s_checks if ok)
        s_total  = len(s_checks)
        s_icon   = "✅" if r["structural_ok"] else "❌"

        q_score  = r["quality_score"]
        reg_status, reg_list, add_list = r["regression"]
        reg_icon = "⚠" if reg_list else ("✅" if reg_status == "no delta" else "")

        gate_str = _gate_display(r["result"], r["fixture"])
        print(
            f"{r['fixture']['name']:<22} "
            f"{gate_str:<14} "
            f"{s_icon} {s_pass}/{s_total:<10} "
            f"{q_score}/100     "
            f"{reg_icon} {reg_status}"
        )

    print()
    q_avg = round(sum(r["quality_score"] for r in rows) / len(rows)) if rows else 0
    print(f"Overall: {passed}/{total} passed  |  Avg quality: {q_avg}/100  |  Regressions: {regressions}")
    print()

    # Detail: failed structural checks
    for r in rows:
        fails = [(label, detail) for label, ok, detail in r["structural_checks"] if not ok]
        if fails:
            print(f"  {r['fixture']['name']} — failed structural checks:")
            for label, detail in fails:
                print(f"    ✗ {label}: {detail}")
    print()


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TAclaw test suite")
    parser.add_argument("--smoke",            action="store_true", help="Run simple_webapp only")
    parser.add_argument("--eval-only",        action="store_true", help="Re-eval cached outputs, no new jobs")
    parser.add_argument("--update-baseline",  action="store_true", help="Write current output as baseline")
    parser.add_argument("--api-url",          default=os.getenv("TA_API_URL", "http://localhost:8000"))
    parser.add_argument("--api-key",          default=os.getenv("API_KEY", ""))
    parser.add_argument("--timeout",          type=int, default=300)
    parser.add_argument("--output-dir",       type=Path, default=None)
    args = parser.parse_args()

    if not args.api_key and not args.eval_only:
        print("ERROR: --api-key or $API_KEY required", file=sys.stderr)
        sys.exit(2)

    client = TAClient(args.api_url, args.api_key, args.timeout)

    fixtures = [FIXTURES[0]] if args.smoke else FIXTURES
    rows: list[dict] = []
    any_error = False

    for fixture in fixtures:
        name = fixture["name"]
        print(f"\n{'─'*50}")
        print(f"Fixture: {name}  [{fixture['adapter_hint']}]")

        result: dict | None = None

        if args.eval_only:
            result = _load_cached(fixture, args.output_dir)
            if result is None:
                print(f"  ⚠ no cached result — skipping (run without --eval-only first)")
                continue
            print(f"  → loaded cached result")
        else:
            try:
                result = _run_fixture(fixture, client, args.output_dir, args.timeout)
            except Exception as exc:
                print(f"  ✗ job failed: {exc}")
                any_error = True
                rows.append({
                    "fixture": fixture,
                    "result": {"error": str(exc)},
                    "structural_checks": [("job_submitted", False, str(exc))],
                    "structural_ok": False,
                    "quality_score": 0,
                    "regression": ("error", [], []),
                })
                continue

        structural = _structural(result, fixture)
        structural_ok = all(ok for _, ok, _ in structural)
        if not structural_ok:
            any_error = True

        quality = _quality(result, fixture)
        q_score = _quality_score(quality)

        if args.update_baseline:
            _save_baseline(fixture, result)
            print(f"  → baseline updated")

        regression = _regression(result, fixture)

        rows.append({
            "fixture":           fixture,
            "result":            result,
            "structural_checks": structural,
            "structural_ok":     structural_ok,
            "quality_score":     q_score,
            "quality_detail":    quality,
            "regression":        regression,
        })

        # inline summary
        s_pass = sum(1 for _, ok, _ in structural if ok)
        print(f"  structural {s_pass}/{len(structural)}  quality {q_score}/100  "
              f"regression: {regression[0]}")
        if regression[1]:
            print(f"  ⚠ lost techniques: {regression[1]}")

    print()
    _render_scorecard(rows, args.api_url)

    sys.exit(1 if any_error else 0)


if __name__ == "__main__":
    main()
