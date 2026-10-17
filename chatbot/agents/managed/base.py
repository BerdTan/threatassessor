"""
ManagedAgent — base class for the TA managed agent fleet.

A ManagedAgent wraps an LLM tool-call loop:
  build_task(context) → task prompt
  should_run(context) → pre-flight gate (Jev optional)
  run(context)        → tool loop → ManagedAgentResult

Adding an agent to the fleet = subclass + one line in registry._auto_register().
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_ITERATIONS_DEFAULT = 8


# ── primitives ────────────────────────────────────────────────────────────────

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


# ── base class ────────────────────────────────────────────────────────────────

class ManagedAgent(ABC):
    """
    Base class for all TA managed agents.

    Subclasses must implement:
      agent_id        (class attribute)
      description     (class attribute)
      system_prompt   (class attribute)
      tools           (list[AgentTool], populated in __init__)
      build_task()
      should_run()    (optional override; base always returns True)
    """

    agent_id: str = ""
    description: str = ""
    system_prompt: str = ""
    max_iterations: int = MAX_ITERATIONS_DEFAULT

    def __init__(self) -> None:
        self.tools: List[AgentTool] = []
        self._tool_map: Dict[str, Callable[[Dict[str, Any]], str]] = {}
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

    # ── tool loop ─────────────────────────────────────────────────────────────

    def run(self, context: Dict[str, Any]) -> ManagedAgentResult:
        """Execute the managed tool loop and return a structured result."""
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

        from agentic.llm_client import LLMClient
        client = LLMClient()

        tools_schema = [t.to_openai_schema() for t in self.tools]
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user",   "content": self.build_task(context)},
        ]

        total_tokens = 0
        tool_calls_made = 0

        for iteration in range(self.max_iterations):
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
                )

            if resp.stop_reason == "end_turn":
                # Final answer — parse structured output from content
                output = self._parse_output(resp.content or "")
                return ManagedAgentResult(
                    agent_id=self.agent_id,
                    success=True,
                    output=output,
                    tool_calls_made=tool_calls_made,
                    tokens_used=total_tokens,
                    jev_gate_passed=jev_passed,
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

                # Execute each tool and append results
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

        logger.warning("ManagedAgent[%s] exhausted max_iterations=%d", self.agent_id, self.max_iterations)
        return ManagedAgentResult(
            agent_id=self.agent_id,
            success=False,
            output={"error": f"max_iterations ({self.max_iterations}) reached"},
            tool_calls_made=tool_calls_made,
            tokens_used=total_tokens,
            jev_gate_passed=jev_passed,
        )

    def _execute_tool(self, name: str, input_dict: Dict[str, Any]) -> str:
        handler = self._tool_map.get(name)
        if handler is None:
            logger.warning("ManagedAgent[%s] unknown tool: %s", self.agent_id, name)
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            result = handler(input_dict)
            logger.debug("ManagedAgent[%s] tool %s → %d chars", self.agent_id, name, len(str(result)))
            return result if isinstance(result, str) else json.dumps(result)
        except Exception as exc:
            logger.error("ManagedAgent[%s] tool %s error: %s", self.agent_id, name, exc)
            return json.dumps({"error": str(exc)})

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
