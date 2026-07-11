"""
EventBroker — pub/sub dispatcher for ThreatAssessor pipeline events.

Instantiated once per run by ThreatAssessorHarness.run() and stored in
ctx["_event_broker"]. Stages call _emit() (stages.py helper) which routes
to all enabled sinks without any stage needing to know which sinks exist.

Registered in CriticRegistry as governance_tier="optional" so it never
activates as a MoE critic, but tooling (e.g. /aivss-gate skill) can
discover it by name.
"""
from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
EVENT_TYPES = frozenset({
    "run_start",
    "stage_complete",
    "critic_complete",
    "governance_complete",
    "aivss_complete",
    "aivss_gate",
    "run_complete",
})


@dataclass
class HarnessEvent:
    event_type: str          # one of EVENT_TYPES
    source: str              # stage name or critic role
    run_id: str
    ts: str                  # ISO 8601 — caller-supplied (no datetime.now() here)
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# EventBrokerCritic
# ---------------------------------------------------------------------------

class EventBrokerCritic:
    """
    Central event dispatcher for the ThreatAssessor pipeline.

    Usage (controller.py):
        broker = EventBrokerCritic()
        ctx["_event_broker"] = broker
        broker.emit(HarnessEvent("run_start", ...))
        # ... pipeline runs ...
        broker.flush()   # in finally block

    Never called by MoEOrchestrator — governance_tier="optional" excludes it.
    """

    def __init__(self, policy_path: str = "policies/agent_governance.yaml"):
        self._sinks: List[Any] = []           # BaseSink instances
        self._current_trace: Optional[Any] = None  # Langfuse trace handle (set by LangfuseSink)
        self._enabled = False
        self._load_sinks(policy_path)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def emit(self, event: HarnessEvent) -> None:
        """Dispatch event to all enabled sinks that subscribe to this event type."""
        if not self._enabled or not self._sinks:
            return
        for sink in self._sinks:
            try:
                sink.emit(event)
            except Exception as exc:
                logger.warning(f"EventBroker sink {type(sink).__name__} failed (non-fatal): {exc}")

    def flush(self) -> None:
        """Flush all sinks (LangfuseSink flushes buffered spans; others are no-ops)."""
        for sink in self._sinks:
            try:
                sink.flush()
            except Exception as exc:
                logger.warning(f"EventBroker flush {type(sink).__name__} failed (non-fatal): {exc}")

    def critique(self, *args, **kwargs):
        """Registry-compat stub — EventBroker is not a scoring critic."""
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_sinks(self, policy_path: str) -> None:
        try:
            import yaml  # type: ignore[import]
        except ImportError:
            logger.debug("PyYAML not available — EventBroker disabled")
            return

        try:
            path = Path(policy_path)
            if not path.exists():
                return
            with open(path, encoding="utf-8") as fh:
                policy = yaml.safe_load(fh)
        except Exception as exc:
            logger.warning(f"EventBroker: could not load policy {policy_path}: {exc}")
            return

        eb_cfg = policy.get("event_broker", {})
        if not eb_cfg:
            return

        # Check settings layer enabled flag (overrides YAML when explicitly False)
        try:
            from chatbot.config.settings import get_settings
            if not get_settings().event_broker.enabled:
                logger.debug("EventBroker disabled via settings.event_broker.enabled=false")
                return
        except Exception:
            pass

        sinks_cfg = eb_cfg.get("sinks", {})

        from chatbot.harness.sinks import SiemSink, LangfuseSink, WebhookSink

        if sinks_cfg.get("siem", {}).get("enabled", False):
            sink = SiemSink(sinks_cfg["siem"])
            self._sinks.append(sink)
            logger.info("EventBroker: SiemSink enabled")

        if sinks_cfg.get("langfuse", {}).get("enabled", False):
            sink = LangfuseSink(sinks_cfg["langfuse"])
            self._sinks.append(sink)
            # Expose trace handle so EventDetectorStage can wrap generation spans
            self._current_trace = getattr(sink, "_current_trace", None)
            logger.info("EventBroker: LangfuseSink enabled")

        if sinks_cfg.get("webhook", {}).get("enabled", False):
            sink = WebhookSink(sinks_cfg["webhook"])
            self._sinks.append(sink)
            logger.info("EventBroker: WebhookSink enabled")

        self._enabled = bool(self._sinks)


# ---------------------------------------------------------------------------
# Self-registration
# ---------------------------------------------------------------------------
try:
    from chatbot.harness.registry import _DEFAULT_REGISTRY, CriticDescriptor
    _DEFAULT_REGISTRY.register(CriticDescriptor(
        name="event_broker",
        cls=EventBrokerCritic,
        governance_tier="optional",
        model_key="event_broker",
    ))
except Exception:
    pass
