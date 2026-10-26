"""
ManagedAgent — base class for the TA managed agent fleet.

A ManagedAgent wraps an LLM tool-call loop:
  build_task(context) → task prompt
  should_run(context) → pre-flight gate (Jev optional)
  run(context)        → tool loop → ManagedAgentResult

Adding an agent to the fleet = subclass + one line in registry._auto_register().

Security model (OpenShell-inspired, software-only):
  - allowed_tools / allowed_endpoints: per-agent capability declaration (Policy)
  - AgentSupervisor: intercepts every tool call and enforces allowed_tools (Supervisor)
  - confirm_isolation(): fail-closed pre-flight before the loop starts (Gateway check)
  - RunCredentials: run-scoped credential handles; raw values never reach agent context
  - Circuit breaker: >=3 supervisor violations → FROZEN terminal state (freeze-on-drop)
"""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

MAX_ITERATIONS_DEFAULT = 8
MAX_AGENT_TOKENS_DEFAULT = 50_000   # hard budget per run (~$0.10 at typical rates)
_TOOL_RESULT_MAX_CHARS = 2048       # cap per tool response to limit corpus injection blast radius
_SUPERVISOR_VIOLATION_THRESHOLD = 3  # violations before circuit breaker freezes the agent

_GOVERNANCE_PATH = Path(__file__).resolve().parents[3] / "policies" / "agent_governance.yaml"

# Lightweight injection guard — covers the most dangerous prompt-injection patterns.
# Intentionally a subset of governance._INJECTION_PATTERNS (no need for full harness here).
_CONTEXT_INJECT_RE = re.compile(
    r"ignore\s+(?:previous|all|above|prior)(?:\s+\w+){0,3}\s+(?:instructions?|prompts?|context)"
    r"|new\s+system\s+prompt"
    r"|override\s+system"
    r"|disregard\s+(?:system|all)\s+(?:instructions?|prompts?)"
    r"|<\s*script"
    r"|</?\s*system\s*>"
    r"|<\|im_end\|>"
    r"|</s>"
    r"|\[INST\]"
    r"|<<SYS>>",
    re.IGNORECASE,
)

# Slightly tighter output guard — prevents the agent from being used as an amplifier
# to embed instruction-override content inside remediation_steps or similar fields.
_OUTPUT_INJECT_RE = re.compile(
    r"ignore\s+(?:previous|all|above|prior).*?(?:instructions?|prompts?|context)"
    r"|new\s+system\s+prompt"
    r"|override\s+system",
    re.IGNORECASE,
)


def _sanitize_str(value: str) -> str:
    """Redact if injection pattern found; otherwise HTML-escape the value."""
    if _CONTEXT_INJECT_RE.search(value):
        logger.warning("ManagedAgent context sanitiser: injection pattern detected, value redacted")
        return "[REDACTED: injection pattern detected]"
    return html.escape(value, quote=True)


def _sanitize_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of context with all string (and list-of-string) values sanitized."""
    clean: Dict[str, Any] = {}
    for k, v in context.items():
        if isinstance(v, str):
            clean[k] = _sanitize_str(v)
        elif isinstance(v, list):
            clean[k] = [_sanitize_str(i) if isinstance(i, str) else i for i in v]
        else:
            clean[k] = v
    return clean


# ── primitives ────────────────────────────────────────────────────────────────

@dataclass
class RunCredentials:
    """
    Run-scoped credential handles. Agents receive this object, not raw key values.
    The supervisor resolves handles to real values internally; the agent context never
    holds a raw secret. Expires (cleared) when the run ends.
    """
    run_id: str
    _store: Dict[str, str] = field(default_factory=dict, repr=False)
    _active: bool = field(default=True, repr=False)

    def provision(self, handle: str, value: str) -> None:
        """Called by AgentPrepStage (or test setup) to bind a handle to a real value."""
        self._store[handle] = value

    def resolve(self, handle: str) -> str:
        """Resolve a handle to its real value. Raises if expired or unknown."""
        if not self._active:
            raise RuntimeError(f"RunCredentials for run {self.run_id} have expired")
        if handle not in self._store:
            raise KeyError(f"Unknown credential handle: {handle!r}")
        return self._store[handle]

    def expire(self) -> None:
        self._active = False
        self._store.clear()


@dataclass
class AgentTool:
    name: str
    description: str
    input_schema: Dict[str, Any]   # JSON Schema for the tool's input
    handler: Callable[[Dict[str, Any]], str]  # sync; returns JSON string or plain text

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass
class ManagedAgentResult:
    agent_id: str
    success: bool
    output: Dict[str, Any]         # structured output; schema defined per agent
    tool_calls_made: int = 0
    tokens_used: int = 0
    jev_gate_passed: Optional[bool] = None   # None = Jev not consulted
    skip_reason: str = ""          # set when success=False and agent was skipped
    supervisor_violations: int = 0  # tool calls blocked by supervisor allowlist check
    frozen: bool = False            # True when circuit breaker tripped (>=3 violations)


# ── base class ────────────────────────────────────────────────────────────────

class ManagedAgent(ABC):
    """
    Base class for all TA managed agents.

    Subclasses must implement:
      agent_id          (class attribute)
      description       (class attribute)
      system_prompt     (class attribute)
      allowed_tools     (class attribute — list of tool names this agent may call)
      allowed_endpoints (class attribute — URL prefixes this agent may reach)
      tools             (list[AgentTool], populated in __init__)
      build_task()
      should_run()      (optional override; base always returns True)

    Enforcement: allowed_tools is enforced by the supervisor in _execute_tool().
    allowed_endpoints is declared for the prover (registry) and future HTTP relay enforcement.
    Empty lists disable enforcement for that dimension but trigger a prover warning at registration.
    """

    agent_id: str = ""
    description: str = ""
    system_prompt: str = ""
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    max_total_tokens: int = MAX_AGENT_TOKENS_DEFAULT

    # Capability declaration — required by the supervisor model.
    # Non-empty → strictly enforced. Empty → no enforcement (prover warns at registration).
    allowed_tools: List[str] = []
    allowed_endpoints: List[str] = []

    def __init__(self) -> None:
        self.tools: List[AgentTool] = []
        self._tool_map: Dict[str, Callable[[Dict[str, Any]], str]] = {}
        self._supervisor_violations: int = 0
        self._frozen: bool = False
        self._run_credentials: Optional[RunCredentials] = None
        self._register_tools()
        logger.info("ManagedAgent[%s] initialised with %d tools", self.agent_id, len(self.tools))

    @abstractmethod
    def _register_tools(self) -> None:
        """Populate self.tools and keep self._tool_map in sync."""

    def _add_tool(self, tool: AgentTool) -> None:
        self.tools.append(tool)
        self._tool_map[tool.name] = tool.handler

    @abstractmethod
    def build_task(self, context: Dict[str, Any]) -> str:
        """Return the initial user-turn task prompt from context."""

    def should_run(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Pre-flight gate.  Override to add Jev noul check or fast filters.
        Returns (should_run, reason_string).
        """
        return True, "ok"

    def confirm_isolation(self) -> Tuple[bool, str]:
        """
        Fail-closed pre-flight: verify the isolation boundary before the loop starts.
        Mirrors the OpenShell supervisor confirming controls before the workload launches.
        Returns (ok, reason). A False result blocks run() from starting.
        """
        # Governance policy must be loadable — if the file is missing or corrupt the
        # agent has no policy basis to run against.
        if not _GOVERNANCE_PATH.exists():
            return False, f"governance policy not found: {_GOVERNANCE_PATH}"
        try:
            import yaml
            yaml.safe_load(_GOVERNANCE_PATH.read_text())
        except Exception as exc:
            return False, f"governance policy unreadable: {exc}"

        # Capability declarations must be non-empty (prover already warned; here we block).
        if not self.allowed_tools:
            logger.warning(
                "ManagedAgent[%s] confirm_isolation: allowed_tools not declared — "
                "supervisor enforcement disabled for this agent",
                self.agent_id,
            )
            # Warn but do not block: allows agents that predate the contract to run.
            # The prover in registry.register() flags this at startup.

        return True, "ok"

    # ── tool loop ─────────────────────────────────────────────────────────────

    def run(self, context: Dict[str, Any]) -> ManagedAgentResult:
        """Execute the managed tool loop and return a structured result."""
        # Reset per-run supervisor state.
        self._supervisor_violations = 0
        self._frozen = False

        # Sanitize context values before they reach build_task() or any tool.
        context = _sanitize_context(context)

        ok, reason = self.should_run(context)
        if not ok:
            logger.info("ManagedAgent[%s] skipped: %s", self.agent_id, reason)
            return ManagedAgentResult(
                agent_id=self.agent_id,
                success=False,
                output={},
                skip_reason=reason,
                jev_gate_passed=(False if "jev" in reason else None),
            )

        jev_passed = True if "jev_gate" not in reason else None

        # Fail-closed pre-flight: confirm isolation boundary before starting the loop.
        isolation_ok, isolation_reason = self.confirm_isolation()
        if not isolation_ok:
            logger.error("ManagedAgent[%s] confirm_isolation failed: %s", self.agent_id, isolation_reason)
            return ManagedAgentResult(
                agent_id=self.agent_id,
                success=False,
                output={"error": f"isolation check failed: {isolation_reason}"},
                skip_reason=f"confirm_isolation:{isolation_reason}",
                jev_gate_passed=jev_passed,
            )

        # Provision run-scoped credentials (empty by default; AgentPrepStage can populate).
        run_id = str(uuid.uuid4())
        self._run_credentials = RunCredentials(run_id=run_id)
        logger.debug("ManagedAgent[%s] run_id=%s credentials provisioned", self.agent_id, run_id)

        from agentic.llm_client import LLMClient
        client = LLMClient()

        tools_schema = [t.to_openai_schema() for t in self.tools]
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": self.build_task(context)},
        ]

        total_tokens = 0
        tool_calls_made = 0

        try:
            for iteration in range(self.max_iterations):
                # Circuit breaker: freeze if supervisor violation threshold reached.
                if self._frozen:
                    logger.error(
                        "ManagedAgent[%s] FROZEN after %d supervisor violations — halting run",
                        self.agent_id, self._supervisor_violations,
                    )
                    return ManagedAgentResult(
                        agent_id=self.agent_id,
                        success=False,
                        output={"error": "agent frozen: supervisor violation threshold exceeded"},
                        tool_calls_made=tool_calls_made,
                        tokens_used=total_tokens,
                        jev_gate_passed=jev_passed,
                        supervisor_violations=self._supervisor_violations,
                        frozen=True,
                    )

                if total_tokens >= self.max_total_tokens:
                    logger.warning(
                        "ManagedAgent[%s] token budget exhausted (%d >= %d) at iteration %d",
                        self.agent_id, total_tokens, self.max_total_tokens, iteration,
                    )
                    break
                resp = client.chat(messages=messages, tools=tools_schema)
                total_tokens += resp.tokens_used

                if resp.stop_reason == "error":
                    logger.error("ManagedAgent[%s] LLM error at iteration %d", self.agent_id, iteration)
                    return ManagedAgentResult(
                        agent_id=self.agent_id,
                        success=False,
                        output={"error": "LLM call failed"},
                        tool_calls_made=tool_calls_made,
                        tokens_used=total_tokens,
                        jev_gate_passed=jev_passed,
                        supervisor_violations=self._supervisor_violations,
                    )

                if resp.stop_reason == "end_turn":
                    # Final answer — parse structured output, then scan for injection in output fields.
                    output = self._scan_output(self._parse_output(resp.content or ""))
                    return ManagedAgentResult(
                        agent_id=self.agent_id,
                        success=True,
                        output=output,
                        tool_calls_made=tool_calls_made,
                        tokens_used=total_tokens,
                        jev_gate_passed=jev_passed,
                        supervisor_violations=self._supervisor_violations,
                    )

                if resp.stop_reason == "tool_use" and resp.tool_calls:
                    # Build assistant message with tool_calls block
                    assistant_msg: Dict[str, Any] = {
                        "role": "assistant",
                        "content": resp.content or "",
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {"name": tc["name"], "arguments": json.dumps(tc["input"])},
                            }
                            for tc in resp.tool_calls
                        ],
                    }
                    messages.append(assistant_msg)

                    # Execute each tool through the supervisor relay.
                    for tc in resp.tool_calls:
                        tool_calls_made += 1
                        result_str = self._execute_tool(tc["name"], tc["input"])
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_str,
                        })

                    continue  # next iteration

                # Unexpected stop reason
                logger.warning("ManagedAgent[%s] unexpected stop_reason=%s", self.agent_id, resp.stop_reason)
                break

        finally:
            # Always expire credentials when the run ends, regardless of outcome.
            if self._run_credentials is not None:
                self._run_credentials.expire()
                self._run_credentials = None

        logger.warning("ManagedAgent[%s] exhausted max_iterations=%d", self.agent_id, self.max_iterations)
        return ManagedAgentResult(
            agent_id=self.agent_id,
            success=False,
            output={"error": f"max_iterations ({self.max_iterations}) reached"},
            tool_calls_made=tool_calls_made,
            tokens_used=total_tokens,
            jev_gate_passed=jev_passed,
            supervisor_violations=self._supervisor_violations,
        )

    def _execute_tool(self, name: str, input_dict: Dict[str, Any]) -> str:
        # ── Supervisor allowlist check ──────────────────────────────────────────
        # If allowed_tools is declared (non-empty), the tool name must be in it.
        # An unlisted call is a supervisor violation; three violations freeze the agent.
        if self.allowed_tools and name not in self.allowed_tools:
            self._supervisor_violations += 1
            logger.error(
                "ManagedAgent[%s] SUPERVISOR VIOLATION #%d: tool %r not in allowed_tools %s",
                self.agent_id, self._supervisor_violations, name, self.allowed_tools,
            )
            if self._supervisor_violations >= _SUPERVISOR_VIOLATION_THRESHOLD:
                self._frozen = True
                logger.error(
                    "ManagedAgent[%s] circuit breaker OPEN — agent frozen after %d violations",
                    self.agent_id, self._supervisor_violations,
                )
            return json.dumps({
                "error": f"supervisor: tool {name!r} not in allowed_tools",
                "violations": self._supervisor_violations,
            })
        # ───────────────────────────────────────────────────────────────────────

        handler = self._tool_map.get(name)
        if handler is None:
            logger.warning("ManagedAgent[%s] unknown tool: %s", self.agent_id, name)
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            result = handler(input_dict)
            result_str = result if isinstance(result, str) else json.dumps(result)
            if len(result_str) > _TOOL_RESULT_MAX_CHARS:
                logger.debug(
                    "ManagedAgent[%s] tool %s result truncated (%d → %d chars)",
                    self.agent_id, name, len(result_str), _TOOL_RESULT_MAX_CHARS,
                )
                result_str = result_str[:_TOOL_RESULT_MAX_CHARS] + " ...[truncated]"
            logger.debug("ManagedAgent[%s] tool %s → %d chars", self.agent_id, name, len(result_str))
            return result_str
        except Exception as exc:
            logger.error("ManagedAgent[%s] tool %s error: %s", self.agent_id, name, exc)
            return json.dumps({"error": str(exc)})

    def _scan_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """Scan output fields for instruction-override patterns; redact affected fields."""
        if not isinstance(output, dict):
            return output
        clean: Dict[str, Any] = {}
        for k, v in output.items():
            if isinstance(v, str) and _OUTPUT_INJECT_RE.search(v):
                logger.warning(
                    "ManagedAgent[%s] output field '%s' contains injection pattern — redacted",
                    self.agent_id, k,
                )
                clean[k] = "[REDACTED: output injection detected]"
            elif isinstance(v, list):
                clean[k] = [
                    "[REDACTED: output injection detected]"
                    if isinstance(i, str) and _OUTPUT_INJECT_RE.search(i) else i
                    for i in v
                ]
            else:
                clean[k] = v
        return clean

    def _parse_output(self, content: str) -> Dict[str, Any]:
        """Parse final LLM output. Override for strict schema enforcement."""
        if not content.strip():
            return {}
        # Try JSON first, fall back to wrapping text
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content and "{" in content:
                for part in content.split("```"):
                    if "{" in part and "}" in part:
                        try:
                            return json.loads(part.strip())
                        except json.JSONDecodeError:
                            continue
            if "{" in content:
                end = content.rindex("}") + 1
                for start in (i for i, c in enumerate(content[:end]) if c == "{"):
                    try:
                        return json.loads(content[start:end])
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return {"summary": content}
