"""
Agent Validation Framework for Phase 3C

Validates that:
1. Each agent uses LLM for reasoning (not just deterministic code)
2. Agent outputs meet minimum confidence threshold (85%)
3. Tool calling works reliably with configured LLM
4. Agent transactions are traced for debugging

VERSION: 1.0 - Initial implementation
"""

import json
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class AgentTrace:
    """Trace of agent execution for debugging."""
    agent_name: str
    start_time: float
    end_time: Optional[float] = None

    # Input
    input_type: str = ""  # "artifacts", "ground_truth", "architect_critique"
    input_summary: str = ""

    # LLM interaction
    llm_provider: str = ""
    llm_model: str = ""
    llm_calls: int = 0
    tool_calls: List[Dict] = field(default_factory=list)

    # Output
    output_score: int = 0
    output_confidence: float = 0.0
    output_gaps: int = 0
    output_rating: str = ""

    # Validation
    used_llm: bool = False  # Did agent call LLM?
    used_tools: bool = False  # Did agent use tools?
    meets_confidence: bool = False  # Score >= 85?
    is_valid: bool = False  # Overall validity

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def duration(self) -> float:
        """Calculate execution duration in seconds."""
        if self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "agent_name": self.agent_name,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_seconds": self.duration(),
            "input_type": self.input_type,
            "input_summary": self.input_summary,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "output_score": self.output_score,
            "output_confidence": self.output_confidence,
            "output_gaps": self.output_gaps,
            "output_rating": self.output_rating,
            "validation": {
                "used_llm": self.used_llm,
                "used_tools": self.used_tools,
                "meets_confidence": self.meets_confidence,
                "is_valid": self.is_valid
            },
            "errors": self.errors,
            "warnings": self.warnings
        }


@dataclass
class PipelineTrace:
    """Trace of full agent pipeline (Architect → Tester → Red Teamer)."""
    pipeline_id: str
    architecture_name: str
    start_time: float
    end_time: Optional[float] = None

    agent_traces: List[AgentTrace] = field(default_factory=list)

    # Overall validation
    all_agents_used_llm: bool = False
    all_agents_meet_confidence: bool = False
    pipeline_valid: bool = False

    errors: List[str] = field(default_factory=list)

    def duration(self) -> float:
        """Calculate total pipeline duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "pipeline_id": self.pipeline_id,
            "architecture_name": self.architecture_name,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_seconds": self.duration(),
            "agent_traces": [trace.to_dict() for trace in self.agent_traces],
            "validation": {
                "all_agents_used_llm": self.all_agents_used_llm,
                "all_agents_meet_confidence": self.all_agents_meet_confidence,
                "pipeline_valid": self.pipeline_valid
            },
            "errors": self.errors
        }


# ============================================================================
# AGENT VALIDATOR
# ============================================================================

class AgentValidator:
    """
    Validates agent execution meets Phase 3C requirements.

    Checks:
    1. Agent uses LLM (not just deterministic code)
    2. Output meets 85% confidence threshold
    3. Output structure is valid
    4. Traces execution for debugging

    Usage:
        validator = AgentValidator()
        trace = validator.start_trace("Architect")

        # ... run agent ...

        validator.end_trace(trace, critique_score)
        if not trace.is_valid:
            print(f"Issues: {trace.errors}")
    """

    def __init__(self, min_confidence: float = 85.0):
        """
        Initialize validator.

        Args:
            min_confidence: Minimum confidence threshold (0-100)
        """
        self.min_confidence = min_confidence
        self.traces: List[AgentTrace] = []

    def start_trace(self, agent_name: str, input_type: str = "") -> AgentTrace:
        """
        Start tracing agent execution.

        Args:
            agent_name: Name of agent (e.g., "Architect", "Tester")
            input_type: Type of input (e.g., "artifacts", "ground_truth")

        Returns:
            AgentTrace object to track execution
        """
        trace = AgentTrace(
            agent_name=agent_name,
            start_time=time.time(),
            input_type=input_type
        )

        logger.info(f"[TRACE] Started tracing {agent_name} agent")
        return trace

    def record_llm_call(
        self,
        trace: AgentTrace,
        provider: str,
        model: str
    ):
        """
        Record LLM call in trace.

        Args:
            trace: AgentTrace being tracked
            provider: LLM provider (openrouter, bedrock, etc.)
            model: Model name
        """
        trace.llm_calls += 1
        trace.llm_provider = provider
        trace.llm_model = model
        trace.used_llm = True

        logger.debug(f"[TRACE] {trace.agent_name}: LLM call #{trace.llm_calls} ({provider}/{model})")

    def record_tool_call(
        self,
        trace: AgentTrace,
        tool_name: str,
        parameters: Dict,
        result: Any
    ):
        """
        Record tool call in trace.

        Args:
            trace: AgentTrace being tracked
            tool_name: Name of tool called
            parameters: Tool parameters
            result: Tool result (truncated if large)
        """
        # Truncate large results
        result_summary = str(result)[:200] if result else "None"

        trace.tool_calls.append({
            "tool": tool_name,
            "parameters": parameters,
            "result_summary": result_summary,
            "timestamp": time.time()
        })
        trace.used_tools = True

        logger.debug(f"[TRACE] {trace.agent_name}: Tool call - {tool_name}")

    def end_trace(
        self,
        trace: AgentTrace,
        output: 'CritiqueScore'
    ):
        """
        End trace and validate output.

        Args:
            trace: AgentTrace being tracked
            output: CritiqueScore from agent
        """
        trace.end_time = time.time()

        # Record output
        trace.output_score = output.score
        trace.output_confidence = output.score  # Assuming score IS confidence (0-100)
        trace.output_gaps = len(output.gaps)
        trace.output_rating = output.rating

        # Validate
        self._validate_trace(trace)

        # Store
        self.traces.append(trace)

        # Log summary
        status = "✅ VALID" if trace.is_valid else "❌ INVALID"
        logger.info(
            f"[TRACE] {trace.agent_name} completed in {trace.duration():.1f}s - "
            f"Score: {trace.output_score}/100 ({trace.output_rating}) - {status}"
        )

        if trace.errors:
            for error in trace.errors:
                logger.error(f"[TRACE] {trace.agent_name}: {error}")

        if trace.warnings:
            for warning in trace.warnings:
                logger.warning(f"[TRACE] {trace.agent_name}: {warning}")

    def _validate_trace(self, trace: AgentTrace):
        """
        Validate trace meets Phase 3C requirements.

        Updates trace with validation results and errors.
        """
        # Check 1: Did agent use LLM?
        if not trace.used_llm or trace.llm_calls == 0:
            trace.errors.append(
                "Agent did NOT use LLM - violates Phase 3C 'LLM as Judge' requirement"
            )

        # Check 2: Meets confidence threshold?
        if trace.output_confidence < self.min_confidence:
            trace.errors.append(
                f"Confidence {trace.output_confidence:.1f}% below threshold {self.min_confidence}%"
            )
        else:
            trace.meets_confidence = True

        # Check 3: Valid output structure?
        if trace.output_score < 0 or trace.output_score > 100:
            trace.errors.append(f"Invalid score: {trace.output_score} (must be 0-100)")

        if not trace.output_rating:
            trace.warnings.append("Missing rating field")

        # Check 4: Tool usage (warning only, not required)
        if not trace.used_tools:
            trace.warnings.append(
                "Agent did not use any tools - may be relying only on LLM reasoning"
            )

        # Overall validity
        trace.is_valid = (
            trace.used_llm and
            trace.meets_confidence and
            len(trace.errors) == 0
        )

    def save_traces(self, filepath: str):
        """Save all traces to JSON file."""
        with open(filepath, 'w') as f:
            json.dump([trace.to_dict() for trace in self.traces], f, indent=2)

        logger.info(f"[TRACE] Saved {len(self.traces)} traces to {filepath}")


# ============================================================================
# PIPELINE VALIDATOR
# ============================================================================

class PipelineValidator:
    """
    Validates full agent pipeline (Architect → Tester → Red Teamer).

    Usage:
        pipeline = PipelineValidator("02_minimal_defended")

        # Architect
        arch_trace = pipeline.start_agent("Architect")
        architect_score = architect.critique(artifacts)
        pipeline.end_agent(arch_trace, architect_score)

        # Tester
        test_trace = pipeline.start_agent("Tester")
        tester_score = tester.critique(artifacts, architect_score)
        pipeline.end_agent(test_trace, tester_score)

        # Validate
        if not pipeline.is_valid():
            print(f"Pipeline issues: {pipeline.get_errors()}")
    """

    def __init__(self, architecture_name: str, min_confidence: float = 85.0):
        """
        Initialize pipeline validator.

        Args:
            architecture_name: Name of architecture being assessed
            min_confidence: Minimum confidence threshold (0-100)
        """
        self.trace = PipelineTrace(
            pipeline_id=f"{architecture_name}_{int(time.time())}",
            architecture_name=architecture_name,
            start_time=time.time()
        )

        self.agent_validator = AgentValidator(min_confidence)

        logger.info(f"[PIPELINE] Started pipeline for {architecture_name}")

    def start_agent(self, agent_name: str, input_type: str = "") -> AgentTrace:
        """Start tracing agent."""
        return self.agent_validator.start_trace(agent_name, input_type)

    def end_agent(self, agent_trace: AgentTrace, output: 'CritiqueScore'):
        """End agent trace and validate."""
        self.agent_validator.end_trace(agent_trace, output)
        self.trace.agent_traces.append(agent_trace)

    def finalize(self):
        """Finalize pipeline and validate."""
        self.trace.end_time = time.time()

        # Validate pipeline
        self._validate_pipeline()

        # Log summary
        status = "✅ VALID" if self.trace.pipeline_valid else "❌ INVALID"
        logger.info(
            f"[PIPELINE] Completed in {self.trace.duration():.1f}s - "
            f"{len(self.trace.agent_traces)} agents - {status}"
        )

    def _validate_pipeline(self):
        """Validate entire pipeline."""
        # Check all agents used LLM
        self.trace.all_agents_used_llm = all(
            trace.used_llm for trace in self.trace.agent_traces
        )

        if not self.trace.all_agents_used_llm:
            self.trace.errors.append(
                "Not all agents used LLM - violates Phase 3C requirement"
            )

        # Check all agents meet confidence
        self.trace.all_agents_meet_confidence = all(
            trace.meets_confidence for trace in self.trace.agent_traces
        )

        if not self.trace.all_agents_meet_confidence:
            failing_agents = [
                trace.agent_name for trace in self.trace.agent_traces
                if not trace.meets_confidence
            ]
            self.trace.errors.append(
                f"Agents below confidence threshold: {', '.join(failing_agents)}"
            )

        # Check no critical errors
        has_errors = any(trace.errors for trace in self.trace.agent_traces)

        # Overall validity
        self.trace.pipeline_valid = (
            self.trace.all_agents_used_llm and
            self.trace.all_agents_meet_confidence and
            not has_errors
        )

    def is_valid(self) -> bool:
        """Check if pipeline is valid."""
        return self.trace.pipeline_valid

    def get_errors(self) -> List[str]:
        """Get all errors from pipeline."""
        errors = list(self.trace.errors)
        for trace in self.trace.agent_traces:
            errors.extend([f"{trace.agent_name}: {e}" for e in trace.errors])
        return errors

    def save(self, filepath: str):
        """Save pipeline trace to JSON."""
        with open(filepath, 'w') as f:
            json.dump(self.trace.to_dict(), f, indent=2)

        logger.info(f"[PIPELINE] Saved trace to {filepath}")


# ============================================================================
# TOOL CALLING TESTER
# ============================================================================

def test_tool_calling(llm_provider: str = "openrouter", llm_model: Optional[str] = None):
    """
    Test tool calling with configured LLM.

    Args:
        llm_provider: LLM provider (openrouter, bedrock, etc.)
        llm_model: Optional model override

    Returns:
        Dict with test results

    Example:
        >>> results = test_tool_calling()
        >>> if results["success"]:
        ...     print("Tool calling works!")
    """
    from agentic.llm_client import LLMClient
    from chatbot.modules.agent_framework import AgentTool

    logger.info(f"Testing tool calling with {llm_provider}/{llm_model or 'default'}")

    # Define simple test tool
    def test_add(a: int, b: int) -> int:
        """Test function: add two numbers."""
        return a + b

    test_tool = AgentTool(
        name="add_numbers",
        description="Add two numbers together",
        function=test_add,
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    )

    # Test LLM with tool
    client = LLMClient()

    try:
        response = client.generate(
            prompt="What is 15 + 27? Use the add_numbers tool.",
            system_message="You are a helpful assistant with access to tools.",
            model=llm_model,
            tools=[test_tool.to_litellm_schema()],
            temperature=0.0
        )

        # Check if LLM called tool
        if hasattr(response, 'tool_calls') and response.tool_calls:
            tool_call = response.tool_calls[0]
            logger.info(f"✅ LLM called tool: {tool_call.function.name}")

            # Parse arguments
            import json
            args = json.loads(tool_call.function.arguments)

            # Execute tool
            result = test_add(args['a'], args['b'])

            logger.info(f"✅ Tool executed: add_numbers({args['a']}, {args['b']}) = {result}")

            return {
                "success": True,
                "llm_provider": llm_provider,
                "llm_model": llm_model or "default",
                "tool_called": tool_call.function.name,
                "tool_args": args,
                "tool_result": result,
                "supports_tool_calling": True
            }
        else:
            logger.warning("❌ LLM did not call tool (may not support tool calling)")
            return {
                "success": False,
                "llm_provider": llm_provider,
                "llm_model": llm_model or "default",
                "error": "LLM did not call tool",
                "response_content": response.content if hasattr(response, 'content') else str(response),
                "supports_tool_calling": False
            }

    except Exception as e:
        logger.error(f"❌ Tool calling test failed: {e}")
        return {
            "success": False,
            "llm_provider": llm_provider,
            "llm_model": llm_model or "default",
            "error": str(e),
            "supports_tool_calling": False
        }


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    print("\n" + "="*70)
    print("AGENT VALIDATION FRAMEWORK TEST")
    print("="*70 + "\n")

    # Test 1: Tool calling
    print("Test 1: Tool Calling with OpenRouter")
    print("-" * 70)

    results = test_tool_calling(llm_provider="openrouter")

    if results["success"]:
        print(f"✅ Tool calling works!")
        print(f"   Provider: {results['llm_provider']}")
        print(f"   Model: {results['llm_model']}")
        print(f"   Tool called: {results['tool_called']}")
        print(f"   Result: {results['tool_result']}")
    else:
        print(f"❌ Tool calling failed")
        print(f"   Error: {results.get('error', 'Unknown')}")
        print(f"   Supports tool calling: {results['supports_tool_calling']}")

    print("\n" + "="*70)
    print("Test complete. See logs above for details.")
    print("="*70 + "\n")
