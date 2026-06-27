"""Lightweight SIEM emitter — appends CEF-compatible JSONL to logs/siem.jsonl."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_SINK = "logs/siem.jsonl"


@dataclass
class SiemEvent:
    event_type: str        # "threat_assessment_complete" | "governance_block"
    architecture: str
    aivss_inbound: float
    aivss_internal: float
    aivss_outbound: float
    overall_severity: str
    top_threat: dict       # {technique_id, technique_name, aivss_score, severity}
    governance_dims: dict  # {D1..D5: severity}
    run_id: str
    ts: str                # ISO timestamp (caller-supplied — no datetime.now() here)


class SiemEmitter:
    """Append a SiemEvent as a JSONL line to sink_path (and optionally POST to a webhook)."""

    def __init__(self, sink_path: str = _DEFAULT_SINK, webhook_url: Optional[str] = None):
        self.sink_path = sink_path
        self.webhook_url = webhook_url

    def emit(self, event: SiemEvent) -> None:
        try:
            path = Path(self.sink_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(asdict(event), ensure_ascii=False) + "\n"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
            logger.debug(f"SIEM event emitted: {event.event_type} / {event.architecture}")
        except Exception as exc:
            logger.warning(f"SIEM emit failed (non-fatal): {exc}")

        if self.webhook_url:
            self._post_webhook(event)

    def _post_webhook(self, event: SiemEvent) -> None:
        try:
            import urllib.request
            payload = json.dumps(asdict(event)).encode()
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as exc:
            logger.warning(f"SIEM webhook failed (non-fatal): {exc}")
