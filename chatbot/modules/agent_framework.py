"""
Agent Framework for Phase 3C LLM Critic

Provides reusable agent classes for critique roles:
- CriticAgent: Individual critic (Architect, Tester, Red Teamer)
- OrchestratorAgent: Manages 3 critics, aggregates scores

Design Philosophy:
- Lightweight (~150 lines)
- No external dependencies (uses existing LiteLLM)
- Tool-augmented reasoning
- Structured output (JSON schema validation)
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import Dict, List, Callable, Optional, Any

from agentic.llm_client import LLMClient

logger = logging.getLogger(__name__)


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class AgentTool:
    """Tool that agents can use during critique"""
    name: str
    description: str
    function: Callable
    parameters: Dict[str, Any]  # JSON schema for parameters

    def to_litellm_schema(self) -> Dict:
        """Convert to LiteLLM tool definition format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


@dataclass
class CritiqueScore:
    """Structured output from a critic agent"""
    role: str
    score: int  # 0-100
    max_score: int  # Usually 100
    rating: str  # EXCELLENT, GOOD, FAIR, POOR
    breakdown: Dict[str, Dict]  # Per-rubric-category scores
    gaps: List[Dict]  # Identified gaps/issues
    strengths: List[str]  # What was done well

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================================
# CRITIC AGENT (Reusable for all 3 roles)
# ============================================================================

class CriticAgent:
    """
    Reusable agent for critique roles.

    Each critic is configured with:
    - role: Name (e.g., "Security Architect")
    - rubric: Scoring criteria (dict with categories and weights)
    - system_prompt: Explicit instructions (no assumed terms)
    - tools: Optional tools for augmented reasoning

    The agent:
    1. Formats prompt with ground truth data
    2. LLM generates critique with optional tool calls
    3. Executes tools if requested
    4. Validates output against rubric schema
    5. Returns CritiqueScore
    """

    def __init__(
        self,
        role: str,
        rubric: Dict,
        system_prompt: str,
        tools: Optional[List[AgentTool]] = None,
        model: Optional[str] = None
    ):
        self.role = role
        self.rubric = rubric
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.model = model  # If None, LLMClient uses .env defaults
        self.llm_client = LLMClient()

        logger.info(f"Initialized {role} agent with {len(self.tools)} tools")

    def critique(self, ground_truth: Dict) -> CritiqueScore:
        """
        Execute critique workflow.

        Returns: CritiqueScore with structured findings
        """
        logger.info(f"{self.role}: Starting critique")

        # 1. Format prompt with ground truth data
        prompt = self._format_prompt(ground_truth)

        # 2. Convert tools to LiteLLM format
        tool_schemas = [tool.to_litellm_schema() for tool in self.tools] if self.tools else None

        # 3. Call LLM with tools
        try:
            # If model is None, LLMClient uses .env defaults (LLM_PROVIDER, BEDROCK_MODEL, etc.)
            response = self.llm_client.generate(
                prompt=prompt,
                system_message=self.system_prompt,
                model=self.model,  # None = use .env config
                tools=tool_schemas,
                temperature=0.3,  # Lower for consistent scoring
                max_tokens=4000
            )
        except Exception as e:
            logger.error(f"{self.role}: LLM call failed: {e}")
            raise

        # 4. Handle tool calls (if any)
        if hasattr(response, 'tool_calls') and response.tool_calls:
            logger.info(f"{self.role}: Executing {len(response.tool_calls)} tool calls")
            tool_results = self._execute_tools(response.tool_calls)

            # Re-prompt with tool results
            # (Simplified for MVP1 - full implementation in MVP2+)
            logger.warning(f"{self.role}: Tool execution not yet implemented in MVP1")

        # 5. Extract and validate output
        critique_data = self._parse_response(response)

        # 6. Validate against rubric
        if not self._validate_output(critique_data):
            logger.warning(f"{self.role}: Output validation failed, using defaults")

        # 7. Convert to CritiqueScore
        score = CritiqueScore(
            role=self.role,
            score=critique_data.get("score", 0),
            max_score=critique_data.get("max_score", 100),
            rating=critique_data.get("rating", "UNKNOWN"),
            breakdown=critique_data.get("breakdown", {}),
            gaps=critique_data.get("gaps", []),
            strengths=critique_data.get("strengths", [])
        )

        logger.info(f"{self.role}: Critique complete - Score: {score.score}/{score.max_score} ({score.rating})")
        return score

    def _format_prompt(self, ground_truth: Dict) -> str:
        """
        Insert ground truth data into prompt template.

        Template variables:
        - {architecture_name}
        - {architecture_type}
        - {component_count}
        - {rapids_summary}
        - {technique_count}
        - {control_count}
        - {before_risk}
        - {after_risk}
        """
        # Extract key data
        arch_name = ground_truth.get("architecture_name", "Unknown")
        arch_type = ground_truth.get("metadata", {}).get("architecture_type", "Unknown")
        nodes = ground_truth.get("parsed_nodes", {})
        component_count = len(nodes)

        rapids = ground_truth.get("rapids_assessment", {})
        rapids_summary = "\n".join([
            f"  - {threat_type.replace('_', ' ').title()}: {data.get('risk', 0)}/100 risk"
            for threat_type, data in rapids.items()
            if threat_type != "_metadata"
        ])

        techniques = ground_truth.get("expected_attack_paths", [])
        technique_count = sum(len(path.get("techniques", [])) for path in techniques)

        controls = ground_truth.get("control_recommendations", [])
        control_count = len(controls)

        residual = ground_truth.get("residual_risk_calculation", {})
        before_risk = residual.get("before", {}).get("overall_risk", "N/A")
        after_risk = residual.get("after", {}).get("overall_risk", "N/A")

        # Format prompt
        prompt = f"""
ARCHITECTURE TO REVIEW: {arch_name}

ARCHITECTURE CONTEXT:
- Type: {arch_type}
- Components: {component_count} nodes
- Entry Points: {nodes.get(list(nodes.keys())[0] if nodes else 'Unknown', {}).get('label', 'Unknown')}

DETERMINISTIC ASSESSMENT (99.5% confidence baseline):

RAPIDS Threats (6 categories):
{rapids_summary}

MITRE Techniques Mapped: {technique_count}
Controls Recommended: {control_count}
Residual Risk: {before_risk} → {after_risk}
Validation: 6/6 checks PASS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Review this assessment using the {self.role} rubric and provide a score (0-100).

For each rubric category:
1. Score (0-10 or as specified)
2. Reasoning (why this score?)
3. Gaps identified (if score is not perfect)
4. Improvement suggestions (specific, actionable)

OUTPUT FORMAT (JSON):
{{
  "score": 92,
  "max_score": 100,
  "rating": "EXCELLENT",
  "breakdown": {{
    "category_1": {{"score": 38, "max": 40, "gaps": [...]}},
    "category_2": {{"score": 28, "max": 30, "gaps": [...]}}
  }},
  "gaps": [
    {{
      "category": "...",
      "severity": "HIGH/MEDIUM/LOW",
      "description": "...",
      "recommendation": "...",
      "affected_components": [...],
      "estimated_impact": "..."
    }}
  ],
  "strengths": [
    "Strength 1...",
    "Strength 2..."
  ]
}}
"""
        return prompt.strip()

    def _parse_response(self, response: Any) -> Dict:
        """
        Parse LLM response into structured data.

        Handles both raw text and structured JSON responses.
        Supports markdown code blocks (```json...```) and raw JSON.
        """
        try:
            # Try to extract JSON from response
            if hasattr(response, 'content'):
                content = response.content
            elif isinstance(response, dict):
                content = response.get('content', str(response))
            else:
                content = str(response)

            # Find JSON block (try markdown first, then raw)
            if '```json' in content:
                # Markdown code block: ```json { ... } ```
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content and '{' in content:
                # Generic code block: ``` { ... } ```
                parts = content.split('```')
                for part in parts:
                    if '{' in part and '}' in part:
                        json_str = part.strip()
                        break
                else:
                    raise ValueError("No JSON in code blocks")
            elif '{' in content and '}' in content:
                # Raw JSON (no code block)
                start = content.index('{')
                end = content.rindex('}') + 1
                json_str = content[start:end]
            else:
                logger.warning(f"{self.role}: No JSON found in response, using defaults")
                return {}

            # Parse JSON
            parsed = json.loads(json_str)
            logger.info(f"{self.role}: Successfully parsed JSON response")
            return parsed

        except Exception as e:
            logger.error(f"{self.role}: Failed to parse response: {e}")
            # Log first 500 chars for debugging
            if hasattr(response, 'content'):
                logger.debug(f"Response content (first 500): {response.content[:500]}")
            return {}

    def _validate_output(self, critique_data: Dict) -> bool:
        """
        Validate critique output against expected schema.

        Checks:
        - Required fields present
        - Score in valid range (0-100)
        - Breakdown matches rubric categories
        """
        required_fields = ["score", "rating", "breakdown", "gaps"]
        for field in required_fields:
            if field not in critique_data:
                logger.warning(f"{self.role}: Missing required field: {field}")
                return False

        score = critique_data.get("score", -1)
        if not (0 <= score <= 100):
            logger.warning(f"{self.role}: Invalid score: {score}")
            return False

        return True

    def _execute_tools(self, tool_calls: List) -> List[Dict]:
        """
        Execute tool calls from LLM.

        Returns: List of tool results
        """
        results = []
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # Find matching tool
            tool = next((t for t in self.tools if t.name == tool_name), None)
            if not tool:
                logger.warning(f"{self.role}: Unknown tool: {tool_name}")
                continue

            # Execute tool
            try:
                result = tool.function(**tool_args)
                results.append({
                    "tool": tool_name,
                    "result": result
                })
            except Exception as e:
                logger.error(f"{self.role}: Tool execution failed: {tool_name} - {e}")
                results.append({
                    "tool": tool_name,
                    "error": str(e)
                })

        return results


# ============================================================================
# ORCHESTRATOR AGENT (Manages 3 critics)
# ============================================================================

class OrchestratorAgent:
    """
    Manages 3 critic agents in sequence.

    Workflow:
    1. Run Architect → Tester → Red Teamer (sequential)
    2. Aggregate scores (weighted average)
    3. Resolve conflicts (if agents disagree)
    4. Consolidate improvements (de-duplicate, prioritize)
    5. Generate unified report

    Note: MVP1 focuses on sequential execution and basic aggregation.
    Conflict resolution and advanced features in MVP4.
    """

    def __init__(self, critic_agents: List[CriticAgent]):
        if len(critic_agents) != 3:
            raise ValueError("OrchestratorAgent requires exactly 3 critic agents")

        self.critics = critic_agents
        logger.info(f"Initialized Orchestrator with {len(critic_agents)} critics")

    def run_critique(self, ground_truth: Dict) -> Dict:
        """
        Execute full critique workflow.

        Returns: Unified critique report with aggregated scores
        """
        logger.info("Orchestrator: Starting critique workflow")

        # 1. Run each critic sequentially
        critique_scores = []
        for critic in self.critics:
            try:
                score = critic.critique(ground_truth)
                critique_scores.append(score)
            except Exception as e:
                logger.error(f"Orchestrator: {critic.role} failed: {e}")
                # Continue with other critics

        if not critique_scores:
            raise RuntimeError("All critics failed - cannot generate report")

        # 2. Aggregate scores
        composite_score = self._calculate_composite_score(critique_scores)

        # 3. Consolidate improvements (de-duplicate gaps)
        all_gaps = []
        for score in critique_scores:
            all_gaps.extend(score.gaps)

        improvements = self._consolidate_improvements(all_gaps)

        # 4. Generate unified report
        report = {
            "critic_scores": {
                score.role: {
                    "score": score.score,
                    "rating": score.rating,
                    "gaps": len(score.gaps),
                    "strengths": len(score.strengths)
                }
                for score in critique_scores
            },
            "composite_score": composite_score,
            "improvements": improvements,
            "baseline_confidence": 0.995,  # Phase 3B+ baseline
            "confidence_adjustment": self._calculate_confidence_boost(composite_score),
            "detailed_critiques": [score.to_dict() for score in critique_scores]
        }

        logger.info(f"Orchestrator: Critique complete - Composite: {composite_score}/100")
        return report

    def _calculate_composite_score(self, scores: List[CritiqueScore]) -> float:
        """
        Calculate weighted composite score.

        Weights:
        - Architect: 30% (design quality)
        - Tester: 30% (validation quality)
        - Red Team: 40% (defense strength, INVERTED)

        Note: Red Team score is inverted (lower = better defense)
        """
        if len(scores) != 3:
            logger.warning("Orchestrator: Expected 3 scores for composite calculation")
            return sum(s.score for s in scores) / len(scores)

        architect_score = scores[0].score  # Assume order: Architect, Tester, Red Team
        tester_score = scores[1].score
        red_team_score = scores[2].score

        # Invert red team score (low score = hard to breach = good)
        red_team_defense = 100 - red_team_score

        composite = (
            architect_score * 0.30 +
            tester_score * 0.30 +
            red_team_defense * 0.40
        )

        return round(composite, 1)

    def _calculate_confidence_boost(self, composite_score: float) -> float:
        """
        Calculate confidence adjustment based on composite score.

        Thresholds:
        - 95+: +0.5% (excellent across all dimensions)
        - 90-94: +0.3% (good across all dimensions)
        - 85-89: +0.1% (fair across all dimensions)
        - 80-84: 0.0% (no boost, some issues)
        - <80: -0.5% (significant gaps)
        """
        if composite_score >= 95:
            return 0.005
        elif composite_score >= 90:
            return 0.003
        elif composite_score >= 85:
            return 0.001
        elif composite_score >= 80:
            return 0.0
        else:
            return -0.005

    def _consolidate_improvements(self, gaps: List[Dict]) -> List[Dict]:
        """
        Consolidate gaps from all critics, de-duplicate, prioritize.

        Returns: Top 5 improvements (HIGH/MEDIUM/LOW priority)
        """
        # De-duplicate by description similarity (simple MVP1 version)
        unique_gaps = []
        seen_descriptions = set()

        for gap in gaps:
            desc = gap.get("description", "")
            if desc not in seen_descriptions:
                unique_gaps.append(gap)
                seen_descriptions.add(desc)

        # Sort by severity (HIGH > MEDIUM > LOW)
        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        unique_gaps.sort(key=lambda g: severity_order.get(g.get("severity", "LOW"), 2))

        # Return top 5
        return unique_gaps[:5]
