"""
Red Teamer Critic Agent for Phase 3C+

Role: Offensive Security Assessor evaluating exploit difficulty

Focus:
- Exploit difficulty (can attacker actually breach?)
- Defense evasion (can attacker bypass controls?)
- Attack path realism (is progression realistic?)

Scoring: INVERTED (0-100)
- Low score (0-40) = Hard to exploit = GOOD defense
- High score (60-100) = Easy to exploit = BAD defense

Approach: Prompt-based with post-processing validation (4 checks)
- Check 1: Control existence (no hallucinated controls)
- Check 2: Difficulty reasonableness (score matches control count)
- Check 3: Tester gap integration (adjust for invalid mappings)
- Check 4: Inverted scoring validation (auto-correct if forgotten)

VERSION: 2.0 - Refactored to inherit from CriticAgent
"""

import json
import logging
from typing import Dict, List, Optional
from pathlib import Path

from chatbot.modules.agent_framework import CriticAgent, CritiqueScore
from chatbot.modules.artifact_extractor import ArtifactSet

logger = logging.getLogger(__name__)


class RedTeamerCritic(CriticAgent):
    """
    Red Team critic assessing exploit difficulty.

    Rubric (100 points, INVERTED):
    - Exploit Difficulty: 40 points
    - Defense Evasion: 30 points
    - Attack Path Realism: 30 points

    INVERTED: Low score = hard to exploit = GOOD defense
    """

    def __init__(self, model: str = None):
        """
        Initialize Red Teamer critic.

        Args:
            model: Optional model override (uses .env if None)
        """
        # Initialize parent CriticAgent
        super().__init__(
            role="Red Teamer",
            rubric=self._create_rubric(),
            system_prompt=self._create_system_prompt(),
            tools=[],  # No tools for Red Teamer MVP
            model=model
        )

        # Red Teamer specific state
        self.prompt_template = self._create_prompt_template()

        logger.info(f"Initialized {self.role} critic agent")

    def _create_system_prompt(self) -> str:
        """System prompt defining Red Teamer role."""
        return """You are a Red Team assessor evaluating exploit difficulty from an offensive security perspective.

Your role: Assess how hard it would be for a real attacker to breach this architecture.

Key principle: Think like an attacker
- What tools are available? (Metasploit, Burp Suite, custom exploits)
- What skill level is needed? (script kiddie, professional, APT)
- Can deployed controls be bypassed?

IMPORTANT - INVERTED SCORING:
- Low score (0-40) = Very hard to exploit = GOOD defense ✅
- High score (60-100) = Easy to exploit = BAD defense ❌

Be realistic, not optimistic. If controls can be bypassed with public tools, score accordingly."""

    def _create_rubric(self) -> Dict:
        """
        Red Team rubric (100 points, INVERTED).

        INVERTED: Lower scores = better defense
        """
        return {
            "total_points": 100,
            "categories": {
                "exploit_difficulty": {
                    "points": 40,
                    "description": "How hard to execute attack paths?",
                    "criteria": [
                        "Path complexity (10 pts) - More hops = harder",
                        "Technique sophistication (10 pts) - T14xx harder than T10xx",
                        "Skill required (10 pts) - Script kiddie vs APT",
                        "Tool availability (10 pts) - Public exploits vs custom"
                    ]
                },
                "defense_evasion": {
                    "points": 30,
                    "description": "Can attacker bypass controls?",
                    "criteria": [
                        "Control bypass (15 pts) - Can evade deployed controls?",
                        "Detection avoidance (15 pts) - Can stay undetected?"
                    ]
                },
                "attack_path_realism": {
                    "points": 30,
                    "description": "Are attack paths realistic?",
                    "criteria": [
                        "Tactic sequence (10 pts) - Is progression realistic?",
                        "Privilege escalation (10 pts) - Can attacker gain needed access?",
                        "Persistence (10 pts) - Can attacker maintain access?"
                    ]
                }
            },
            "rating_scale": {
                "0-29": "MINIMAL = Nearly impossible = EXCELLENT defense",
                "30-49": "LOW = Very difficult = GOOD defense",
                "50-69": "MEDIUM = Difficult = ACCEPTABLE defense",
                "70-89": "HIGH = Moderate difficulty = WEAK defense",
                "90-100": "CRITICAL = Trivial to exploit = BAD defense"
            }
        }

    def _create_prompt_template(self) -> str:
        """
        Create Red Team prompt template.

        Template receives:
        - {deployed_controls}: List of actual controls present
        - {attack_paths}: Attack path details
        - {tester_gaps}: Optional gaps from Tester
        """
        return """# Red Team Assessment - Exploit Difficulty Analysis

IMPORTANT: This uses INVERTED scoring
- Low score (0-40) = Hard to exploit = GOOD defense ✅
- High score (60-100) = Easy to exploit = BAD defense ❌

## Architecture Overview

**Deployed Controls (what's actually protecting):**
{deployed_controls}

**Attack Paths:**
{attack_paths}

{tester_validation}

## Scoring Guide (INVERTED)

**0-29 points (MINIMAL):**
- Nearly impossible to exploit
- Multiple strong controls (WAF + MFA + EDR + IDS)
- No known bypasses
- Requires APT-level capabilities + 0-day exploits

**30-49 points (LOW):**
- Very difficult to exploit
- Strong controls like MFA + EDR
- Requires custom exploits and professional skills
- Public tools mostly ineffective

**50-69 points (MEDIUM):**
- Difficult to exploit
- Moderate controls (basic firewall, logging)
- Requires professional skills
- Public tools need customization

**70-89 points (HIGH):**
- Moderate difficulty
- Weak or few controls
- Public tools work with some skill
- Script kiddie + Metasploit can succeed

**90-100 points (CRITICAL):**
- Trivial to exploit
- No controls or easily bypassed
- Metasploit + default credentials work
- Script kiddie level

## Examples

**Example 1: No controls deployed**
```
Deployed controls: NONE
Attack path: Internet → Web Server → Database
Analysis: Direct exploitation possible, no barriers
Tools: Metasploit + nmap + sqlmap
Skill: Script kiddie
Score: 85/100 (CRITICAL = Easy to exploit = BAD defense)
```

**Example 2: Strong defense-in-depth**
```
Deployed controls: WAF, MFA, EDR, Encryption, IDS, DLP
Attack path: Internet → WAF → MFA → Web Server (EDR) → Database (Encrypted)
Analysis: Multiple layers, each requires bypass
- WAF blocks web exploits (requires custom payloads)
- MFA blocks auth (requires phishing or SIM swap)
- EDR detects malware (requires custom malware)
- IDS alerts on anomalies (requires stealth techniques)
Tools: Custom exploits, advanced malware, social engineering
Skill: APT-level
Score: 25/100 (LOW = Very hard to exploit = GOOD defense)
```

## Your Task

Assess overall exploit difficulty based ONLY on deployed controls listed above.

DO NOT assume controls that aren't deployed.
DO NOT be overly optimistic about defense strength.

For each attack path:
1. Identify deployed controls in path
2. Assess bypass difficulty (EASY/MODERATE/HARD/VERY_HARD)
3. Estimate required tools (public/custom)
4. Estimate required skill (script_kiddie/professional/apt)
5. Score difficulty (0-100, INVERTED)

Then calculate overall difficulty (average across paths).

## Exploit Mitigation Roadmap

After assessing current exploit difficulty, provide a **stepped roadmap** showing how to make this architecture harder to exploit.

**Guidelines:**
1. Provide 2-3 stepped targets (e.g., if current is 45, targets might be 30, 20, 10)
2. For each target, specify:
   - What controls would reduce exploit difficulty to this level?
   - How much harder for attacker? (new skill level, tools needed)
   - Is it practical? (YES/MAYBE/NO based on business impact)
   - What are the tradeoffs? (cost, user friction, operational overhead)

3. Mark realistic vs impractical:
   - **Practical (YES)**: Controls that enhance security without breaking business
   - **Questionable (MAYBE)**: High overhead but possible
   - **Impractical (NO)**: Would make system unusable or prohibitively expensive

**Example:**

Current: 45/100 (MEDIUM - Difficult to exploit)

**Target 30 (LOW - Very difficult):**
- Add: IDS/IPS for lateral movement detection, DLP for exfiltration, behavioral analysis
- Attacker impact: Forces use of custom malware, requires APT-level skills
- Practical: YES (standard security layers, moderate cost)
- Effort: 2-3 weeks, $50K-$100K

**Target 20 (MINIMAL - Nearly impossible):**
- Add: Zero-trust microsegmentation, deception technology, hardware MFA keys
- Attacker impact: Requires nation-state capabilities or insider access
- Practical: MAYBE (high operational overhead, user friction)
- Effort: 3-6 months, $200K-$500K

**Target 10 (IMPOSSIBLE):**
- Add: Air-gap systems, physical access controls, manual approvals for all transfers
- Attacker impact: Requires nation-state + insider + physical access
- Practical: NO (business would stop functioning)
- Effort: Not recommended

## Output Format

Provide your assessment in this JSON format:

```json
{{
  "score": <int 0-100>,
  "rating": "<MINIMAL/LOW/MEDIUM/HIGH/CRITICAL> = <easy/hard> to exploit = <GOOD/BAD> defense",
  "breakdown": {{
    "exploit_difficulty": <int 0-40>,
    "defense_evasion": <int 0-30>,
    "attack_path_realism": <int 0-30>
  }},
  "reasoning": "<1-2 sentences explaining the score>",
  "path_assessments": [
    {{
      "path_id": <int>,
      "path": "<description>",
      "difficulty": <int 0-100>,
      "key_controls": ["control1", "control2"],
      "bypass_difficulty": "<EASY/MODERATE/HARD/VERY_HARD>",
      "tools_needed": "<public/custom>",
      "skill_required": "<script_kiddie/professional/apt>"
    }}
  ],
  "gaps": [
    {{
      "severity": "<LOW/MEDIUM/HIGH/CRITICAL>",
      "description": "<what makes this exploitable>"
    }}
  ],
  "strengths": [
    "<what defenses are effective>"
  ],
  "exploit_mitigation_roadmap": [
    {{
      "target_score": <int>,
      "target_rating": "<MINIMAL/LOW/MEDIUM/HIGH/CRITICAL>",
      "difficulty_reduction": <int>,
      "requirements": ["control1", "control2"],
      "attacker_impact": "<how this affects attacker capability>",
      "practical": "<YES/MAYBE/NO>",
      "effort": "<time estimate>",
      "cost": "<cost estimate>",
      "tradeoffs": "<user friction, operational overhead, etc.>"
    }}
  ],
  "recommended_target": <int>
}}
```

**Important Notes:**
- Provide 2-3 stepped targets showing realistic → questionable → impractical
- Mark what's actually achievable vs theoretical
- Consider business impact (don't recommend air-gapping a web app!)
- Recommended target should be the highest practical improvement

REMEMBER: Low score = hard to exploit = GOOD defense (we want this!)
"""

    def critique(
        self,
        artifacts: ArtifactSet,
        ground_truth: Dict,
        tester_critique: Optional[CritiqueScore] = None
    ) -> CritiqueScore:
        """
        Execute Red Team critique with post-processing validation.

        Overrides parent critique() to add Red Team-specific logic:
        - Custom prompt building (attack paths, controls)
        - Post-processing validation (4 checks)
        - Tester gap integration

        Args:
            artifacts: Extracted artifacts from report
            ground_truth: Ground truth data (for controls_present)
            tester_critique: Optional Tester critique (for gap integration)

        Returns:
            CritiqueScore with exploit difficulty assessment (INVERTED)
        """
        logger.info(f"{self.role}: Starting critique")

        # Format prompt (Red Team specific)
        prompt = self._build_prompt(artifacts, ground_truth, tester_critique)

        # Call LLM (inherited from CriticAgent/BaseAgent via llm_client)
        logger.info(f"{self.role}: Calling LLM for exploit assessment")
        response = self.llm_client.generate(
            prompt=prompt,
            system_message=self.system_prompt,
            model=self.model,
            temperature=0.3,
            max_tokens=3000
        )

        # Parse response (uses parent _parse_llm_response via _parse_response_wrapper)
        raw_score = self._parse_response_wrapper(response)

        # POST-PROCESSING VALIDATION (4 checks) - Red Team specific
        logger.info(f"{self.role}: Starting post-processing validation")
        validated_score = self._validate_and_adjust(raw_score, ground_truth, tester_critique)

        logger.info(f"{self.role}: Critique complete - Score: {validated_score.score}/100 ({validated_score.rating})")
        return validated_score

    def _build_prompt(
        self,
        artifacts: ArtifactSet,
        ground_truth: Dict,
        tester_critique: Optional[CritiqueScore]
    ) -> str:
        """Build complete prompt for LLM."""

        # Extract attack paths
        paths = artifacts.tier1_critical['artifact_1_attack_paths']['paths']

        # Get deployed controls
        controls_present = ground_truth.get('controls_present', [])

        # Format deployed controls
        if controls_present:
            controls_text = ', '.join(controls_present)
        else:
            controls_text = "NONE - Architecture is completely vulnerable!"

        # Format attack paths
        paths_text = ""
        for i, path in enumerate(paths, 1):
            paths_text += f"\nPath #{i}: {' → '.join(path['path'])}\n"
            paths_text += f"  Techniques: {', '.join(path.get('techniques', [])[:5])}\n"
            paths_text += f"  Hop count: {len(path['path']) - 1}\n"

        # Format Tester validation (if available)
        tester_text = ""
        if tester_critique:
            critical_gaps = [g for g in tester_critique.gaps if 'CRITICAL' in str(g) or 'invalid' in str(g).lower()]
            if critical_gaps:
                tester_text = f"""
## Tester's Validation Findings

The Tester agent found {len(critical_gaps)} critical gaps in the ground truth:

"""
                for gap in critical_gaps[:5]:  # Top 5
                    tester_text += f"- {gap}\n"

                tester_text += """
**IMPORTANT:** Consider these gaps when assessing exploit difficulty.
- Invalid MITRE mappings = Control doesn't actually work as claimed
- Missing coverage = Unprotected techniques available for exploitation

If a control's MITRE mapping is invalid, the attacker can exploit that technique more easily.
Adjust your difficulty score accordingly (increase score = easier to exploit).
"""

        # Build final prompt
        prompt = self.prompt_template.format(
            deployed_controls=controls_text,
            attack_paths=paths_text,
            tester_validation=tester_text
        )

        return prompt

    def _parse_response_wrapper(self, response) -> CritiqueScore:
        """
        Parse LLM response into CritiqueScore.

        Uses parent's _parse_llm_response() for JSON extraction,
        then adds Red Team-specific fields.
        """
        # Use parent's JSON parsing (handles markdown blocks, etc.)
        data = self._parse_llm_response(response)

        if not data:
            # Return default score if parsing failed
            logger.warning(f"{self.role}: Using default score due to parse failure")
            return CritiqueScore(
                role=self.role,
                score=50,
                max_score=100,
                rating="UNKNOWN",
                breakdown={},
                gaps=[],
                strengths=[],
                improvement_roadmap=[]
            )

        # Build CritiqueScore with full data in breakdown
        breakdown = data.get("breakdown", {})

        # Add roadmap and path assessments to breakdown (Red Team specific)
        if "exploit_mitigation_roadmap" in data:
            breakdown["exploit_mitigation_roadmap"] = data["exploit_mitigation_roadmap"]
            breakdown["recommended_target"] = data.get("recommended_target")

        if "path_assessments" in data:
            breakdown["path_assessments"] = data["path_assessments"]

        if "reasoning" in data:
            breakdown["reasoning"] = data["reasoning"]

        score = CritiqueScore(
            role=self.role,
            score=data.get("score", 50),
            max_score=100,
            rating=data.get("rating", "UNKNOWN"),
            breakdown=breakdown,
            gaps=data.get("gaps", []),
            strengths=data.get("strengths", []),
            improvement_roadmap=[]  # Red Team uses exploit_mitigation_roadmap instead
        )

        return score

    # ========================================================================
    # POST-PROCESSING VALIDATION (4 checks)
    # ========================================================================

    def _validate_and_adjust(
        self,
        score: CritiqueScore,
        ground_truth: Dict,
        tester_critique: Optional[CritiqueScore]
    ) -> CritiqueScore:
        """
        Apply all validation checks.

        Checks:
        1. Control existence - no hallucinated controls
        2. Difficulty reasonableness - score matches control count
        3. Tester gap integration - adjust for invalid mappings
        4. Inverted scoring - auto-correct if forgotten
        """

        logger.info(f"{self.role}: Post-processing validation started")

        # Check 1: Control existence
        false_controls = self._validate_control_claims(score, ground_truth)
        if false_controls:
            logger.warning(f"{self.role}: Found {len(false_controls)} false control claims")
            score = self._remove_false_controls(score, false_controls)

        # Check 2: Difficulty reasonableness
        difficulty_check = self._validate_difficulty_score(score.score, ground_truth)
        if not difficulty_check.get("valid"):
            logger.warning(f"{self.role}: {difficulty_check['issue']}")
            old_score = score.score
            score.score = difficulty_check["suggested"]
            logger.info(f"{self.role}: Adjusted score {old_score} → {score.score}")

        # Check 3: Tester gap integration
        if tester_critique:
            old_score = score.score
            score.score = self._adjust_for_tester_gaps(score.score, tester_critique)
            if old_score != score.score:
                logger.info(f"{self.role}: Adjusted for Tester gaps {old_score} → {score.score}")

        # Check 4: Inverted scoring validation
        score = self._validate_inverted_scoring(score)

        logger.info(f"{self.role}: Post-processing complete - Final score: {score.score}/100")

        return score

    def _validate_control_claims(self, score: CritiqueScore, ground_truth: Dict) -> List[Dict]:
        """
        Check 1: Verify Red Team only mentions controls that actually exist.

        Returns: List of false positive control claims
        """
        controls_present = set(c.lower() for c in ground_truth.get("controls_present", []))

        false_positives = []

        # Check path assessments for claimed controls
        path_assessments = score.breakdown.get("path_assessments", [])
        for path in path_assessments:
            claimed = path.get("key_controls", [])
            for ctrl in claimed:
                if ctrl.lower() not in controls_present:
                    false_positives.append({
                        "path_id": path.get("path_id"),
                        "claimed_control": ctrl,
                        "issue": f"Control '{ctrl}' not in deployed controls"
                    })

        return false_positives

    def _remove_false_controls(self, score: CritiqueScore, false_controls: List[Dict]) -> CritiqueScore:
        """Remove false control claims from path assessments."""

        false_ctrl_names = set(fp["claimed_control"].lower() for fp in false_controls)

        # Update path assessments
        path_assessments = score.breakdown.get("path_assessments", [])
        for path in path_assessments:
            if "key_controls" in path:
                path["key_controls"] = [c for c in path["key_controls"]
                                       if c.lower() not in false_ctrl_names]

        return score

    def _validate_difficulty_score(self, score: int, ground_truth: Dict) -> Dict:
        """
        Check 2: Validate difficulty score makes sense given control count.

        Heuristic:
        - 0 controls: 80-90 (CRITICAL)
        - 1-2 controls: 65-80 (HIGH)
        - 3-5 controls: 45-65 (MEDIUM)
        - 6-10 controls: 25-45 (LOW)
        - 10+ controls: 10-25 (MINIMAL)
        """

        control_count = len(ground_truth.get("controls_present", []))

        # Calculate expected range
        if control_count == 0:
            expected_min, expected_max = 80, 90
        elif control_count <= 2:
            expected_min, expected_max = 65, 80
        elif control_count <= 5:
            expected_min, expected_max = 45, 65
        elif control_count <= 10:
            expected_min, expected_max = 25, 45
        else:
            expected_min, expected_max = 10, 25

        # Check if score is way off (>20 points outside range)
        if score < expected_min - 20:
            return {
                "valid": False,
                "issue": f"Score {score} too optimistic (rated too hard to exploit)",
                "expected_range": (expected_min, expected_max),
                "suggested": expected_min,
                "severity": "MEDIUM"
            }
        elif score > expected_max + 20:
            return {
                "valid": False,
                "issue": f"Score {score} too pessimistic (rated too easy to exploit)",
                "expected_range": (expected_min, expected_max),
                "suggested": expected_max,
                "severity": "MEDIUM"
            }
        else:
            return {"valid": True}

    def _adjust_for_tester_gaps(self, score: int, tester_critique: CritiqueScore) -> int:
        """
        Check 3: Increase exploit difficulty if Tester found critical gaps.

        Logic:
        - Tester found invalid MITRE mappings
        - Control claims to mitigate technique but mapping invalid
        - Technique is actually NOT mitigated
        - Attacker can exploit technique freely
        - → Increase exploit score (easier to attack)
        """

        critical_gaps = len([g for g in tester_critique.gaps
                            if 'CRITICAL' in str(g) or 'invalid' in str(g).lower()])

        if critical_gaps == 0:
            return score

        # Each critical gap makes exploit easier (+5 points per gap)
        adjustment = critical_gaps * 5

        adjusted_score = min(100, score + adjustment)

        logger.info(f"{self.role}: Adjusted for {critical_gaps} critical gaps (+{adjustment} points)")

        return adjusted_score

    def _validate_inverted_scoring(self, score: CritiqueScore) -> CritiqueScore:
        """
        Check 4: Ensure LLM understood inverted scoring.

        Common mistake: LLM forgets inversion
        - Rates strong defense as 90/100 (thinking high = good)
        - Should be 30/100 (low = good in inverted scale)

        Detection:
        - Rating says "GOOD defense" but score is >60
        - Rating says "BAD defense" but score is <40
        """

        rating = score.rating.lower()
        actual_score = score.score

        # Check for contradiction (good defense + high score)
        if ("good" in rating or "strong" in rating or "hard" in rating or "excellent" in rating) and actual_score > 60:
            logger.warning(f"{self.role}: Inverted scoring error - "
                          f"Rating says 'good defense' but score is {actual_score}/100")

            # Invert the score
            corrected_score = 100 - actual_score
            score.score = corrected_score

            logger.info(f"{self.role}: Corrected score {actual_score} → {corrected_score} (inverted)")

        # Check for contradiction (bad defense + low score)
        elif ("bad" in rating or "weak" in rating or "easy" in rating or "trivial" in rating) and actual_score < 40:
            logger.warning(f"{self.role}: Inverted scoring error - "
                          f"Rating says 'bad defense' but score is {actual_score}/100")

            # Invert the score
            corrected_score = 100 - actual_score
            score.score = corrected_score

            logger.info(f"{self.role}: Corrected score {actual_score} → {corrected_score} (inverted)")

        return score


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def critique_red_team(
    report_dir: str,
    tester_critique_path: Optional[str] = None
) -> CritiqueScore:
    """
    Convenience function to run Red Team critique on a report directory.

    Args:
        report_dir: Path to report directory
        tester_critique_path: Optional path to Tester critique JSON

    Returns:
        CritiqueScore with Red Team assessment
    """
    from chatbot.modules.artifact_extractor import extract_artifacts

    # Load ground truth
    gt_path = Path(report_dir) / "ground_truth.json"
    with open(gt_path) as f:
        ground_truth = json.load(f)

    # Extract artifacts
    artifacts = extract_artifacts(report_dir)

    # Load Tester critique if provided
    tester_critique = None
    if tester_critique_path:
        with open(tester_critique_path) as f:
            tester_data = json.load(f)
            # Convert to CritiqueScore (simplified)
            tester_critique = CritiqueScore(
                role="Tester",
                score=tester_data.get("score", 0),
                max_score=100,
                rating=tester_data.get("rating", "UNKNOWN"),
                breakdown=tester_data.get("breakdown", {}),
                gaps=tester_data.get("gaps", []),
                strengths=tester_data.get("strengths", []),
                improvement_roadmap=[]
            )

    # Run critique
    critic = RedTeamerCritic()
    return critic.critique(artifacts, ground_truth, tester_critique)
