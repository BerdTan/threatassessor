#!/usr/bin/env python3
"""
check-mcp — ThreatAssessor MCP server validation.

Usage:
    python3 check-mcp.py               # static checks only (~3s, no network)
    python3 check-mcp.py --live        # static + live smoke-test (API must be running)
    python3 check-mcp.py --live --url http://localhost:8000
"""

import argparse
import ast
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

GREEN = lambda s: f"\033[32m{s}\033[0m"
AMBER = lambda s: f"\033[33m{s}\033[0m"
RED   = lambda s: f"\033[31m{s}\033[0m"
DIM   = lambda s: f"\033[2m{s}\033[0m"
BOLD  = lambda s: f"\033[1m{s}\033[0m"
CYAN  = lambda s: f"\033[36m{s}\033[0m"

EXPECTED_TOOLS = [
    "analyze_architecture",
    "run_expert_review",
    "get_job_status",
    "get_threat_briefing",
    "get_ciso_brief",
    "get_governance_signals",
    "get_detect_trends",
    "get_tatb_scores",
    "list_architectures",
    "lookup_mitre_technique",
]

MCP_FILES = [
    REPO_ROOT / "chatbot" / "api" / "job_store.py",
    REPO_ROOT / "chatbot" / "api" / "routes" / "jobs.py",
    REPO_ROOT / "chatbot" / "api" / "routes" / "__init__.py",
    REPO_ROOT / "mcp_server" / "__init__.py",
    REPO_ROOT / "mcp_server" / "job_client.py",
    REPO_ROOT / "mcp_server" / "server.py",
]

passed = failed = 0


def ok(label: str, detail: str = "") -> None:
    global passed
    passed += 1
    suffix = f"  {DIM(detail)}" if detail else ""
    print(f"  {GREEN('✓')}  {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    global failed
    failed += 1
    suffix = f"\n      {RED(detail)}" if detail else ""
    print(f"  {RED('✗')}  {label}{suffix}")


def skip(label: str, reason: str = "") -> None:
    suffix = f"  {DIM('— ' + reason)}" if reason else ""
    print(f"  {AMBER('-')}  {label}{suffix}")


# ── Section 1: Syntax ─────────────────────────────────────────────────────────

def check_syntax() -> None:
    print(f"\n{BOLD(CYAN('1. Syntax'))} — {len(MCP_FILES)} files\n")
    for f in MCP_FILES:
        if not f.exists():
            fail(f.name, "file not found")
            continue
        try:
            ast.parse(f.read_text(encoding="utf-8"))
            ok(f.name)
        except SyntaxError as e:
            fail(f.name, str(e))


# ── Section 2: Imports ────────────────────────────────────────────────────────

def check_imports() -> None:
    print(f"\n{BOLD(CYAN('2. Imports'))}\n")

    # mcp SDK
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401
        ok("mcp.server.fastmcp.FastMCP importable")
    except ImportError as e:
        fail("mcp SDK", f"{e} — run: pip install mcp>=1.0.0")

    # job_store
    try:
        from chatbot.api.job_store import get_job_store  # noqa: F401
        ok("chatbot.api.job_store")
    except Exception as e:
        fail("chatbot.api.job_store", str(e))

    # jobs router
    try:
        from chatbot.api.routes.jobs import router  # noqa: F401
        ok("chatbot.api.routes.jobs")
    except Exception as e:
        fail("chatbot.api.routes.jobs", str(e))

    # mcp_server.job_client
    try:
        import mcp_server.job_client  # noqa: F401
        ok("mcp_server.job_client")
    except Exception as e:
        fail("mcp_server.job_client", str(e))

    # mcp_server.server
    try:
        from mcp_server.server import mcp as ta_mcp  # noqa: F401
        ok("mcp_server.server")
    except Exception as e:
        fail("mcp_server.server", str(e))


# ── Section 3: Tool registration ─────────────────────────────────────────────

def check_tools() -> None:
    print(f"\n{BOLD(CYAN('3. Tool registration'))} — expect {len(EXPECTED_TOOLS)} tools\n")
    try:
        from mcp_server.server import mcp as ta_mcp
        registered = {t.name for t in ta_mcp._tool_manager.list_tools()}
    except Exception as e:
        fail("load tools", str(e))
        return

    for name in EXPECTED_TOOLS:
        if name in registered:
            ok(name)
        else:
            fail(name, "not registered")

    extra = registered - set(EXPECTED_TOOLS)
    if extra:
        for name in sorted(extra):
            skip(name, "extra tool (not in expected list)")


# ── Section 4: Job store ──────────────────────────────────────────────────────

def check_job_store() -> None:
    print(f"\n{BOLD(CYAN('4. Job store'))}\n")
    try:
        from chatbot.api.job_store import JobStore, JOB_TTL_SECONDS

        store = JobStore()

        # create
        j = store.create()
        assert j.status == "queued", "initial status must be queued"
        assert j.job_id, "job_id must be set"
        ok("create() → queued job with uuid")

        # update
        store.update(j.job_id, status="running", progress=42, message="test")
        j2 = store.get(j.job_id)
        assert j2.status == "running"
        assert j2.progress == 42
        assert j2.message == "test"
        ok("update() → status/progress/message persisted")

        # get nonexistent
        assert store.get("nonexistent-id") is None
        ok("get() → None for unknown job_id")

        # complete with result
        store.update(j.job_id, status="completed", progress=100,
                     result={"success": True, "confidence": 0.87})
        j3 = store.get(j.job_id)
        assert j3.result["confidence"] == 0.87
        ok("update() → result payload stored")

        # TTL eviction
        store2 = JobStore()
        j_old = store2.create()
        store2._jobs[j_old.job_id].created_at = 0  # force expiry
        store2._evict()
        assert store2.get(j_old.job_id) is None
        ok(f"TTL eviction works (TTL={JOB_TTL_SECONDS}s)")

    except Exception as e:
        fail("job store check", str(e))


# ── Section 5: Jobs router ────────────────────────────────────────────────────

def check_jobs_router() -> None:
    print(f"\n{BOLD(CYAN('5. Jobs router'))}\n")
    try:
        from chatbot.api.routes.jobs import router

        routes = {r.path: list(r.methods) for r in router.routes if hasattr(r, "methods")}

        submit_path = "/api/v1/jobs/expert-review"
        status_path = "/api/v1/jobs/{job_id}/status"

        if submit_path in routes and "POST" in routes[submit_path]:
            ok(f"POST {submit_path}")
        else:
            fail(f"POST {submit_path}", f"found: {routes}")

        if status_path in routes and "GET" in routes[status_path]:
            ok(f"GET  {status_path}")
        else:
            fail(f"GET  {status_path}", f"found: {routes}")

    except Exception as e:
        fail("jobs router", str(e))


# ── Section 6: App wire-up ────────────────────────────────────────────────────

def check_app_wiring() -> None:
    print(f"\n{BOLD(CYAN('6. App wire-up'))}\n")
    try:
        from chatbot.api.app import create_app
        app = create_app()
        paths = {r.path for r in app.routes if hasattr(r, "path")}

        for p in ["/api/v1/jobs/expert-review", "/api/v1/jobs/{job_id}/status"]:
            if p in paths:
                ok(f"{p} registered in FastAPI app")
            else:
                fail(f"{p} not found in app routes")

    except Exception as e:
        fail("app wire-up", str(e))


# ── Section 7: Live smoke-test ────────────────────────────────────────────────

def check_live(base_url: str) -> None:
    print(f"\n{BOLD(CYAN('7. Live smoke-test'))} — {base_url}\n")
    try:
        import requests
    except ImportError:
        skip("live checks", "requests not installed")
        return

    api_key = os.environ.get("TM_API_KEY", os.environ.get("API_KEY", ""))
    headers = {"TM-API-KEY": api_key} if api_key else {}

    def _get(path: str, params: dict = None) -> tuple:
        try:
            r = requests.get(f"{base_url}{path}", headers=headers,
                             params=params, timeout=10)
            return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
        except Exception as e:
            return None, str(e)

    def _post(path: str, body: dict = None) -> tuple:
        try:
            r = requests.post(f"{base_url}{path}", headers={**headers, "Content-Type": "application/json"},
                              json=body or {}, timeout=10)
            return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
        except Exception as e:
            return None, str(e)

    # health
    code, data = _get("/health")
    if code == 200:
        ok("/health → 200")
    else:
        fail("/health", f"status {code}: {data}")
        print(f"  {AMBER('  API may not be running — skipping remaining live checks')}")
        return

    # list_architectures
    code, data = _get("/api/v1/insights/all")
    if code == 200:
        n = len(data) if isinstance(data, list) else len(data.get("architectures", []))
        ok(f"/api/v1/insights/all → {n} architectures")
    elif code == 401:
        fail("/api/v1/insights/all", "401 — set TM_API_KEY env var")
    else:
        fail("/api/v1/insights/all", f"status {code}")

    # tatb corpus
    code, data = _get("/api/v1/tatb-corpus")
    if code in (200, 401):
        ok(f"/api/v1/tatb-corpus → {code}") if code == 200 else fail("/api/v1/tatb-corpus", "401")
    else:
        fail("/api/v1/tatb-corpus", f"status {code}")

    # techniques
    code, data = _get("/api/v1/techniques", {"technique_ids": "T1566"})
    if code in (200, 401):
        ok(f"/api/v1/techniques?technique_ids=T1566 → {code}")
    else:
        fail("/api/v1/techniques", f"status {code}")

    # jobs submit (invalid arch — expect 404, not 500)
    code, data = _post("/api/v1/jobs/expert-review", {"arch_name": "__nonexistent__", "critic_mode": "partial_parallel"})
    if code == 404:
        ok("/api/v1/jobs/expert-review → 404 for unknown arch (correct)")
    elif code == 401:
        fail("/api/v1/jobs/expert-review", "401 — set TM_API_KEY")
    elif code == 422:
        fail("/api/v1/jobs/expert-review", f"422 validation error: {data}")
    else:
        fail("/api/v1/jobs/expert-review", f"unexpected status {code}: {data}")

    # jobs status (invalid id — expect 404)
    code, data = _get("/api/v1/jobs/nonexistent-job-id/status")
    if code == 404:
        ok("/api/v1/jobs/{id}/status → 404 for unknown id (correct)")
    elif code == 401:
        fail("/api/v1/jobs/{id}/status", "401 — set TM_API_KEY")
    else:
        fail("/api/v1/jobs/{id}/status", f"unexpected status {code}: {data}")

    # MCP dry-run over real stdio (validates protocol handshake + tool list)
    print(f"\n  {DIM('MCP stdio dry-run:')}")
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "mcp_server" / "client_sim.py"), "--dry-run"],
            capture_output=True, text=True, cwd=REPO_ROOT,
            timeout=30,
            env={**os.environ, "TM_API_BASE_URL": base_url},
        )
        if "10 tools registered" in result.stdout:
            ok("MCP stdio handshake → 10 tools negotiated")
        elif result.returncode == 0:
            ok("MCP stdio handshake completed")
        else:
            fail("MCP stdio handshake", result.stderr.splitlines()[-1] if result.stderr else "non-zero exit")
    except subprocess.TimeoutExpired:
        fail("MCP stdio handshake", "timed out after 30s")
    except Exception as e:
        fail("MCP stdio handshake", str(e))


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(live: bool) -> int:
    total = passed + failed
    print(f"\n{'─' * 52}")
    status = GREEN("PASS") if failed == 0 else RED("FAIL")
    mode = "static + live" if live else "static"
    print(f"  {BOLD(status)}  {passed}/{total} checks passed  {DIM(f'({mode})')}")
    if failed:
        print(f"  {RED(f'{failed} check(s) failed — fix before wiring Claude Desktop')}")
    print()
    return 1 if failed else 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="check-mcp — ThreatAssessor MCP validation")
    p.add_argument("--live", action="store_true", help="include live API smoke-test")
    p.add_argument("--url", default=os.environ.get("TM_API_BASE_URL", "http://localhost:8000"),
                   help="API base URL for live checks")
    args = p.parse_args()

    print(f"\n{BOLD('ThreatAssessor MCP Server — Validation')}")
    print(DIM(f"  repo: {REPO_ROOT}"))
    if args.live:
        print(DIM(f"  mode: static + live  ({args.url})"))

    check_syntax()
    check_imports()
    check_tools()
    check_job_store()
    check_jobs_router()
    check_app_wiring()
    if args.live:
        check_live(args.url)

    return print_summary(args.live)


if __name__ == "__main__":
    sys.exit(main())
