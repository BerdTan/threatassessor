#!/usr/bin/env python3
"""
check-sip — TA Security Intelligence Platform test suite.

Validates the full SIP layer: adapter registry, input adapters (TF/CF/OAI/Prose/MMD),
enrichment API, artifact endpoint, TAclaw jobs, brain match, and taclaw CLI.

Usage:
  python3 check-sip.py              # static checks only (no API)
  python3 check-sip.py --live       # static + live REST API checks
  python3 check-sip.py --all        # static + live + CLI smoke tests
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
FIXTURES  = REPO_ROOT / "tests" / "data" / "adapters"
API_BASE  = os.environ.get("TA_API_URL", "http://localhost:8000")
API_KEY   = os.environ.get("TA_API_KEY", "")

# ── test runner ───────────────────────────────────────────────────────────────

_results: List[dict] = []

def _check(name: str, fn: Callable) -> bool:
    try:
        fn()
        _results.append({"name": name, "ok": True})
        print(f"  \033[32m✓\033[0m  {name}")
        return True
    except AssertionError as exc:
        _results.append({"name": name, "ok": False, "detail": str(exc)})
        print(f"  \033[31m✗\033[0m  {name}\n      {exc}")
        return False
    except Exception as exc:
        _results.append({"name": name, "ok": False, "detail": str(exc)})
        print(f"  \033[31m✗\033[0m  {name}\n      {type(exc).__name__}: {exc}")
        return False


def _api(method: str, path: str, **kwargs):
    import urllib.request, urllib.error
    url = f"{API_BASE}{path}"
    data = kwargs.get("json")
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    if data is not None:
        body = json.dumps(data).encode()
    else:
        body = None

    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"HTTP {exc.code}: {exc.read().decode()[:200]}")


# ── Section 1: Static — adapter imports & registry ───────────────────────────

def check_static():
    print("\n\033[1mSection 1 — Adapter Registry (static)\033[0m")

    def _adapters_import():
        import chatbot.adapters  # noqa: F401
        from chatbot.adapters.registry import list_adapters, detect_adapter
        names = list_adapters()
        assert len(names) >= 5, f"Expected ≥5 adapters, got {len(names)}: {names}"

    _check("All 5+ adapters import and self-register", _adapters_import)

    def _mmd_first():
        from chatbot.adapters.registry import _ADAPTERS
        first = type(_ADAPTERS[0]).__name__
        assert first == "MermaidAdapter", f"First adapter should be MermaidAdapter, got {first}"

    _check("MermaidAdapter registered first (extension priority)", _mmd_first)

    def _detect_tf():
        from chatbot.adapters.registry import detect_adapter
        content = (FIXTURES / "sample.tf").read_bytes()
        adapter = detect_adapter("sample.tf", content)
        assert "Terraform" in type(adapter).__name__, f"Got {type(adapter).__name__}"

    _check("detect_adapter() routes .tf to TerraformAdapter", _detect_tf)

    def _detect_cf():
        from chatbot.adapters.registry import detect_adapter
        content = (FIXTURES / "template.yaml").read_bytes()
        adapter = detect_adapter("template.yaml", content)
        assert "CloudFormation" in type(adapter).__name__, f"Got {type(adapter).__name__}"

    _check("detect_adapter() routes CloudFormation YAML to CloudFormationAdapter", _detect_cf)

    def _detect_oa():
        from chatbot.adapters.registry import detect_adapter
        content = (FIXTURES / "openapi.yaml").read_bytes()
        adapter = detect_adapter("openapi.yaml", content)
        assert "OpenAPI" in type(adapter).__name__, f"Got {type(adapter).__name__}"

    _check("detect_adapter() routes OpenAPI YAML to OpenAPIAdapter", _detect_oa)

    def _detect_prose():
        from chatbot.adapters.registry import detect_adapter
        content = (FIXTURES / "prose.txt").read_bytes()
        adapter = detect_adapter("prose.txt", content)
        assert "Prose" in type(adapter).__name__, f"Got {type(adapter).__name__}"

    _check("detect_adapter() routes .txt to ProseAdapter", _detect_prose)

    def _detect_mmd():
        from chatbot.adapters.registry import detect_adapter
        mmd_file = next((REPO_ROOT / "tests" / "data" / "architectures").glob("*.mmd"), None)
        assert mmd_file, "No .mmd fixture found in tests/data/architectures"
        content = mmd_file.read_bytes()
        adapter = detect_adapter(mmd_file.name, content)
        assert "Mermaid" in type(adapter).__name__, f"Got {type(adapter).__name__}"

    _check("detect_adapter() routes .mmd to MermaidAdapter", _detect_mmd)


# ── Section 2: Static — adapter extract + to_mmd ──────────────────────────────

def check_extract():
    print("\n\033[1mSection 2 — Adapter Extract + to_mmd() (static)\033[0m")

    def _extract_tf():
        from chatbot.adapters.terraform import TerraformAdapter
        content = (FIXTURES / "sample.tf").read_text()
        graph = TerraformAdapter().extract(content, "sample.tf")
        assert len(graph.nodes) >= 3, f"Expected ≥3 nodes from sample.tf, got {len(graph.nodes)}"
        mmd = graph.to_mmd()
        assert mmd.startswith("flowchart"), f"to_mmd() should start with 'flowchart', got: {mmd[:40]}"

    _check("TerraformAdapter extracts ≥3 nodes + valid to_mmd()", _extract_tf)

    def _extract_cf():
        from chatbot.adapters.cloudformation import CloudFormationAdapter
        content = (FIXTURES / "template.yaml").read_text()
        graph = CloudFormationAdapter().extract(content, "template.yaml")
        assert len(graph.nodes) >= 3, f"Expected ≥3 nodes from template.yaml, got {len(graph.nodes)}"
        mmd = graph.to_mmd()
        assert "flowchart" in mmd, f"to_mmd() invalid: {mmd[:40]}"

    _check("CloudFormationAdapter extracts ≥3 nodes + valid to_mmd()", _extract_cf)

    def _extract_oa():
        from chatbot.adapters.openapi import OpenAPIAdapter
        content = (FIXTURES / "openapi.yaml").read_text()
        graph = OpenAPIAdapter().extract(content, "openapi.yaml")
        assert len(graph.nodes) >= 2, f"Expected ≥2 nodes from openapi.yaml, got {len(graph.nodes)}"
        mmd = graph.to_mmd()
        assert "flowchart" in mmd

    _check("OpenAPIAdapter extracts ≥2 nodes + valid to_mmd()", _extract_oa)

    def _to_architecture_data():
        from chatbot.adapters.terraform import TerraformAdapter
        content = (FIXTURES / "sample.tf").read_text()
        graph = TerraformAdapter().extract(content, "sample.tf")
        data = graph.to_architecture_data()
        assert "nodes" in data, "to_architecture_data() missing 'nodes'"
        assert "edges" in data, "to_architecture_data() missing 'edges'"

    _check("to_architecture_data() returns nodes + edges dict", _to_architecture_data)


# ── Section 3: Static — schema + mcp_connector models ─────────────────────────

def check_contracts():
    print("\n\033[1mSection 3 — Schema + mcp_connector Models (static)\033[0m")

    def _schema_valid():
        schema_path = REPO_ROOT / "chatbot" / "schemas" / "ta_export_v1.json"
        assert schema_path.exists(), f"Schema not found: {schema_path}"
        schema = json.loads(schema_path.read_text())
        assert "$schema" in schema or "properties" in schema, "Schema missing $schema or properties"

    _check("ta_export_v1.json is valid JSON with properties", _schema_valid)

    def _models_import():
        from mcp_connector.models import (
            TAExportBundle, ComponentContext, GateResult,
            AttackPath, AssessmentSection,
        )
        gate = GateResult(result="PASS", risk_level="MEDIUM", blocking_signals=[])
        assert gate.result == "PASS"
        ctx = ComponentContext(
            component_label="API Gateway", attack_paths=[], techniques=[],
            risk_level="MEDIUM", controls_recommended=[]
        )
        assert ctx.as_markdown()

    _check("mcp_connector typed models import + instantiate correctly", _models_import)

    def _taclaw_pyproject():
        pp = REPO_ROOT / "taclaw_cli" / "pyproject.toml"
        assert pp.exists(), "taclaw_cli/pyproject.toml not found"
        text = pp.read_text()
        assert 'ta = "taclaw_cli.cli:main"' in text
        assert 'taclaw = "taclaw_cli.cli:main"' in text

    _check("taclaw_cli/pyproject.toml has both 'ta' and 'taclaw' entry points", _taclaw_pyproject)

    def _publish_workflows():
        cli_wf  = REPO_ROOT / ".github" / "workflows" / "publish-cli.yml"
        mcp_wf  = REPO_ROOT / ".github" / "workflows" / "publish-mcp.yml"
        assert cli_wf.exists(), "publish-cli.yml missing"
        assert mcp_wf.exists(), "publish-mcp.yml missing"
        assert "taclaw-v*" in cli_wf.read_text()
        assert "mcp-connector-v*" in mcp_wf.read_text()

    _check("PyPI publish workflows exist with correct tag triggers", _publish_workflows)


# ── Section 4: Live — REST API endpoints ──────────────────────────────────────

def check_live():
    print("\n\033[1mSection 4 — Live REST API (requires running API)\033[0m")

    def _sip_health():
        data = _api("GET", "/api/v1/sip/health")
        assert data.get("ok"), f"SIP health not ok: {data}"
        checks = data.get("checks", {})
        assert "adapter_registry" in checks
        assert checks["adapter_registry"]["ok"]

    _check("GET /api/v1/sip/health — all checks pass", _sip_health)

    def _adapters_endpoint():
        data = _api("GET", "/api/v1/adapters")
        assert data.get("total", 0) >= 5, f"Expected ≥5 adapters, got {data}"
        names = [a["name"] for a in data.get("adapters", [])]
        assert "MermaidAdapter" in names, f"MermaidAdapter missing: {names}"

    _check("GET /api/v1/adapters — ≥5 adapters, MermaidAdapter present", _adapters_endpoint)

    def _schema_endpoint():
        import urllib.request
        url = f"{API_BASE}/api/v1/schemas/ta-export"
        req = urllib.request.Request(url, headers={"X-API-Key": API_KEY})
        with urllib.request.urlopen(req, timeout=10) as resp:
            schema = json.loads(resp.read().decode())
        assert "properties" in schema or "$schema" in schema

    _check("GET /api/v1/schemas/ta-export — returns JSON Schema", _schema_endpoint)

    def _taclaw_jobs_list():
        data = _api("GET", "/api/v1/taclaw/jobs")
        assert "jobs" in data, f"Missing 'jobs' key: {data}"
        assert isinstance(data["jobs"], list)

    _check("GET /api/v1/taclaw/jobs — returns jobs list", _taclaw_jobs_list)

    def _enrich_404():
        import urllib.request, urllib.error
        url = f"{API_BASE}/api/v1/enrich"
        body = json.dumps({
            "arch_name": "nonexistent_arch_sip_test_xyz",
            "component": "API Gateway",
            "finding": {"type": "technique", "id": "T1190"},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"X-API-Key": API_KEY, "Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("Expected 404 for nonexistent arch")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404, f"Expected 404, got {exc.code}"

    _check("POST /api/v1/enrich — 404 for nonexistent arch", _enrich_404)

    def _taclaw_run_dircheck():
        import urllib.request, urllib.error
        url = f"{API_BASE}/api/v1/taclaw/run"
        body = json.dumps({
            "target_type": "directory",
            "target": "/nonexistent_sip_test_path",
            "arch_name": "sip_test",
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"X-API-Key": API_KEY, "Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
            raise AssertionError("Expected 400 for nonexistent dir")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400, f"Expected 400, got {exc.code}"

    _check("POST /api/v1/taclaw/run — 400 for nonexistent directory", _taclaw_run_dircheck)

    def _taclaw_run_fixtures():
        """Submit TAclaw job on the fixtures directory — queues without error."""
        data = _api("POST", "/api/v1/taclaw/run", json={
            "target_type": "directory",
            "target": str(FIXTURES),
            "arch_name": "sip_check_fixtures",
        })
        assert "job_id" in data, f"Missing job_id: {data}"
        assert data["status"] == "queued"
        # Poll once to confirm it started
        time.sleep(2)
        job = _api("GET", f"/api/v1/taclaw/jobs/{data['job_id']}")
        assert job["status"] in ("queued", "running", "completed", "failed"), f"Unknown status: {job['status']}"
        print(f"      → job {data['job_id'][:8]}… status={job['status']}, progress={job.get('progress')}%")

    _check("POST /api/v1/taclaw/run on fixtures dir — job queued + polls OK", _taclaw_run_fixtures)

    def _brain_match():
        data = _api("POST", "/api/v1/brain/match", json={
            "topology_signature": "api-gateway → lambda → rds",
            "arch_type": "cloud",
            "component_labels": ["API Gateway", "Lambda", "RDS"],
        })
        assert "matched_patterns" in data or "coverage_gaps" in data, f"Unexpected response: {data}"

    _check("POST /api/v1/brain/match — returns matched_patterns or coverage_gaps", _brain_match)


# ── Section 5: CLI smoke tests ─────────────────────────────────────────────────

def check_cli():
    print("\n\033[1mSection 5 — taclaw CLI Smoke Tests\033[0m")

    def _ta_cli_importable():
        result = subprocess.run(
            [sys.executable, "-c", "from taclaw_cli.cli import main; print('ok')"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, f"Import failed: {result.stderr[:300]}"
        assert "ok" in result.stdout

    _check("taclaw_cli.cli imports without error", _ta_cli_importable)

    def _ta_help():
        result = subprocess.run(
            [sys.executable, "-m", "taclaw_cli.cli", "--help"],
            capture_output=True, text=True, cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        # typer exits 0 for --help
        assert result.returncode == 0, f"--help failed: {result.stderr[:200]}"
        assert "analyze" in result.stdout or "gate" in result.stdout

    _check("ta --help lists analyze and gate subcommands", _ta_help)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    mode_live = "--live" in sys.argv or "--all" in sys.argv
    mode_cli  = "--all" in sys.argv

    # Always activate venv if running from bare Python
    venv_activate = REPO_ROOT / ".venv" / "bin" / "activate"
    if venv_activate.exists() and "VIRTUAL_ENV" not in os.environ:
        print(f"\033[33m⚠ Not in venv — some imports may fail. Activate: source {venv_activate}\033[0m")

    print("\n\033[1m=== TA-SIP Check Suite ===\033[0m")
    print(f"Mode: {'live + CLI' if mode_cli else 'live' if mode_live else 'static'}")
    print(f"API:  {API_BASE}")
    print(f"Repo: {REPO_ROOT}")

    check_static()
    check_extract()
    check_contracts()

    if mode_live:
        check_live()
    if mode_cli:
        check_cli()

    # Summary
    total  = len(_results)
    passed = sum(1 for r in _results if r["ok"])
    failed = total - passed

    print(f"\n{'─'*50}")
    print(f"\033[1mResults: {passed}/{total} passed", end="")
    if failed:
        print(f"  ({failed} failed)\033[0m")
        for r in _results:
            if not r["ok"]:
                print(f"  ✗ {r['name']}: {r.get('detail', '')[:120]}")
    else:
        print("  ✓ all green\033[0m")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
