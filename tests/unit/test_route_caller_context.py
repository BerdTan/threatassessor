"""Routes that launch the instrumented harness must hand it the caller (Entry 264 step 11).

Found live (2026-11-21): TAclaw and gym built a PipelineRequest with no caller_id/session_id,
so their runs reached Langfuse with no user or session. Each test drives the real route with
the job runner stubbed and asserts the caller arrives.
"""
import pytest
from fastapi.testclient import TestClient

from chatbot.harness import spend_gate as sg
from chatbot.harness.spend_ledger import LEDGER

H = {"TM-API-KEY": "k", "TM-CALLER": "route-check", "TM-SESSION": "sess-route-check"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    from chatbot.api.app import create_app
    LEDGER.reset()
    pol = tmp_path / "p.yaml"
    pol.write_text("bouncer: {}\n")
    monkeypatch.setenv("API_KEY", "k")
    monkeypatch.setattr(sg, "POLICY_PATH", pol)
    yield TestClient(create_app())
    LEDGER.reset()


def test_taclaw_run_passes_caller_to_the_job(client, monkeypatch, tmp_path):
    from chatbot.api.routes import taclaw
    seen = {}

    async def _stub(**kw):
        seen.update(kw)

    monkeypatch.setattr(taclaw, "_run_taclaw_job", _stub)
    r = client.post("/api/v1/taclaw/run", json={"target": str(tmp_path)}, headers=H)
    assert r.status_code == 200, r.text
    c = seen["caller"]
    assert c["caller_id"] == "route-check" and c["session_id"] == "sess-route-check"
    assert c["source"] == "taclaw"


def test_gym_start_stamps_caller_on_the_session(client, monkeypatch, tmp_path):
    from chatbot.api.routes import gym
    seen = {}

    async def _stub(sess):
        seen["caller"] = sess.caller
        sess.status = "stopped"

    monkeypatch.setattr(gym, "_gym_loop", _stub)
    r = client.post("/api/v1/gym/start", json={"targets": [str(tmp_path)]}, headers=H)
    assert r.status_code == 200, r.text
    assert seen["caller"]["caller_id"] == "route-check"
    assert seen["caller"]["session_id"] == "sess-route-check"


def test_gym_loop_forwards_the_session_caller_to_each_run(monkeypatch, tmp_path):
    """The loop is where the caller used to get dropped: assert it reaches _run_taclaw_job."""
    import asyncio
    from chatbot.api.routes import gym, taclaw
    got = []

    async def _job(**kw):
        got.append(kw.get("caller"))

    monkeypatch.setattr(taclaw, "_run_taclaw_job", _job)
    sess = gym.GymSession(session_id="s", status="running", targets=[str(tmp_path)],
                          target_type="directory", ssp_profile="low_risk_cloud",
                          max_iterations=1, caller={"caller_id": "route-check"})
    asyncio.run(gym._gym_loop(sess))
    assert got == [{"caller_id": "route-check"}]


def test_record_expert_review_emits_events_and_charges_the_ledger():
    from types import SimpleNamespace as NS
    from chatbot.harness.er_telemetry import record_expert_review
    from chatbot.harness.spend_ledger import SpendLedger
    sent = []

    class _B:
        def __init__(self):
            from chatbot.harness.event_broker import EventBrokerCritic
            self._real = EventBrokerCritic.__new__(EventBrokerCritic)
            self._real._usage = {}

        def emit(self, ev):
            self._real._track_usage(ev)
            sent.append(ev)

        def usage(self, rid):
            return self._real.usage(rid)

        def flush(self):
            pass

    led = SpendLedger()
    moe = NS(final_confidence=80.0, pipeline_perf={"model": "m"},
             architect_result=NS(perf={"llm_tokens": 1000, "llm_model": "m"}, validation_status="PASS"),
             tester_result=NS(perf={"llm_tokens": 500}, validation_status="PASS"))
    u = record_expert_review("arch", moe, {"caller_id": "er-check", "session_id": "s", "source": "rest"},
                             "sequential", 3.0, broker=_B(), ledger=led)
    kinds = [e.event_type for e in sent]
    assert kinds == ["run_start", "critic_generation", "critic_generation", "run_complete"]
    assert u["tokens"] == 1500 and sent[0].payload["caller_id"] == "er-check"
    assert led.totals("er-check", 60)["tokens"] == 1500


def test_expert_review_route_charges_the_caller_for_critic_tokens(client, monkeypatch, tmp_path):
    """Drive the real route with the critics stubbed: the caller's ledger must show the tokens."""
    import json
    from types import SimpleNamespace as NS
    from chatbot.api.routes import streaming
    from chatbot.modules.agents.orchestrators import moe_orchestrator as mo
    (tmp_path / "ground_truth.json").write_text(json.dumps({"confidence": 0.9}))
    monkeypatch.setattr(streaming, "_resolve_report_dir", lambda name: tmp_path)
    monkeypatch.setattr(mo, "run_moe_pipeline", lambda *a, **k: NS(
        final_confidence=70.0, pipeline_perf={},
        architect_result=NS(perf={"llm_tokens": 4321}, validation_status="PASS")))
    r = client.get("/api/v1/expert-review", params={"architecture_name": "zz_er_check"}, headers=H)
    assert r.status_code == 200
    assert LEDGER.totals("route-check", 60)["tokens"] == 4321
