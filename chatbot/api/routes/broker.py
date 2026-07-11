"""
EventBroker configuration and status API routes.

GET  /api/v1/broker/config   → return current event_broker block from agent_governance.yaml
POST /api/v1/broker/config   → merge payload into event_broker block and save
GET  /api/v1/broker/status   → connectivity test per enabled sink
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/broker", tags=["event-broker"])
logger = logging.getLogger(__name__)

_POLICY_PATH = Path("policies/agent_governance.yaml")


def _load_policy() -> Dict[str, Any]:
    try:
        import yaml  # type: ignore[import]
        with open(_POLICY_PATH, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not load policy: {exc}")


def _save_policy(policy: Dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore[import]
        with open(_POLICY_PATH, "w", encoding="utf-8") as fh:
            yaml.dump(policy, fh, default_flow_style=False, allow_unicode=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save policy: {exc}")


@router.get("/config")
async def get_broker_config() -> Dict[str, Any]:
    """Return the current event_broker block from policies/agent_governance.yaml."""
    policy = _load_policy()
    return policy.get("event_broker", {})


@router.post("/config")
async def save_broker_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge payload into the event_broker block and save to policies/agent_governance.yaml.
    Only keys present in payload are updated — other policy sections untouched.
    """
    policy = _load_policy()
    eb = policy.get("event_broker", {})
    # Deep-merge sinks
    if "sinks" in payload:
        eb.setdefault("sinks", {})
        for sink_name, sink_cfg in payload["sinks"].items():
            eb["sinks"].setdefault(sink_name, {})
            eb["sinks"][sink_name].update(sink_cfg)
    # Top-level keys (verbosity_presets etc.)
    for k, v in payload.items():
        if k != "sinks":
            eb[k] = v
    policy["event_broker"] = eb
    _save_policy(policy)
    return eb


@router.get("/status")
async def broker_status() -> Dict[str, Any]:
    """
    Test connectivity for each enabled sink.
    Returns {siem: "ok"|"error", langfuse: "ok"|"error"|"not_configured", webhook: ...}
    """
    policy = _load_policy()
    sinks_cfg = policy.get("event_broker", {}).get("sinks", {})
    results: Dict[str, Any] = {}

    # SIEM sink — check log path is writable
    siem_cfg = sinks_cfg.get("siem", {})
    if siem_cfg.get("enabled", False):
        try:
            log_path = Path("logs/siem.jsonl")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.touch(exist_ok=True)
            results["siem"] = "ok"
        except Exception as exc:
            results["siem"] = f"error: {exc}"
    else:
        results["siem"] = "not_configured"

    # Langfuse sink — GET /api/health
    langfuse_cfg = sinks_cfg.get("langfuse", {})
    if langfuse_cfg.get("enabled", False):
        import urllib.request
        host = langfuse_cfg.get("host", "http://localhost:3000").rstrip("/")
        try:
            with urllib.request.urlopen(f"{host}/api/health", timeout=4) as resp:
                body = json.loads(resp.read().decode())
                results["langfuse"] = "ok" if body.get("status") == "ok" else f"warn: {body}"
        except Exception as exc:
            results["langfuse"] = f"error: {exc}"
    else:
        results["langfuse"] = "not_configured"

    # Webhook sink — HEAD request
    webhook_cfg = sinks_cfg.get("webhook", {})
    if webhook_cfg.get("enabled", False):
        url = webhook_cfg.get("url", "")
        if url:
            import urllib.request
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=4):
                    pass
                results["webhook"] = "ok"
            except Exception as exc:
                results["webhook"] = f"error: {exc}"
        else:
            results["webhook"] = "error: url not set"
    else:
        results["webhook"] = "not_configured"

    return results
