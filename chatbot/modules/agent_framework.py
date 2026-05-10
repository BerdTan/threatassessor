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

VERSION: 1.1 - Fixed JSON parsing (markdown code blocks) + Unicode chars
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
    improvement_roadmap: List[Dict]  # How to increase score (priority-ordered)

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
        # MVP1: Disable tools for now - LLM prefers to ask for tools rather than directly answer
        # Full tool execution in MVP2+
        tool_schemas = None  # [tool.to_litellm_schema() for tool in self.tools] if self.tools else None

        # 3. Call LLM without tools (MVP1 simplification)
        try:
            # If model is None, LLMClient uses .env defaults (LLM_PROVIDER, BEDROCK_MODEL, etc.)
            logger.info(f"{self.role}: Calling LLM (model={self.model}, tools disabled for MVP1)")
            response = self.llm_client.generate(
                prompt=prompt,
                system_message=self.system_prompt,
                model=self.model,  # None = use .env config
                # tools=tool_schemas,  # Disabled for MVP1
                temperature=0.3,  # Lower for consistent scoring
                max_tokens=4000
            )
            logger.info(f"{self.role}: LLM call completed - Response type: {type(response)}")
            logger.info(f"{self.role}: Response attributes: {dir(response)[:10]}...")  # First 10 to avoid spam
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
        logger.info(f"{self.role}: Parsing response...")
        critique_data = self._parse_response(response)
        logger.info(f"{self.role}: Parsed data keys: {list(critique_data.keys()) if critique_data else 'None'}")

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
            strengths=critique_data.get("strengths", []),
            improvement_roadmap=critique_data.get("improvement_roadmap", [])
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
        # Extract key data (adapted to actual ground truth format)
        arch_name = ground_truth.get("architecture", "Unknown")
        arch_type = ground_truth.get("metadata", {}).get("architecture_type", "Unknown")

        # Component count from controls present + missing
        controls_present = ground_truth.get("controls_present", [])
        controls_missing = ground_truth.get("controls_missing", [])
        component_count = len(controls_present) + len(controls_missing)

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

        # Residual risk from residual_risks dict
        residual = ground_truth.get("residual_risks", {})
        before_risk = residual.get("before", {}).get("overall_risk", "N/A")
        after_risk = residual.get("after", {}).get("overall_risk", "N/A")

        # Get detailed data for critique
        controls_present_list = ", ".join(controls_present[:10]) if controls_present else "None"
        controls_missing_list = ", ".join(controls_missing[:10]) if controls_missing else "None"

        # Top 3 control recommendations with details
        control_details = []
        for ctrl in controls[:3]:
            control_details.append(
                f"  - {ctrl.get('control', 'N/A')} (priority: {ctrl.get('priority', 'N/A')}, "
                f"score: {ctrl.get('score', 0)}, threats: {', '.join(ctrl.get('rapids_threats', []))})"
            )
        control_summary = "\n".join(control_details) if control_details else "  (None)"

        # Attack path summary
        attack_path_summary = []
        for i, path in enumerate(techniques[:3], 1):
            techs = path.get('techniques', [])
            attack_path_summary.append(f"  Path {i}: {len(techs)} techniques ({', '.join(techs[:3])}...)")
        attack_paths = "\n".join(attack_path_summary) if attack_path_summary else "  (None)"

        # RAPIDS rationale
        rapids_rationale = []
        for threat_type, data in rapids.items():
            if threat_type != "_metadata":
                rationale = data.get('rationale', 'N/A')[:80]
                rapids_rationale.append(f"  - {threat_type}: {rationale}...")
        rapids_reasoning = "\n".join(rapids_rationale[:3]) if rapids_rationale else "  (None)"

        # Format prompt
        prompt = f"""
ARCHITECTURE TO REVIEW: {arch_name}

ARCHITECTURE CONTEXT:
- Type: {arch_type}
- Description: {ground_truth.get('description', 'N/A')}
- Controls Present ({len(controls_present)}): {controls_present_list}
- Controls Missing ({len(controls_missing)}): {controls_missing_list}

DETERMINISTIC ASSESSMENT (99.5% confidence baseline):

A. RAPIDS Threat Scores:
{rapids_summary}

B. RAPIDS Rationale (top 3):
{rapids_reasoning}

C. MITRE Attack Paths ({len(techniques)} total):
{attack_paths}

D. Control Recommendations ({control_count} total, showing top 3):
{control_summary}

E. Residual Risk Calculation:
- Before controls: {before_risk}
- After controls: {after_risk}

F. Validation: 6/6 checks PASS

============================================================
YOUR TASK
============================================================

Review this DETERMINISTIC assessment using the {self.role} rubric and provide a score (0-100).

IMPORTANT: You are critiquing the QUALITY of the assessment above, NOT creating a new threat analysis.
- Does the assessment cover all relevant threats for this architecture type?
- Are the control recommendations appropriate and feasible?
- Is the defense-in-depth strategy sufficient?
- Does it consider architecture-specific context?

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
  ],
  "improvement_roadmap": [
    {{
      "action": "Specific improvement action",
      "category": "threat_completeness|control_appropriateness|defense_in_depth|context_awareness",
      "points_gained": 5,
      "effort": "LOW|MEDIUM|HIGH",
      "priority": 1,
      "verification_method": "How Tester agent can verify this improvement",
      "expected_outcome": "What will change in the assessment"
    }}
  ]
}}

CRITICAL: The improvement_roadmap must show HOW TO INCREASE THE SCORE.
- List improvements in priority order (priority: 1 = highest)
- Each action should increase score by specific points_gained
- Include verification_method so Tester agent can validate improvements
- Sum of points_gained should bring score close to 100
"""
        return prompt.strip()

    def _parse_response(self, response: Any) -> Dict:
        """
        Parse LLM response into structured data.

        Handles both raw text and structured JSON responses.
        Supports markdown code blocks (```json...```) and raw JSON.
        """
        try:
            # DEBUG: Log response type and structure
            logger.info(f"{self.role}: Response type: {type(response)}")
            logger.info(f"{self.role}: Response has content attr: {hasattr(response, 'content')}")

            # Try to extract JSON from response
            if hasattr(response, 'content'):
                content = response.content
                logger.info(f"{self.role}: Extracted content from response.content (length: {len(content)})")
            elif isinstance(response, dict):
                content = response.get('content', str(response))
                logger.info(f"{self.role}: Extracted content from dict (length: {len(content)})")
            else:
                content = str(response)
                logger.info(f"{self.role}: Converted response to string (length: {len(content)})")

            # DEBUG: Log content preview
            logger.info(f"{self.role}: Content preview (first 200 chars): {content[:200]}")
            logger.info(f"{self.role}: Has '```json': {'```json' in content}")
            logger.info(f"{self.role}: Has '{{': {'{' in content}")

            # Find JSON block (try markdown first, then raw)
            if '```json' in content:
                # Markdown code block: ```json { ... } ```
                json_str = content.split('```json')[1].split('```')[0].strip()
                logger.info(f"{self.role}: Found ```json block (length: {len(json_str)})")
            elif '```' in content and '{' in content:
                # Generic code block: ``` { ... } ```
                parts = content.split('```')
                for part in parts:
                    if '{' in part and '}' in part:
                        json_str = part.strip()
                        logger.info(f"{self.role}: Found generic ``` block (length: {len(json_str)})")
                        break
                else:
                    raise ValueError("No JSON in code blocks")
            elif '{' in content and '}' in content:
                # Raw JSON (no code block)
                start = content.index('{')
                end = content.rindex('}') + 1
                json_str = content[start:end]
                logger.info(f"{self.role}: Found raw JSON (length: {len(json_str)})")
            else:
                logger.warning(f"{self.role}: No JSON found in response, using defaults")
                logger.warning(f"{self.role}: Full content: {content}")
                return {}

            # Parse JSON
            logger.info(f"{self.role}: Attempting to parse JSON string...")
            parsed = json.loads(json_str)
            logger.info(f"{self.role}: Successfully parsed JSON response with keys: {list(parsed.keys())}")
            return parsed

        except Exception as e:
            logger.error(f"{self.role}: Failed to parse response: {e}")
            logger.error(f"{self.role}: Exception type: {type(e)}")
            # Log first 1000 chars for debugging
            if hasattr(response, 'content'):
                logger.warning(f"Response content (first 1000 chars): {response.content[:1000]}")
            elif 'content' in locals():
                logger.warning(f"Extracted content (first 1000 chars): {content[:1000]}")
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
    1. Run Architect -> Tester -> Red Teamer (sequential)
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
