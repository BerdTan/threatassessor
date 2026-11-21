"""Single spend gate (Entry 264 step 1).

One function decides whether a spend entry point may proceed. It returns a
verdict on the response ladder (allow < steer < throttle < block < kill), not a
boolean, so graduated responses can be added without changing callers.
``allow``, ``throttle`` (per-caller soft limit, see spend_ledger), ``block`` and
``kill`` are produced today; ``steer`` is reserved for a later step.

Principle 5: the decision lives in code. Principle 3: deterministic, no LLM.
Fail closed: a policy file that is missing, unparseable or malformed yields
``block``; it never silently allows spend. The path is resolved from the repo
root, not the working directory.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

ACTIONS = ("allow", "steer", "throttle", "block", "kill")
POLICY_PATH = Path(__file__).resolve().parents[2] / "policies" / "agent_governance.yaml"

# Every REST route that can spend LLM tokens (directly or through a helper).
# (method, path suffix). Tests assert each carries the gate dependency and that
# no route calling an LLM path is missing from this list.
SPEND_ROUTES: tuple[tuple[str, str], ...] = (
    ("POST", "/analyze-stream"),
    ("POST", "/analyze/artifact"),
    ("GET", "/expert-review"),
    ("GET", "/run-critic"),
    ("POST", "/generate-mmd"),
    ("GET", "/llm-check"),
    ("POST", "/jobs/expert-review"),
    ("POST", "/reports/{architecture_name}/rerun-with-sm"),
    ("POST", "/reports/{architecture_name}/sm/{n}/rerun"),
    ("POST", "/reports/{architecture_name}/generate-ciso-brief"),
    ("POST", "/ask"),
    ("POST", "/taclaw/run"),
    ("POST", "/taco/run"),
    ("POST", "/taco/run-sync"),
    ("POST", "/boxing/run"),
    ("POST", "/brain/generate-mmds"),
    ("POST", "/gym/start"),
    ("POST", "/perspective/run/{architecture_name}"),
)


@dataclass(frozen=True)
class Verdict:
    action: str
    reason: str = ""
    entry_point: str = ""
    caller_id: str = ""

    @property
    def allowed(self) -> bool:
        return self.action == "allow"


def _load(policy_path: Any) -> tuple[Optional[dict], str]:
    try:
        import yaml

        path = Path(policy_path)
        if not path.is_file():
            return None, f"policy_unreadable: {path.name} not found"
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            return None, "policy_unreadable: not a mapping"
        return data, ""
    except Exception as exc:  # fail closed on anything
        return None, f"policy_unreadable: {type(exc).__name__}"


def _over_limit(limits: Any, caller_id: str, ledger: Any) -> str:
    """Reason string if the caller is over a configured soft limit, else "".

    ``caller_limits: {window_s, max_requests, max_tokens}``; absent or empty
    means no limit. A malformed limits block raises, and ``check`` turns that
    into ``block`` (fail closed), not into silently unlimited spend.
    """
    if not limits or not caller_id:
        return ""
    if not isinstance(limits, dict):
        raise ValueError("caller_limits not a mapping")
    window = float(limits.get("window_s", 60))
    if window <= 0:
        raise ValueError("window_s must be positive")
    if ledger is None:
        from chatbot.harness.spend_ledger import LEDGER as ledger
    t = ledger.totals(caller_id, window)
    mr, mt = limits.get("max_requests"), limits.get("max_tokens")
    if mr is not None and t["requests"] >= int(mr):
        return f"throttle: {t['requests']} requests in {window:g}s (limit {int(mr)})"
    if mt is not None and t["tokens"] >= int(mt):
        return f"throttle: {t['tokens']} tokens in {window:g}s (limit {int(mt)})"
    return ""


def check(
    entry_point: str,
    architecture: str = "",
    caller_id: str = "",
    policy_path: Any = None,
    ledger: Any = None,
    enforce_limits: bool = True,
) -> Verdict:
    """Return a verdict for one spend attempt. Never raises."""

    def v(action: str, reason: str = "") -> Verdict:
        return Verdict(action, reason, entry_point, caller_id)

    try:
        policy, err = _load(policy_path if policy_path is not None else POLICY_PATH)
        if policy is None:
            return v("block", err)
        bouncer = policy.get("bouncer") or {}
        if not isinstance(bouncer, dict):
            return v("block", "policy_unreadable: bouncer not a mapping")
        ks = bouncer.get("kill_switch", False)
        if ks is True:
            return v("kill", "kill_switch=True in agent_governance.yaml")
        if ks is not False:
            return v("block", "policy_unreadable: kill_switch not a boolean")
        blocked = bouncer.get("blocked_architectures") or []
        if architecture and architecture in blocked:
            return v("block", f"architecture '{architecture}' in blocked_architectures")
        # Limits apply at the front door only: the pipeline stage re-checks policy
        # after the route already counted this request, so it passes False.
        throttled = _over_limit(bouncer.get("caller_limits"), caller_id, ledger) if enforce_limits else ""
        if throttled:
            return v("throttle", throttled)
        return v("allow")
    except Exception as exc:
        return v("block", f"policy_unreadable: {type(exc).__name__}")
