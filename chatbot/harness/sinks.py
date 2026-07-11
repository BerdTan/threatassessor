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
            "critic_trace": {"critic_complete"},
            "governance":   {"governance_complete"},
            "aivss":        {"aivss_complete", "aivss_gate"},
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
      aivss_complete      → span  (inbound/internal/outbound scores)
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
        self._init_client(config)

    def _init_client(self, config: Dict[str, Any]) -> None:
        try:
            from langfuse import Langfuse  # type: ignore[import]
            import os
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

    def emit(self, event: "HarnessEvent") -> None:
        if self._lf is None or not self._should_handle(event):
            return
        try:
            p = event.payload
            if event.event_type == "run_start":
                self._trace = self._lf.trace(
                    id=event.run_id,
                    name="threat_assessment",
                    metadata={
                        "scenario": p.get("scenario", ""),
                        "architecture": p.get("architecture", ""),
                    },
                )
                self._current_trace = self._trace

            elif event.event_type == "stage_complete" and self._trace:
                self._trace.span(
                    name=event.source,
                    metadata=p,
                    end_time=event.ts,
                )

            elif event.event_type == "critic_complete" and self._trace:
                self._trace.generation(
                    name=event.source,
                    model=p.get("model", ""),
                    usage_details={"total_tokens": p.get("moe_total_tokens", 0)},
                    cost_details={"total_cost": p.get("moe_total_cost", 0.0)},
                    metadata=p,
                )

            elif event.event_type == "governance_complete" and self._trace:
                self._trace.update(metadata={
                    "governance_risk_level": p.get("overall_risk_level", "LOW"),
                    "D1_exploitation":  p.get("D1", "LOW"),
                    "D2_manipulation":  p.get("D2", "LOW"),
                    "D3_leakage":       p.get("D3", "LOW"),
                    "D4_identity":      p.get("D4", "LOW"),
                    "D5_sovereignty":   p.get("D5", "LOW"),
                    "blocked_agents":   p.get("blocked_agents", []),
                })

            elif event.event_type == "aivss_complete" and self._trace:
                self._trace.span(
                    name="aivss_scoring",
                    metadata={
                        "inbound":  p.get("inbound", 0.0),
                        "internal": p.get("internal", 0.0),
                        "outbound": p.get("outbound", 0.0),
                        "overall_severity": p.get("overall_severity", "LOW"),
                    },
                    end_time=event.ts,
                )

            elif event.event_type == "aivss_gate" and self._trace:
                self._trace.span(
                    name="outbound_aivss_gate",
                    metadata={
                        "outbound_score": p.get("outbound_score", 0.0),
                        "blocked": p.get("blocked", False),
                    },
                    end_time=event.ts,
                )

            elif event.event_type == "run_complete" and self._trace:
                self._trace.update(output={
                    "confidence": p.get("confidence"),
                    "errors": p.get("errors", []),
                })

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
