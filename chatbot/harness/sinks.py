"""
EventBroker sinks — SiemSink, LangfuseSink, WebhookSink.

Each sink subscribes to a subset of HarnessEvent types defined in its
config block (policies/agent_governance.yaml → event_broker.sinks.<name>.events).

All sinks are non-fatal: exceptions are caught and logged as warnings.
LangfuseSink is a no-op when langfuse package is not installed.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.harness.event_broker import HarnessEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseSink(ABC):
    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._subscribed: List[str] = config.get("events", [])

    def _should_handle(self, event: "HarnessEvent") -> bool:
        if not self._subscribed:
            return True
        return event.event_type in self._subscribed or self._matches_preset(event.event_type)

    def _matches_preset(self, event_type: str) -> bool:
        """Map YAML preset names (stage_trace, critic_trace) to concrete event types."""
        presets = {
            "stage_trace":  {"run_start", "stage_complete", "run_complete"},
            "critic_trace": {"critic_complete", "critic_generation"},
            "governance":   {"governance_complete"},
            "aivss":        {"aivss_complete", "aivss_gate"},
            "mcp_trace":    {"mcp_tool_call"},
            "gate_trace":   {"gate_verdict"},
        }
        for preset, types in presets.items():
            if preset in self._subscribed and event_type in types:
                return True
        return False

    @abstractmethod
    def emit(self, event: "HarnessEvent") -> None: ...

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SiemSink — backward-compatible replacement for harness_siem.SiemEmitter
# ---------------------------------------------------------------------------

_SIEM_SINK_PATH = "logs/siem.jsonl"


class SiemSink(BaseSink):
    """
    Translates "aivss_gate" and "governance_complete" events into the existing
    SiemEvent dict format and appends to siem.jsonl — byte-identical output to
    the direct SiemEmitter call it replaces in OutboundAIVSSGate.

    Other event types are also written as-is when subscribed via events list.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._sink_path = config.get("sink_path", _SIEM_SINK_PATH)
        self._webhook_url: Optional[str] = config.get("webhook_url") or None
        # Also pick up siem_webhook_url from settings as fallback
        if not self._webhook_url:
            try:
                from chatbot.config.settings import get_settings
                self._webhook_url = get_settings().governance.siem_webhook_url or None
            except Exception:
                pass

    def emit(self, event: "HarnessEvent") -> None:
        if not self._should_handle(event):
            return
        try:
            # Translate well-known event types into the canonical SiemEvent format
            if event.event_type == "aivss_gate":
                record = self._translate_aivss_gate(event)
            elif event.event_type == "governance_complete":
                record = self._translate_governance(event)
            else:
                record = event.to_dict()

            path = Path(self._sink_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
            logger.debug(f"SiemSink: emitted {event.event_type} / {event.source}")
        except Exception as exc:
            logger.warning(f"SiemSink emit failed (non-fatal): {exc}")

        if self._webhook_url:
            self._post_webhook(record if "record" in dir() else event.to_dict())

    def _translate_aivss_gate(self, event: "HarnessEvent") -> Dict:
        """Produce a dict matching the legacy SiemEvent schema."""
        p = event.payload
        return {
            "event_type": "threat_assessment_complete",
            "architecture": p.get("architecture", ""),
            "aivss_inbound":  p.get("aivss_inbound", 0.0),
            "aivss_internal": p.get("aivss_internal", 0.0),
            "aivss_outbound": p.get("aivss_outbound", 0.0),
            "overall_severity": p.get("overall_severity", "LOW"),
            "top_threat": p.get("top_threat", {}),
            "governance_dims": p.get("governance_dims", {}),
            "run_id": event.run_id,
            "ts": event.ts,
        }

    def _translate_governance(self, event: "HarnessEvent") -> Dict:
        p = event.payload
        return {
            "event_type": "governance_complete",
            "architecture": p.get("architecture", ""),
            "overall_risk_level": p.get("overall_risk_level", "LOW"),
            "D1": p.get("D1", "LOW"),
            "D2": p.get("D2", "LOW"),
            "D3": p.get("D3", "LOW"),
            "D4": p.get("D4", "LOW"),
            "D5": p.get("D5", "LOW"),
            "blocked_agents": p.get("blocked_agents", []),
            "run_id": event.run_id,
            "ts": event.ts,
        }

    def _post_webhook(self, record: Dict) -> None:
        try:
            import urllib.request
            payload = json.dumps(record).encode()
            req = urllib.request.Request(
                self._webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            logger.warning(f"SiemSink webhook failed (non-fatal): {exc}")


# ---------------------------------------------------------------------------
# LangfuseSink — traces every pipeline run as a Langfuse trace
# ---------------------------------------------------------------------------

class LangfuseSink(BaseSink):
    """
    Maps HarnessEvent types to Langfuse observation hierarchy:
      run_start           → trace (one per run_id)
      stage_complete      → span  (one per stage)
      critic_complete     → generation (captures model + token + cost)
      governance_complete → trace metadata update (D1-D5 dims)
      aivss_complete      → span (inbound/internal/outbound) +
                            Score objects (aivss_inbound / aivss_internal / aivss_outbound)
                            Score objects make AIVSS composites queryable by name in the
                            Langfuse API and consumable by langfuse-to-ocsf via
                            lf.api.scores_v3.get_many_v3(trace_id=...).
      aivss_gate          → span  (outbound gate result)
      run_complete        → trace output update (confidence + errors)

    All Langfuse SDK calls are inside try/except ImportError — this sink
    is a silent no-op when langfuse is not installed.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._trace: Optional[Any] = None
        self._current_trace: Optional[Any] = None  # alias for EventDetectorStage
        self._lf: Optional[Any] = None
        self._routing_mode: str = ""  # preserved across trace.update() calls
        self._init_client(config)

    def _init_client(self, config: Dict[str, Any]) -> None:
        try:
            from langfuse import Langfuse  # type: ignore[import]
            import os
            # LANGFUSE_SKIP=1 lets bench/rerun jobs suppress tracing to protect free-tier quota
            if os.getenv("LANGFUSE_SKIP", "").strip() in ("1", "true", "yes"):
                logger.info("LangfuseSink: LANGFUSE_SKIP set — tracing disabled for this run")
                return
            host = (config.get("host") or
                    os.getenv("LANGFUSE_BASE_URL") or
                    "http://localhost:3000")
            public_key = (config.get("public_key") or
                          os.getenv("LANGFUSE_PUBLIC_KEY") or "")
            secret_key = (config.get("secret_key") or
                          os.getenv("LANGFUSE_SECRET_KEY") or "")
            if not public_key or not secret_key:
                logger.warning("LangfuseSink: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set — sink disabled")
                return
            self._lf = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            logger.info(f"LangfuseSink: connected to {host}")
        except ImportError:
            logger.debug("LangfuseSink: langfuse package not installed — sink is a no-op")
        except Exception as exc:
            logger.warning(f"LangfuseSink: init failed (non-fatal): {exc}")

    def _tid(self, event: "HarnessEvent") -> str:
        """Real Langfuse trace id of the current run (falls back to the run id)."""
        t = getattr(self, "_trace_id", None)
        return t if isinstance(t, str) and t else event.run_id

    def _scope(self, event: "HarnessEvent"):
        """Langfuse trace-level session/user for every span of this event.

        Session = the caller's ``TM-SESSION`` (or caller:date); user = caller_id.
        Remembered from run_start so later events of the same run carry it too.
        """
        import contextlib
        p = event.payload
        if event.event_type in ("run_start", "mcp_tool_call", "gate_verdict"):
            self._session = (p.get("session_id") or "")[:200]
            self._user = (p.get("caller_id") or "")[:200]
        sid, uid = getattr(self, "_session", ""), getattr(self, "_user", "")
        if not (sid or uid):
            return contextlib.nullcontext()
        try:
            from langfuse import propagate_attributes
            return propagate_attributes(session_id=sid or None, user_id=uid or None)
        except Exception:
            return contextlib.nullcontext()

    def emit(self, event: "HarnessEvent") -> None:
        if self._lf is None or not self._should_handle(event):
            return
        with self._scope(event):
            self._emit(event)

    def _emit(self, event: "HarnessEvent") -> None:
        try:
            p = event.payload
            if event.event_type == "run_start":
                _routing_mode = p.get("routing_mode", "")
                self._routing_mode = _routing_mode
                # v4: start_observation with trace_context pins the trace_id so
                # create_score(trace_id=run_id) references the same trace.
                # A true root (no trace_context): pinning only the trace_id gives the
                # span a synthetic parent Langfuse never receives, so the trace has no
                # top-level span and shows no input/output (Langfuse support, 2026-11-21).
                # The run id stays in metadata; scores use the real trace id (_tid).
                self._trace = self._lf.start_observation(
                    name="threat_assessment",
                    as_type="span",
                    input={
                        "architecture": p.get("architecture", ""),
                        "scenario": p.get("scenario", ""),
                        "routing_mode": _routing_mode,
                    },
                    metadata={
                        "run_id": event.run_id,
                        "scenario": p.get("scenario", ""),
                        "architecture": p.get("architecture", ""),
                        "routing_mode": _routing_mode,
                        "caller_id": p.get("caller_id", ""),
                        "caller_asserted": p.get("caller_asserted", False),
                        "source": p.get("source", "unknown"),
                    },
                )
                self._current_trace = self._trace
                self._trace_id = getattr(self._trace, "trace_id", None)

            elif event.event_type == "gate_verdict":
                # A refusal (throttle/block/kill) as its own root span, so it shows in the
                # caller's session next to the runs it stopped. Level marks severity.
                span = self._lf.start_observation(
                    name=f"gate:{p.get('action', '')}",
                    as_type="guardrail",
                    input={"entry_point": p.get("entry_point", ""),
                           "architecture": p.get("architecture", "")},
                    output={"action": p.get("action", ""), "reason": p.get("reason", "")},
                    metadata={k: v for k, v in p.items() if k not in ("reason",)},
                    level="ERROR" if p.get("action") in ("block", "kill") else "WARNING",
                    status_message=p.get("reason", "")[:500],
                )
                span.end()

            elif event.event_type == "mcp_tool_call":
                # One real root span per tool call, with the call's input/output and its
                # measured duration. (Previously: a 0 ms metadata-only span with a
                # synthetic parent, which left Langfuse sessions empty.)
                meta = {k: v for k, v in p.items() if k not in ("input", "output", "duration_s")}
                span = self._lf.start_observation(
                    name=f"mcp:{p.get('tool', event.source)}",
                    as_type="tool",
                    input=p.get("input"),
                    metadata=meta,
                )
                if p.get("output") is not None:
                    span.update(output=p.get("output"))
                dur = p.get("duration_s")
                try:
                    start_ns = span._otel_span.start_time
                    span.end(end_time=start_ns + int(float(dur) * 1e9)) if dur else span.end()
                except Exception:
                    span.end()

            elif event.event_type == "stage_complete" and self._trace:
                child = self._trace.start_observation(
                    name=event.source,
                    as_type="span",
                    metadata=p,
                )
                child.end()

            elif event.event_type == "critic_complete" and self._trace:
                child = self._trace.start_observation(
                    name=event.source,
                    as_type="generation",
                    model=p.get("model", ""),
                    usage_details={"total_tokens": p.get("moe_total_tokens", 0)},
                    cost_details={"total_cost": p.get("moe_total_cost", 0.0)},
                    metadata=p,
                )
                child.end()

            elif event.event_type == "critic_generation" and self._trace:
                child = self._trace.start_observation(
                    name=event.source,
                    as_type="generation",
                    model=p.get("model", ""),
                    usage_details={
                        "input": p.get("prompt_tokens", 0),
                        "output": p.get("completion_tokens", 0),
                        "total": p.get("prompt_tokens", 0) + p.get("completion_tokens", 0),
                    },
                    cost_details={"total_cost": p.get("cost_usd", 0.0)},
                    metadata={
                        "latency_s": p.get("latency_s", 0.0),
                        "validation_status": p.get("validation_status", ""),
                    },
                )
                child.end()

            elif event.event_type == "governance_complete" and self._trace:
                self._trace.update(metadata={
                    "routing_mode":          self._routing_mode,
                    "governance_risk_level": p.get("overall_risk_level", "LOW"),
                    "D1_exploitation":       p.get("D1", "LOW"),
                    "D2_manipulation":       p.get("D2", "LOW"),
                    "D3_leakage":            p.get("D3", "LOW"),
                    "D4_identity":           p.get("D4", "LOW"),
                    "D5_sovereignty":        p.get("D5", "LOW"),
                    "blocked_agents":        p.get("blocked_agents", []),
                })

            elif event.event_type == "aivss_complete" and self._trace:
                # Payload field may be a float (stages.py path) or dict (test/legacy path)
                def _composite(val) -> float:
                    if isinstance(val, dict):
                        return float(val.get("composite", 0.0))
                    return float(val) if val is not None else 0.0

                inbound  = _composite(p.get("inbound",  0.0))
                internal = _composite(p.get("internal", 0.0))
                outbound = _composite(p.get("outbound", 0.0))
                overall_sev = p.get("overall_severity", "LOW")

                child = self._trace.start_observation(
                    name="aivss_scoring",
                    as_type="span",
                    metadata={
                        "inbound":         inbound,
                        "internal":        internal,
                        "outbound":        outbound,
                        "overall_severity": overall_sev,
                    },
                )
                child.end()

                # Attach AIVSS composites as first-class Langfuse Score objects so
                # langfuse-to-ocsf can fetch them via scores_v3.get_many_v3(trace_id=).
                # Score name convention matches what score_to_ocsf() filters on.
                for flow, value in (
                    ("aivss_inbound",  inbound),
                    ("aivss_internal", internal),
                    ("aivss_outbound", outbound),
                ):
                    self._lf.create_score(
                        name=flow,
                        value=value,
                        trace_id=self._tid(event),
                        data_type="NUMERIC",
                        comment=f"AIVSS {flow.replace('aivss_','')} composite — {overall_sev}",
                    )

            elif event.event_type == "sm_verdicts" and self._trace:
                child = self._trace.start_observation(
                    name="sm_verdicts",
                    as_type="span",
                    metadata=p,
                )
                child.end()
                # Per-critic acceptance as individual Score objects so langfuse-to-ocsf
                # can query by name ("sm_verdict_<critic>") for DETECT-QC-004 evaluation.
                for critic, verdict in (p.get("per_critic") or {}).items():
                    self._lf.create_score(
                        name=f"sm_verdict_{critic}",
                        value=1.0 if verdict == "accepted" else 0.0,
                        trace_id=self._tid(event),
                        data_type="NUMERIC",
                        comment=f"SM verdict for {critic}: {verdict}",
                    )
                # Overall acceptance rate as a single score for DETECT-QC-004 threshold query.
                self._lf.create_score(
                    name="sm_acceptance_rate",
                    value=float(p.get("acceptance_rate", 1.0)),
                    trace_id=self._tid(event),
                    data_type="NUMERIC",
                    comment="Fraction of critics accepted by ScrumMaster (1.0 = all accepted)",
                )

            elif event.event_type == "aivss_gate" and self._trace:
                child = self._trace.start_observation(
                    name="outbound_aivss_gate",
                    as_type="span",
                    metadata={
                        "outbound_score": p.get("outbound_score", 0.0),
                        "blocked":        p.get("blocked", False),
                    },
                )
                child.end()

            elif event.event_type == "run_complete" and self._trace:
                _out = {
                    "confidence": p.get("confidence"),
                    "errors":     p.get("errors", []),
                }
                self._trace.set_trace_io(output=_out)
                # Also on the root observation itself: that is what observations.get_many
                # (the only run reader left since trace.get returns 410) returns.
                self._trace.update(output=_out, metadata={
                    "routing_mode":    self._routing_mode,
                    "arch_type":       p.get("arch_type", ""),
                    "aivss_composite": p.get("aivss_composite"),
                    "pipeline_wall_s": p.get("pipeline_wall_s"),
                    "caller_id":       p.get("caller_id", ""),
                    "source":          p.get("source", "unknown"),
                    "usage":           p.get("usage", {}),
                })
                self._trace.end()

        except Exception as exc:
            logger.warning(f"LangfuseSink emit failed (non-fatal): {exc}")

    def flush(self) -> None:
        if self._lf is None:
            return
        try:
            self._lf.flush()
        except Exception as exc:
            logger.warning(f"LangfuseSink flush failed (non-fatal): {exc}")


# ---------------------------------------------------------------------------
# WebhookSink — generic JSON POST
# ---------------------------------------------------------------------------

class WebhookSink(BaseSink):
    """Generic JSON POST to a configurable URL. No new dependencies."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._url: Optional[str] = config.get("url") or None

    def emit(self, event: "HarnessEvent") -> None:
        if not self._url or not self._should_handle(event):
            return
        try:
            import urllib.request
            payload = json.dumps(event.to_dict(), ensure_ascii=False).encode()
            req = urllib.request.Request(
                self._url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
            logger.debug(f"WebhookSink: posted {event.event_type}")
        except Exception as exc:
            logger.warning(f"WebhookSink emit failed (non-fatal): {exc}")
