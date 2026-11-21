"""Telemetry for the standalone expert-review route (Entry 264, step 11).

``/expert-review`` runs the critics through ``run_moe_pipeline`` directly, bypassing the
harness, so its LLM spend reached neither Langfuse nor the per-caller ledger (found live,
2026-11-21). This records one run for it using the same event types the harness emits, so
the readers and the token report need no special case. Best-effort: never raises.
"""
from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any, Optional

_CRITICS = ("architect", "tester", "red_team", "purple_team", "blackhat")


def record_expert_review(
    architecture: str,
    moe: Any,
    caller: Optional[dict] = None,
    critic_mode: str = "",
    wall_s: float = 0.0,
    broker: Any = None,
    ledger: Any = None,
) -> dict:
    """Emit run_start / critic_generation / run_complete for a finished expert review.

    Returns the usage totals recorded (also fed to the caller's ledger).
    """
    usage: dict = {"tokens": 0, "cost_usd": 0.0, "llm_calls": 0}
    try:
        from chatbot.harness.event_broker import EventBrokerCritic, HarnessEvent

        caller = caller or {}
        broker = broker or EventBrokerCritic()
        run_id = uuid.uuid4().hex
        ident = {"caller_id": caller.get("caller_id", ""),
                 "caller_asserted": caller.get("caller_asserted", False),
                 "session_id": caller.get("session_id", ""),
                 "source": caller.get("source", "rest")}

        def _ev(kind: str, source: str, payload: dict) -> None:
            broker.emit(HarnessEvent(
                event_type=kind, source=source, run_id=run_id,
                ts=_dt.datetime.now(_dt.timezone.utc).isoformat(), payload=payload))

        _ev("run_start", "expert-review", {
            "architecture": architecture, "scenario": "expert_review",
            "routing_mode": "full_moe", "critic_mode": critic_mode, **ident})
        perf = getattr(moe, "pipeline_perf", None) or {}
        for key in _CRITICS:
            vr = getattr(moe, f"{key}_result", None)
            if vr is None:
                continue
            cp = getattr(vr, "perf", None) or {}
            _ev("critic_generation", f"critic_{key}", {
                "model": cp.get("llm_model", perf.get("model", "")),
                "prompt_tokens": cp.get("llm_tokens", 0), "completion_tokens": 0,
                "cost_usd": cp.get("llm_cost_usd", 0.0),
                "latency_s": cp.get("llm_latency_s", 0.0),
                "validation_status": getattr(vr, "validation_status", "")})
        usage = broker.usage(run_id)
        _ev("run_complete", "expert-review", {
            "confidence": getattr(moe, "final_confidence", None), "errors": [],
            "pipeline_wall_s": round(float(wall_s or 0.0), 2), "usage": usage, **ident})
        broker.flush()
        if ledger is None:
            from chatbot.harness.spend_ledger import LEDGER as ledger
        ledger.record(ident["caller_id"], tokens=int(usage.get("tokens", 0)))
    except Exception:
        pass
    return usage
