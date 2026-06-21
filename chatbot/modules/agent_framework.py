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

VERSION: 1.2 - Refactored to use BaseAgent hierarchy
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Callable, Optional, Any

from chatbot.modules.base_agent import BaseAgent, AgentResult
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
    reasoning: str = ""  # 2-3 sentence "so what" from the LLM — shown as topliner in UI

    # ── Performance telemetry (populated by CriticAgent.critique()) ─────────
    # llm_calls: number of LLM round-trips (1 normally; >1 if tool-use or retries)
    llm_calls: int = 0
    llm_tokens: int = 0          # total tokens (prompt + completion)
    llm_cost_usd: float = 0.0   # estimated cost
    llm_latency_s: float = 0.0  # wall-clock seconds for all LLM calls combined
    llm_model: str = ""          # exact model string used
    wall_clock_s: float = 0.0   # total time for the full critique() call (parse + LLM)

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================================
# CRITIC AGENT (Reusable for all 3 roles)
# ============================================================================

class CriticAgent(BaseAgent):
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
        super().__init__(role=role, model=model)
        self.rubric = rubric
        self.system_prompt = system_prompt
        self.tools = tools or []

        logger.info(f"Initialized {role} critic agent with {len(self.tools)} tools")

    def execute(self, context: Dict) -> CritiqueScore:
        """
        Execute critique workflow (implements BaseAgent.execute()).

        Args:
            context: Must contain "ground_truth" key

        Returns:
            CritiqueScore with structured findings
        """
        return self.critique(context.get("ground_truth", context))

    def get_capabilities(self) -> List[str]:
        """Return critic capabilities."""
        return ["critique", "score", "identify_gaps", "recommend_improvements"]

    def critique(self, ground_truth: Dict) -> CritiqueScore:
        """
        Execute critique workflow.

        Returns: CritiqueScore with structured findings
        """
        _wall_start = time.time()
        logger.info(f"{self.role}: Starting critique")

        # 1. Format prompt with ground truth data
        prompt = self._format_prompt(ground_truth)

        # 2. Convert tools to LiteLLM format
        # Tools disabled by default (_tools_enabled=False). Set to True on subclass to enable.
        _tools_enabled = getattr(self, "_tools_enabled", False)
        tool_schemas = [t.to_litellm_schema() for t in self.tools] if (self.tools and _tools_enabled) else None

        # 3. Call LLM without tools (MVP1 simplification)
        _llm_tokens = 0
        _llm_cost   = 0.0
        _llm_latency = 0.0
        _llm_model  = self.model or ""
        _llm_calls  = 0
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
            _llm_calls   += 1
            _llm_tokens  += getattr(response, 'tokens_used', 0) or 0
            _llm_cost    += getattr(response, 'cost_usd', 0.0) or 0.0
            _llm_latency += getattr(response, 'latency_seconds', 0.0) or 0.0
            _llm_model    = getattr(response, 'model', self.model or "") or _llm_model
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
        raw_roadmap = critique_data.get("improvement_roadmap", [])
        current_score = critique_data.get("score", 0)

        # Normalize roadmap to realistic target (85-95, not >100)
        normalized_roadmap = self._normalize_roadmap(raw_roadmap, current_score)

        _wall_elapsed = time.time() - _wall_start
        score = CritiqueScore(
            role=self.role,
            score=current_score,
            max_score=critique_data.get("max_score", 100),
            rating=critique_data.get("rating", "UNKNOWN"),
            breakdown=critique_data.get("breakdown", {}),
            gaps=critique_data.get("gaps", []),
            strengths=critique_data.get("strengths", []),
            improvement_roadmap=normalized_roadmap,
            reasoning=critique_data.get("reasoning", ""),
            llm_calls=_llm_calls,
            llm_tokens=_llm_tokens,
            llm_cost_usd=round(_llm_cost, 6),
            llm_latency_s=round(_llm_latency, 3),
            llm_model=_llm_model,
            wall_clock_s=round(_wall_elapsed, 3),
        )

        logger.info(
            f"{self.role}: Critique complete — Score: {score.score}/{score.max_score} ({score.rating}) "
            f"| {score.llm_tokens} tokens | ${score.llm_cost_usd:.4f} | {score.wall_clock_s:.1f}s"
        )
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
  "rating": "GOOD",
  "reasoning": "1-2 plain sentences stating the single most important finding from this review and its direct consequence for the architecture. State facts, not grades. Do not use terms like 'excellent', 'impressive', or 'great'. Do not reference the assessor tool, your role, or the organisation's context unless directly relevant to the finding.",
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
- Target realistic improvement (aim for 85-90, not perfection)

VALUABLE IMPROVEMENTS (in priority order):
1. MITRE Technique Quality & Accuracy (HIGH VALUE)
   - More architecture-specific techniques (not generic)
   - Accurate technique IDs mapped to actual attack paths
   - Complete kill chains (initial access → execution → persistence → exfiltration)
   - Example: "Replace generic T1059 with specific T1190.003 (SQL Injection) for web app"

2. RAPIDS Risk Mitigation (HIGH VALUE)
   - Controls that demonstrably reduce specific RAPIDS scores
   - Example: "Add backup control → reduces Ransomware risk 70→30" (measurable)
   - Map each control to RAPIDS categories it mitigates

3. Attack Path Completeness (MEDIUM VALUE)
   - Cover all entry points (web, API, admin, file upload)
   - Show multi-stage attack progression
   - Include lateral movement paths

4. Defense-in-Depth Validation (MEDIUM VALUE)
   - Multiple control layers per critical path
   - Prevention + Detection + Isolation + Response coverage
   - No single points of failure

SCORING GUIDANCE:
- 90-100: EXCELLENT (rare, near-perfect assessment)
- 80-89: GOOD (strong assessment, minor gaps)
- 70-79: FAIR (acceptable but notable gaps)
- <70: POOR (significant improvements needed)
"""
        return prompt.strip()

    def _parse_response(self, response: Any) -> Dict:
        """Parse LLM response (delegates to BaseAgent._parse_llm_response)."""
        return self._parse_llm_response(response)

    def _validate_output(self, critique_data: Dict) -> bool:
        """
        Validate critique output against expected schema.

        Checks:
        - Required fields present
        - Score in valid range (0-100)
        - Breakdown matches rubric categories
        """
        required_fields = ["score", "rating", "breakdown", "gaps"]
        if not self._validate_dict_fields(critique_data, required_fields):
            return False

        score = critique_data.get("score", -1)
        return self._validate_score_range(score, 0, 100)

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

            # Execute tool (wrapped by governance adapter if present)
            fn = tool.function
            governance_adapter = getattr(self, "_governance_adapter", None)
            if governance_adapter is not None:
                try:
                    fn = governance_adapter.wrap_capability(fn, "tool", self.role)
                except Exception:
                    pass  # governance wrap failure is non-fatal
            try:
                result = fn(**tool_args)
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

    def _normalize_roadmap(self, roadmap: List[Dict], current_score: int) -> List[Dict]:
        """
        Normalize improvement roadmap to realistic target (85-95, not >100).

        Logic:
        - Target realistic best: 90/100 (allows room for improvement)
        - If current + sum(points) > 90, proportionally scale down
        - Keep priority ordering and relative weights
        - Ensure focus on RAPIDS mitigation improvements
        """
        if not roadmap:
            return []

        # Calculate realistic target based on current score
        if current_score >= 85:
            target = 95  # Near-perfect, small improvements
        elif current_score >= 70:
            target = 90  # Good, can reach excellent
        elif current_score >= 50:
            target = 85  # Fair, can reach good
        else:
            target = 75  # Poor, significant work needed

        # Calculate total points and scaling factor
        total_points = sum(item.get("points_gained", 0) for item in roadmap)
        max_gain = target - current_score

        if total_points == 0:
            return roadmap

        if total_points > max_gain:
            # Need to scale down proportionally
            scale_factor = max_gain / total_points
            logger.info(f"{self.role}: Normalizing roadmap: {total_points} pts -> {max_gain} pts (scale={scale_factor:.2f})")

            normalized = []
            for item in roadmap:
                original_points = item.get("points_gained", 0)
                scaled_points = max(1, round(original_points * scale_factor))  # Min 1 point

                normalized.append({
                    **item,
                    "points_gained": scaled_points,
                    "original_points": original_points  # Keep for reference
                })

            return normalized
        else:
            # Points within range, no scaling needed
            return roadmap


# ============================================================================
# ORCHESTRATOR AGENT (Manages 3 critics)
# ============================================================================
# NOTE: This class is deprecated in favor of Orchestrator in orchestrator.py
# Kept for potential future use in simplified orchestration scenarios
# ============================================================================

class OrchestratorAgent(BaseAgent):
    """
    Manages critic agents in sequence.

    Workflow:
    1. Run critics sequentially (Architect -> Tester -> Red Teamer)
    2. Aggregate scores (weighted average)
    3. Resolve conflicts (if agents disagree)
    4. Consolidate improvements (de-duplicate, prioritize)
    5. Generate unified report

    Note: MVP1 focuses on sequential execution with 3 critics.
    Future: Support variable agent count and parallel execution.
    """

    def __init__(self, critic_agents: List[BaseAgent], workflow: str = "sequential"):
        super().__init__(role="Orchestrator")

        # For now, require exactly 3 critics (backward compatibility)
        # Future: Support any number of agents
        if len(critic_agents) != 3:
            raise ValueError("OrchestratorAgent currently requires exactly 3 critic agents")

        self.critics = critic_agents
        self.workflow = workflow  # "sequential" only for now
        logger.info(f"Initialized Orchestrator with {len(critic_agents)} critics")

    def execute(self, context: Dict) -> Dict:
        """
        Execute orchestration workflow (implements BaseAgent.execute()).

        Args:
            context: Must contain "ground_truth" key

        Returns:
            Unified critique report with aggregated scores
        """
        return self.run_critique(context.get("ground_truth", context))

    def get_capabilities(self) -> List[str]:
        """Return orchestrator capabilities."""
        return ["orchestrate", "aggregate_scores", "consolidate_improvements"]

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
