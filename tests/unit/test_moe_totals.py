"""MoE token totals (Entry 264, step 12).

Found via a Langfuse screenshot: the `critics` span said moe_total_tokens=0 while the five
critic generations summed to ~68k. The orchestrator writes total_llm_tokens; the stage read
total_tokens, which never existed. Fixing only the key would have double counted, because the
aggregate was also written as a GENERATION with usage.
"""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock

from chatbot.harness.event_broker import HarnessEvent
from chatbot.harness.sinks import LangfuseSink


def _moe():
    crit = lambda t: NS(perf={"llm_tokens": t, "llm_model": "m", "llm_cost_usd": 0.0},
                        validation_status="PASS")
    return NS(
        final_confidence=70.0,
        architect_result=crit(1000), tester_result=crit(2000),
        red_team_result=None, purple_team_result=None, blackhat_result=None,
        pipeline_perf={"total_llm_tokens": 3500, "total_llm_cost_usd": 0.0,
                       "critics": {"architect": {}, "tester": {},
                                   "orchestrator": {"llm_tokens": 500, "llm_model": "m"}}})


def _run_stage(monkeypatch, tmp_path):
    from chatbot.harness import stages
    from chatbot.modules.agents.orchestrators import moe_orchestrator as mo
    monkeypatch.setattr(mo, "run_moe_pipeline", lambda *a, **k: _moe())
    sent = []
    broker = NS(emit=lambda e: sent.append(e))
    ctx = {"enable_moe": True, "report_dir": str(tmp_path), "_event_broker": broker,
           "_run_id": "r"}
    stages.CriticStage()._logic(ctx)
    return sent


def test_critic_complete_reports_the_real_total(monkeypatch, tmp_path):
    sent = _run_stage(monkeypatch, tmp_path)
    cc = next(e for e in sent if e.event_type == "critic_complete")
    assert cc.payload["moe_total_tokens"] == 3500


def test_generations_sum_to_the_total_including_orchestrator(monkeypatch, tmp_path):
    sent = _run_stage(monkeypatch, tmp_path)
    gens = [e for e in sent if e.event_type == "critic_generation"]
    assert {g.source for g in gens} == {"critic_architect", "critic_tester", "critic_orchestrator"}
    assert sum(g.payload["prompt_tokens"] for g in gens) == 3500


def test_aggregate_is_not_a_generation_so_langfuse_does_not_double_count():
    s = LangfuseSink.__new__(LangfuseSink)
    s._lf, s._trace, s._routing_mode = MagicMock(), MagicMock(), ""
    s._should_handle = lambda e: True
    s.emit(HarnessEvent("critic_complete", "critics", "r", "t",
                        {"moe_total_tokens": 3500, "model": "m"}))
    kw = s._trace.start_observation.call_args.kwargs
    assert kw["as_type"] == "span" and "usage_details" not in kw
    assert kw["metadata"]["moe_total_tokens"] == 3500


def test_expert_review_records_orchestrator_tokens_too():
    from chatbot.harness.er_telemetry import record_expert_review
    from chatbot.harness.event_broker import EventBrokerCritic
    from chatbot.harness.spend_ledger import SpendLedger
    real = EventBrokerCritic.__new__(EventBrokerCritic)
    real._usage = {}
    b = NS(emit=real._track_usage, usage=real.usage, flush=lambda: None)
    led = SpendLedger()
    u = record_expert_review("a", _moe(), {"caller_id": "c"}, broker=b, ledger=led)
    assert u["tokens"] == 3500 and led.totals("c", 60)["tokens"] == 3500
