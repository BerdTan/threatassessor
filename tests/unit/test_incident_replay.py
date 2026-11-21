"""Incident replays (Entry 264 step 5): each scenario asserts the response class
that fires AND that the trace names the caller, so an investigator can rebuild
the story. No LLM, no network.

Scenarios: relay, MCP worker, model probe, force_mode escalation.
"""
import logging

import pytest

from chatbot.harness import spend_gate as sg
from chatbot.harness.spend_ledger import LEDGER


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from chatbot.api.app import create_app
    LEDGER.reset()
    p = tmp_path / "agent_governance.yaml"
    p.write_text("bouncer:\n  caller_limits: {window_s: 60, max_requests: 2}\n")
    monkeypatch.setenv("API_KEY", "k")
    monkeypatch.setattr(sg, "POLICY_PATH", p)
    yield TestClient(create_app())
    LEDGER.reset()


def _hit(c, caller):
    return c.post("/api/v1/boxing/run", json={},
                  headers={"TM-API-KEY": "k", "TM-CALLER": caller})


def test_relay_flood_is_throttled_and_traced(client, caplog):
    """A key resold to a relay: one label floods, gets 429, the trace names it."""
    caplog.set_level(logging.WARNING)
    codes = [_hit(client, "relay-7").status_code for _ in range(4)]
    assert codes[:2] != [429, 429] and codes[2] == 429 and codes[3] == 429
    assert any("throttle" in r.message and "caller=relay-7" in r.message for r in caplog.records)
    assert _hit(client, "honest-user").status_code != 429  # others unaffected


def test_mcp_workers_attributed_and_throttled_independently(client, monkeypatch):
    """MCP-as-worker: the MCP client sends its own label, so two workers do not
    share one anonymous bucket (before this fix every local MCP caller was one id)."""
    from mcp_server import job_client
    out = {}
    for name in ("worker-a", "worker-b"):
        monkeypatch.setenv("TA_MCP_CALLER", name)
        h = job_client._headers()
        assert h["TM-CALLER"] == name
        out[name] = h
    h = {"TM-API-KEY": "k"}
    for _ in range(3):
        r = client.post("/api/v1/boxing/run", json={}, headers={**h, "TM-CALLER": "worker-a"})
    assert r.status_code == 429
    assert client.post("/api/v1/boxing/run", json={}, headers={**h, "TM-CALLER": "worker-b"}).status_code != 429


def test_other_clients_send_a_caller_label(monkeypatch):
    from mcp_connector.client import MCPClient as TAClient
    from taclaw import cli
    monkeypatch.setenv("TA_CALLER", "ci-bot")
    assert TAClient(base_url="http://x", api_key="k")._headers()["TM-CALLER"] == "ci-bot"
    assert cli._headers({"api_key": "k"})["TM-CALLER"] == "ci-bot"


def test_model_probe_is_detected_but_response_is_alert_only():
    """Model probing: repeated queries of one arch raise probe_pattern, DETECT-ABU-001
    fires. The response class is alert-only: honest gap, recorded in the gap map."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "tmeval"))
    import gap_map
    from chatbot.harness.rule_evaluator import RuleEvaluator
    from mcp_server.access_logger import MCPAccessLogger

    log = MCPAccessLogger()
    for _ in range(6):
        log.record_tool_call("analyze_architecture", arch_name="victim", caller_id="prober")
    sig = log.get_signals()
    assert sig["mcp_access"]["probe_pattern"] is True
    ids = [f["unmapped"]["rule_id"] for f in RuleEvaluator().evaluate(
        {"mcp_access": sig["mcp_access"]}, arch_name="victim", run_id="r")]
    assert "DETECT-ABU-001" in ids
    resp = {r["id"]: r["response"] for r in gap_map.build()["rows"]}
    assert resp["DETECT-ABU-001"] == "alert_only"  # flips when a response is added


@pytest.mark.xfail(strict=True, reason="KNOWN GAP (Entry 264): the gate is mode-blind. "
                   "force_mode=full_moe costs several times a plain run but counts as one "
                   "request. Flips to XPASS, and fails, when the gate weights by mode.")
def test_force_mode_escalation_costs_more_than_a_plain_request():
    assert sg.request_weight("analyze-stream", force_mode="full_moe") > \
           sg.request_weight("analyze-stream", force_mode=None)
