"""
MoE (Mixture of Experts) Orchestrator for Phase 3D

Architecture:
    Layer 1: Deterministic Expert (Source of Truth)
        └─> ground_truth.json (99.5% confidence)

    Layer 2: Sequential Expert Chain (LLM Validation)
        └─> 2A: Architect validates threat model
        └─> 2B: Tester validates MITRE + Architect
        └─> 2C: Red Team validates controls + Tester

    Layer 3: Orchestrator (Consensus & Coherence)
        └─> 00_executive_dashboard.md (unified report)

Key Principles:
1. FAIL FAST: Missing prerequisite = abort (quality over quantity)
2. SEQUENTIAL: Each expert requires previous outputs
3. VALIDATION ONLY: LLM experts adjust confidence, not parallel recommendations
4. SINGLE SCORING: Base 99.5% ± adjustments (not composite scores)
5. CONSENSUS: Unified recommendations only

Version: 1.0 (Phase 3D foundation)
Date: 2025-05-17
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from chatbot.modules.agents.critics.architect_critic import EnhancedArchitectCritic
from chatbot.modules.agents.critics.tester_critic import TesterCritic
from chatbot.modules.agents.critics.red_teamer_critic import RedTeamerCritic
from chatbot.modules.artifact_extractor import extract_artifacts, ArtifactSet
from chatbot.modules.agent_framework import CritiqueScore
from agentic.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Orchestrator system prompt — defines the synthesis role precisely
# ---------------------------------------------------------------------------
_ORCHESTRATOR_SYSTEM = """You are the Layer 3 Orchestrator in a Mixture-of-Experts security assessment pipeline.

Your role is SYNTHESIS, not generation. Three expert agents have already reviewed a deterministic threat assessment:
- Architect (2A): assessed design quality and threat model completeness
- Tester (2B):    validated MITRE technique mappings and internal consistency
- Red Team (2C):  assessed exploit difficulty and control bypass feasibility

Your job is to produce a balanced, grounded final view that the human decision-maker can act on.

Rules you must follow:
1. CITE YOUR EVIDENCE — every finding must reference which critic raised it or which field in ground_truth supports it.
2. DISTINGUISH KNOWN vs UNSURE — if only one critic raised a finding, mark it UNSURE. If all three agree, mark it KNOWN.
3. NEVER INVENT COSTS — use the Red Team's exploit_mitigation_roadmap cost/effort fields verbatim. If no cost data exists, say "cost not estimated".
4. CALL OUT CONTRADICTIONS — where critics disagree, surface the contradiction rather than picking a side.
5. CALL OUT BLINDSPOTS — identify what ALL THREE critics structurally could not see (e.g. a whole threat category with zero controls).
6. ROI BALANCE — Quick Win = highest security gain per unit effort, lowest user friction. Recommended = balanced security/usability/cost. Max = full coverage including diminishing-return items.
7. RESIDUAL IS REAL — never claim a tier eliminates risk. State what residual remains and why (misconfiguration, human error, zero-days, implementation drift).
"""


# ============================================================================
# EXCEPTIONS
# ============================================================================

class MissingPrerequisiteError(Exception):
    """Raised when required input file is missing (fail-fast)."""
    def __init__(self, missing_file: str, layer: str):
        self.missing_file = missing_file
        self.layer = layer
        message = (
            f"MoE Pipeline ABORTED at {layer}\n"
            f"Missing prerequisite: {missing_file}\n\n"
            f"Quality depends on prior analysis - cannot proceed with missing data.\n"
            f"Run deterministic analysis first: python3 -m chatbot.main --gen-arch-truth <architecture.mmd>"
        )
        super().__init__(message)


# ============================================================================
# RESULT STRUCTURES
# ============================================================================

@dataclass
class ValidationResult:
    """Result from a single validation expert."""
    expert_name: str
    validation_status: str  # PASS, MINOR_GAPS, MAJOR_GAPS
    confidence_adjustment: float  # -0.0 to -0.25 (percentage)
    gaps: List[Dict]
    strengths: List[str]
    recommendations: List[Dict]
    original_score: int  # Original expert score (for reference)
    breakdown: Dict = None  # Sub-dimension scores (for UI display)

    def __post_init__(self):
        if self.breakdown is None:
            self.breakdown = {}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class MoEResult:
    """Result from full MoE pipeline."""
    # Architecture
    architecture_name: str

    # Confidence progression
    base_confidence: float  # 99.5% from deterministic
    architect_adjustment: float
    tester_adjustment: float
    red_team_adjustment: float
    final_confidence: float

    # Expert results
    architect_result: ValidationResult
    tester_result: ValidationResult
    red_team_result: ValidationResult

    # Consensus recommendations — produced by LLM synthesis
    critical_recommendations: List[Dict]  # ≥2 critics agree (KNOWN)
    high_recommendations: List[Dict]      # 1 critic + corroborated (UNSURE)
    review_recommendations: List[Dict]    # 1 critic only (UNSURE)

    # Synthesis extras
    blindspots: List[Dict] = None         # Gaps all three critics structurally missed
    contradictions: List[Dict] = None     # Where critics disagree — human must decide
    synthesis_quality: str = "UNKNOWN"    # FULL | FALLBACK

    # Risk transformation (from deterministic)
    current_risk: int = 0
    target_risk: int = 0
    risk_reduction: int = 0

    # Improvement options (sourced from Red Team roadmap, not hardcoded)
    quick_wins: Dict = None
    recommended: Dict = None
    maximum: Dict = None

    def __post_init__(self):
        if self.blindspots is None:
            self.blindspots = []
        if self.contradictions is None:
            self.contradictions = []
        if self.quick_wins is None:
            self.quick_wins = {}
        if self.recommended is None:
            self.recommended = {}
        if self.maximum is None:
            self.maximum = {}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "architecture": self.architecture_name,
            "confidence": {
                "base": self.base_confidence,
                "adjustments": {
                    "architect": self.architect_adjustment,
                    "tester": self.tester_adjustment,
                    "red_team": self.red_team_adjustment
                },
                "final": self.final_confidence,
                "interpretation": self._interpret_confidence()
            },
            "expert_validations": {
                "architect": self.architect_result.to_dict(),
                "tester": self.tester_result.to_dict(),
                "red_team": self.red_team_result.to_dict()
            },
            "consensus_recommendations": {
                "critical": self.critical_recommendations,
                "high": self.high_recommendations,
                "review": self.review_recommendations,
                "blindspots": self.blindspots,
                "contradictions": self.contradictions,
                "synthesis_quality": self.synthesis_quality,
            },
            "risk_transformation": {
                "current": self.current_risk,
                "target": self.target_risk,
                "reduction_percent": self.risk_reduction
            },
            "improvement_options": {
                "quick_wins": self.quick_wins,
                "recommended": self.recommended,
                "maximum": self.maximum
            }
        }

    def _interpret_confidence(self) -> str:
        """Interpret final confidence score."""
        if self.final_confidence >= 95:
            return "EXCEPTIONAL - High confidence in analysis"
        elif self.final_confidence >= 90:
            return "EXCELLENT - Minor validation gaps"
        elif self.final_confidence >= 85:
            return "GOOD - Some gaps, recommendations valid"
        elif self.final_confidence >= 80:
            return "ACCEPTABLE - Several gaps, review recommended"
        else:
            return "NEEDS REVIEW - Significant gaps found"


# ============================================================================
# MOE ORCHESTRATOR
# ============================================================================

class MoEOrchestrator:
    """
    Mixture of Experts orchestrator with fail-fast sequential validation.

    Philosophy:
    - Deterministic analysis is SOURCE OF TRUTH (what to do)
    - LLM experts are VALIDATORS (how confident we are)
    - Orchestrator is PRESENTER (how to communicate)

    Never allows LLM to override deterministic recommendations.
    """

    def __init__(self, model: Optional[str] = None):
        """
        Initialize MoE orchestrator.

        Args:
            model: Optional model override for LLM experts
        """
        self.model = model

        # Create expert agents
        self.architect = EnhancedArchitectCritic(model=model)
        self.tester = TesterCritic(model=model)
        self.red_team = RedTeamerCritic(model=model)

        logger.info("MoEOrchestrator initialized with 3 validation experts")

    def run_pipeline(
        self,
        report_dir: str,
        base_confidence: float = 99.5
    ) -> MoEResult:
        """
        Execute full MoE pipeline with fail-fast validation.

        Pipeline:
        1. Layer 1: Check deterministic analysis exists (ground_truth.json)
        2. Layer 2A: Architect validates threat model
        3. Layer 2B: Tester validates MITRE + Architect
        4. Layer 2C: Red Team validates controls + Tester
        5. Layer 3: Orchestrator synthesizes consensus

        Args:
            report_dir: Path to report directory
            base_confidence: Base confidence from deterministic (default: 99.5%)

        Returns:
            MoEResult with unified assessment

        Raises:
            MissingPrerequisiteError: If any prerequisite file missing
        """
        report_path = Path(report_dir)
        architecture_name = report_path.name

        logger.info(f"MoE Pipeline: Starting for {architecture_name}")
        logger.info(f"MoE Pipeline: Base confidence = {base_confidence}%")

        # ===== LAYER 1: DETERMINISTIC (REQUIRED) =====
        logger.info("MoE Pipeline: Layer 1 - Checking deterministic analysis...")
        gt_path = report_path / "ground_truth.json"

        if not gt_path.exists():
            raise MissingPrerequisiteError(
                missing_file=str(gt_path),
                layer="Layer 1 (Deterministic)"
            )

        with open(gt_path) as f:
            ground_truth = json.load(f)

        logger.info(f"MoE Pipeline: ✓ Layer 1 complete - ground_truth.json found")

        # Extract artifacts for experts
        artifacts = extract_artifacts(report_dir)
        logger.info(f"MoE Pipeline: Extracted {artifacts.completeness['overall']['present']}/10 artifacts")

        # ===== LAYER 2A: ARCHITECT VALIDATION (REQUIRED) =====
        logger.info("MoE Pipeline: Layer 2A - Running Architect validation...")

        architect_critique = self.architect.critique(artifacts)
        architect_result = self._process_architect_validation(architect_critique)

        # Save immediately (fail-fast principle)
        arch_path = report_path / "04_architect_critique.json"
        self._save_validation(architect_critique, arch_path)

        logger.info(f"MoE Pipeline: ✓ Layer 2A complete - {architect_result.validation_status}")
        logger.info(f"MoE Pipeline:   Confidence adjustment: {architect_result.confidence_adjustment*100:.1f}%")

        # ===== LAYER 2B: TESTER VALIDATION (REQUIRED) =====
        logger.info("MoE Pipeline: Layer 2B - Running Tester validation...")

        # Check prerequisite
        if not arch_path.exists():
            raise MissingPrerequisiteError(
                missing_file=str(arch_path),
                layer="Layer 2B (Tester)"
            )

        tester_critique = self.tester.critique(artifacts, architect_critique)
        tester_result = self._process_tester_validation(tester_critique)

        # Save immediately
        test_path = report_path / "05_tester_critique.json"
        self._save_validation(tester_critique, test_path)

        logger.info(f"MoE Pipeline: ✓ Layer 2B complete - {tester_result.validation_status}")
        logger.info(f"MoE Pipeline:   Confidence adjustment: {tester_result.confidence_adjustment*100:.1f}%")

        # ===== LAYER 2C: RED TEAM VALIDATION (REQUIRED) =====
        logger.info("MoE Pipeline: Layer 2C - Running Red Team validation...")

        # Check prerequisites
        if not test_path.exists():
            raise MissingPrerequisiteError(
                missing_file=str(test_path),
                layer="Layer 2C (Red Team)"
            )

        red_team_critique = self.red_team.critique(artifacts, ground_truth, tester_critique)
        red_team_result = self._process_red_team_validation(red_team_critique)

        # Save immediately
        red_path = report_path / "06_red_team_critique.json"
        self._save_validation(red_team_critique, red_path)

        logger.info(f"MoE Pipeline: ✓ Layer 2C complete - {red_team_result.validation_status}")
        logger.info(f"MoE Pipeline:   Confidence adjustment: {red_team_result.confidence_adjustment*100:.1f}%")

        # ===== LAYER 3: CONSENSUS SYNTHESIS =====
        logger.info("MoE Pipeline: Layer 3 - Synthesizing consensus...")

        # Calculate final confidence
        final_confidence = self._calculate_final_confidence(
            base_confidence,
            architect_result,
            tester_result,
            red_team_result
        )

        logger.info(f"MoE Pipeline: Final confidence = {final_confidence:.1f}%")

        # Synthesize consensus recommendations (LLM call — passes raw CritiqueScore
        # objects so the synthesiser can read Red Team's exploit_mitigation_roadmap)
        consensus = self._synthesize_consensus(
            ground_truth,
            architect_result,
            tester_result,
            red_team_result,
            architect_raw=architect_critique,
            tester_raw=tester_critique,
            red_team_raw=red_team_critique,
        )

        # Extract risk transformation from ground truth
        risk_data = self._extract_risk_transformation(ground_truth)

        # Build improvement options
        improvement_options = self._build_improvement_options(
            consensus,
            risk_data
        )

        # Build final result
        result = MoEResult(
            architecture_name=architecture_name,
            base_confidence=base_confidence,
            architect_adjustment=architect_result.confidence_adjustment,
            tester_adjustment=tester_result.confidence_adjustment,
            red_team_adjustment=red_team_result.confidence_adjustment,
            final_confidence=final_confidence,
            architect_result=architect_result,
            tester_result=tester_result,
            red_team_result=red_team_result,
            critical_recommendations=consensus["critical"],
            high_recommendations=consensus["high"],
            review_recommendations=consensus["review"],
            blindspots=consensus.get("blindspots", []),
            contradictions=consensus.get("contradictions", []),
            synthesis_quality=consensus.get("synthesis_quality", "UNKNOWN"),
            current_risk=risk_data["current"],
            target_risk=risk_data["target"],
            risk_reduction=risk_data["reduction"],
            quick_wins=improvement_options["quick_wins"],
            recommended=improvement_options["recommended"],
            maximum=improvement_options["maximum"]
        )

        # Save orchestrator result (MoE format)
        orch_path = report_path / "07_moe_orchestrator.json"
        with open(orch_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        # Also save as legacy format for backward compatibility with improvement generators
        legacy_path = report_path / "07_orchestrator_report.json"
        with open(legacy_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"MoE Pipeline: ✓ Layer 3 complete - saved to {orch_path} (+ legacy format)")

        # ===== GENERATE ADDITIONAL ARTIFACTS (Phase 3D Week 3) =====
        logger.info("MoE Pipeline: Generating CISO artifacts...")

        # Generate executive dashboard (00_executive_dashboard.md) - NEW in Week 3
        try:
            from chatbot.modules.executive_dashboard_generator import generate_executive_dashboard
            dashboard_file = generate_executive_dashboard(report_dir)
            logger.info(f"MoE Pipeline: ✓ Generated executive dashboard: {dashboard_file}")
        except Exception as e:
            logger.warning(f"MoE Pipeline: Failed to generate executive dashboard: {e}")

        # Generate improvement summary (08_improvement_summary.md)
        try:
            from chatbot.modules.improvement_summary_generator import generate_summary
            summary_file = generate_summary(report_dir, orchestrator_result=None)
            logger.info(f"MoE Pipeline: ✓ Generated improvement summary: {summary_file}")
        except Exception as e:
            logger.warning(f"MoE Pipeline: Failed to generate improvement summary: {e}")

        # Generate stepped improvement MMDs (08a/08b/08c.mmd)
        try:
            from chatbot.modules.mmd_improvement_generator import generate_improvement_mmds
            mmd_files = generate_improvement_mmds(report_dir, orchestrator_result=None)
            logger.info(f"MoE Pipeline: ✓ Generated {len(mmd_files)} stepped improvement diagrams")
        except Exception as e:
            logger.warning(f"MoE Pipeline: Failed to generate improvement MMDs: {e}")

        logger.info(f"MoE Pipeline: COMPLETE - {final_confidence:.1f}% confidence")
        logger.info(f"MoE Pipeline: Generated 16/16 files (ground_truth + 1 dashboard + 6 JSON + 4 MD + 4 MMD)")

        return result

    def _process_architect_validation(self, critique: CritiqueScore) -> ValidationResult:
        """
        Process Architect critique into validation result.

        Architect validates:
        - Threat model completeness
        - Control appropriateness
        - Defense-in-depth coverage
        - RAPIDS alignment
        """
        # Determine validation status
        if critique.score >= 90:
            status = "PASS"
            adjustment = 0.0
        elif critique.score >= 80:
            status = "MINOR_GAPS"
            adjustment = -0.02  # -2%
        elif critique.score >= 70:
            status = "MINOR_GAPS"
            adjustment = -0.05  # -5%
        else:
            status = "MAJOR_GAPS"
            adjustment = -0.10  # -10%

        # Extract actionable recommendations (not new controls)
        recommendations = []
        for item in critique.improvement_roadmap:
            recommendations.append({
                "priority": item.get("priority", 5),
                "action": item.get("action", "Unknown"),
                "category": item.get("category", "unknown"),
                "verification": item.get("verification_method", "Manual review")
            })

        return ValidationResult(
            expert_name="Architect",
            validation_status=status,
            confidence_adjustment=adjustment,
            gaps=critique.gaps,
            strengths=critique.strengths,
            recommendations=recommendations,
            original_score=critique.score
        )

    def _process_tester_validation(self, critique: CritiqueScore) -> ValidationResult:
        """
        Process Tester critique into validation result.

        Tester validates:
        - MITRE mappings correct
        - Internal consistency
        - Coverage metrics
        - Architect's recommendations valid
        """
        # Count CRITICAL/HIGH gaps — used to override PASS when serious gaps exist
        critical_gaps = len([g for g in critique.gaps if g.get("severity") in ["CRITICAL", "HIGH"]])

        # Penalty for sub-dimensions that critically fail (<50% of their max score)
        # e.g. roadmap_validation: 1/10 = 10% — flags structural weakness missed by aggregate score
        sub_penalty = 0.0
        raw_breakdown = critique.breakdown if isinstance(critique.breakdown, dict) else {}
        for sub_key, sub_data in raw_breakdown.items():
            if isinstance(sub_data, dict):
                sub_score = sub_data.get("score", 0)
                sub_max = sub_data.get("max", 0)
                if sub_max > 0 and (sub_score / sub_max) < 0.50:
                    sub_penalty -= 0.02  # -2% per critically failed sub-dimension
                    logger.info(
                        f"Tester: sub-dimension '{sub_key}' critically low "
                        f"({sub_score}/{sub_max} = {sub_score/sub_max*100:.0f}%) → -2% penalty"
                    )

        if critique.score >= 85:
            status = "PASS"
            adjustment = 0.0
        elif critique.score >= 75:
            status = "MINOR_GAPS"
            adjustment = -0.01  # -1%
        elif critique.score >= 65:
            status = "MINOR_GAPS"
            adjustment = -0.03  # -3%
        else:
            status = "MAJOR_GAPS"
            adjustment = -0.05  # -5%

        # Override: PASS is not valid when HIGH/CRITICAL gaps exist
        if status == "PASS" and critical_gaps > 0:
            status = "MINOR_GAPS"
            adjustment = -0.01

        # Apply sub-dimension penalty
        if sub_penalty < 0:
            adjustment += sub_penalty
            if adjustment <= -0.05:
                status = "MAJOR_GAPS"
            elif adjustment < 0 and status == "PASS":
                status = "MINOR_GAPS"

        # Extract recommendations
        recommendations = []
        for item in critique.improvement_roadmap:
            recommendations.append({
                "priority": item.get("priority", 5),
                "action": item.get("action", "Unknown"),
                "category": item.get("category", "unknown"),
                "verification": item.get("verification_method", "Manual review")
            })

        return ValidationResult(
            expert_name="Tester",
            validation_status=status,
            confidence_adjustment=adjustment,
            gaps=critique.gaps,
            strengths=critique.strengths,
            recommendations=recommendations,
            original_score=critique.score,
            breakdown=raw_breakdown,
        )

    def _process_red_team_validation(self, critique: CritiqueScore) -> ValidationResult:
        """
        Process Red Team critique into validation result.

        Red Team validates:
        - Control effectiveness (would they actually stop attacks?)
        - Bypass scenarios
        - Tester's assessment correct
        """
        # Red Team is INVERTED: low score = hard to exploit = good
        # So high score (easy to exploit) = major gaps

        if critique.score <= 40:  # Hard to exploit
            status = "PASS"
            adjustment = 0.0
        elif critique.score <= 55:  # Moderate difficulty
            status = "MINOR_GAPS"
            adjustment = -0.03  # -3%
        elif critique.score <= 70:  # Somewhat easy
            status = "MINOR_GAPS"
            adjustment = -0.06  # -6%
        else:  # Easy to exploit
            status = "MAJOR_GAPS"
            adjustment = -0.10  # -10%

        # Extract recommendations (bypass scenarios)
        recommendations = []
        roadmap = critique.breakdown.get("exploit_mitigation_roadmap", [])
        for item in roadmap:
            if item.get("practical") == "YES":
                recommendations.append({
                    "priority": 1 if item.get("target_score", 100) < 40 else 2,
                    "action": f"Reduce exploit difficulty to {item.get('target_score')}/100",
                    "category": "control_effectiveness",
                    "verification": "Red Team penetration test"
                })

        return ValidationResult(
            expert_name="Red Team",
            validation_status=status,
            confidence_adjustment=adjustment,
            gaps=critique.gaps,
            strengths=critique.strengths,
            recommendations=recommendations,
            original_score=critique.score
        )

    def _calculate_final_confidence(
        self,
        base: float,
        architect: ValidationResult,
        tester: ValidationResult,
        red_team: ValidationResult
    ) -> float:
        """
        Calculate final confidence with adjustments.

        Formula: Base × (1 + architect_adj) × (1 + tester_adj) × (1 + red_team_adj)

        Capped at 100%, floored at 50%.
        """
        final = base
        final = final * (1 + architect.confidence_adjustment)
        final = final * (1 + tester.confidence_adjustment)
        final = final * (1 + red_team.confidence_adjustment)

        # Cap and floor
        final = max(50.0, min(100.0, final))

        return final

    def _synthesize_consensus(
        self,
        ground_truth: Dict,
        architect: ValidationResult,
        tester: ValidationResult,
        red_team: ValidationResult,
        architect_raw: Optional[CritiqueScore] = None,
        tester_raw: Optional[CritiqueScore] = None,
        red_team_raw: Optional[CritiqueScore] = None,
    ) -> Dict:
        """
        LLM synthesis: cross-validate all three critic outputs and produce grounded
        consensus with KNOWN/UNSURE distinction, ROI-tiered improvement options,
        real costs from Red Team data, and explicit residual risk per tier.

        Falls back to simple gap-union if the LLM call fails.
        """
        synthesis = self._llm_synthesize(
            ground_truth, architect, tester, red_team,
            architect_raw, tester_raw, red_team_raw
        )
        if synthesis:
            # Second pass: self-reflect on any contradictions found
            if synthesis.get("contradictions"):
                synthesis["contradictions"] = self._reflect_contradictions(
                    synthesis["contradictions"],
                    architect, tester, red_team
                )
            return synthesis

        # ---- fallback: union of all gaps, no consensus scoring ----
        logger.warning("Orchestrator: LLM synthesis failed — using gap-union fallback")
        all_gaps = architect.gaps + tester.gaps + red_team.gaps
        seen, deduped = set(), []
        for g in all_gaps:
            key = g.get("description", "")[:80]
            if key not in seen:
                seen.add(key)
                deduped.append({
                    "description": g.get("description", ""),
                    "category": g.get("category", ""),
                    "severity": g.get("severity", "MEDIUM"),
                    "source": "fallback-union",
                    "confidence_label": "UNSURE",
                })
        return {
            "critical": [],
            "high": deduped[:5],
            "review": deduped[5:],
            "blindspots": [],
            "contradictions": [],
            "improvement_tiers": {},
            "synthesis_quality": "FALLBACK",
        }

    def _llm_synthesize(
        self,
        ground_truth: Dict,
        architect: ValidationResult,
        tester: ValidationResult,
        red_team: ValidationResult,
        architect_raw: Optional[CritiqueScore],
        tester_raw: Optional[CritiqueScore],
        red_team_raw: Optional[CritiqueScore],
    ) -> Optional[Dict]:
        """
        Single LLM call that reads all three critic outputs and produces the
        structured synthesis JSON.  Returns None on any failure so the caller
        can fall back gracefully.
        """
        try:
            # ---- build the prompt ----
            arch_name = ground_truth.get("architecture", "unknown")

            # Risk numbers from ground truth
            rt = self._extract_risk_transformation(ground_truth)
            risk_summary = (
                f"Current risk score: {rt['current']}/100  |  "
                f"Target after all controls: {rt['target']}/100  |  "
                f"Estimated reduction: {rt['reduction']}%"
            )

            # Red Team exploit-mitigation roadmap (the only place real costs live)
            rt_roadmap = []
            if red_team_raw and hasattr(red_team_raw, 'breakdown'):
                rt_roadmap = red_team_raw.breakdown.get("exploit_mitigation_roadmap", [])
            rt_roadmap_json = json.dumps(rt_roadmap, indent=2) if rt_roadmap else "[]"

            # Serialize critic outputs compactly
            def _gap_list(v: ValidationResult) -> str:
                return json.dumps(v.gaps, indent=2) if v.gaps else "[]"

            def _roadmap(v: ValidationResult) -> str:
                return json.dumps(v.recommendations, indent=2) if v.recommendations else "[]"

            prompt = f"""
You are synthesising a security assessment for architecture: "{arch_name}"

{risk_summary}

═══════════════════════════════════════════════════════════
ARCHITECT CRITIC OUTPUT  (Layer 2A)
Score: {architect.original_score}/100  |  Status: {architect.validation_status}
Gaps:
{_gap_list(architect)}
Recommendations:
{_roadmap(architect)}

═══════════════════════════════════════════════════════════
TESTER CRITIC OUTPUT  (Layer 2B)
Score: {tester.original_score}/100  |  Status: {tester.validation_status}
Gaps:
{_gap_list(tester)}
Recommendations:
{_roadmap(tester)}

═══════════════════════════════════════════════════════════
RED TEAM CRITIC OUTPUT  (Layer 2C)
Score: {red_team.original_score}/100  |  Status: {red_team.validation_status}
Gaps (exploit feasibility):
{_gap_list(red_team)}
Exploit Mitigation Roadmap (use these cost/effort fields verbatim — do not invent):
{rt_roadmap_json}

═══════════════════════════════════════════════════════════
YOUR SYNTHESIS TASK

Produce a JSON object with EXACTLY this structure:

```json
{{
  "critical": [
    {{
      "description": "...",
      "category": "...",
      "severity": "CRITICAL|HIGH",
      "source": "which critics raised this (e.g. architect+tester)",
      "confidence_label": "KNOWN",
      "evidence": "cite the specific gap/field that supports this"
    }}
  ],
  "high": [ /* same shape, confidence_label KNOWN or UNSURE */ ],
  "review": [ /* same shape, confidence_label UNSURE — single-critic findings */ ],
  "blindspots": [
    {{
      "description": "gap that ALL THREE critics structurally missed",
      "why_missed": "reason (e.g. rubric scope, single-lens focus)",
      "recommendation": "what the human should investigate"
    }}
  ],
  "contradictions": [
    {{
      "topic": "...",
      "architect_view": "...",
      "tester_or_redteam_view": "...",
      "resolution": "UNSURE — human review needed"
    }}
  ],
  "improvement_tiers": {{
    "quick_win": {{
      "rationale": "highest security gain per unit effort, lowest user friction",
      "items": ["..."],
      "effort": "use Red Team roadmap effort field verbatim, or state 'not estimated'",
      "cost": "use Red Team roadmap cost field verbatim, or state 'cost not estimated'",
      "risk_reduction": "estimated score change (e.g. {rt['current']} → X)",
      "residual": "what risk remains even after Quick Win — be honest",
      "practical_verdict": "YES|MAYBE based on Red Team practical field"
    }},
    "recommended": {{
      "rationale": "balanced security / usability / cost — realistic for most teams",
      "items": ["..."],
      "effort": "...",
      "cost": "...",
      "risk_reduction": "...",
      "residual": "...",
      "practical_verdict": "..."
    }},
    "maximum": {{
      "rationale": "full coverage including diminishing-return items",
      "items": ["..."],
      "effort": "...",
      "cost": "...",
      "risk_reduction": "...",
      "residual": "residual that persists regardless (misconfiguration, human error, zero-days, implementation drift) — never claim zero",
      "practical_verdict": "MAYBE|NO for most teams — explain tradeoff"
    }}
  }},
  "confidence_commentary": "1-2 sentences: what the cross-expert agreement pattern means for confidence in this assessment",
  "synthesis_quality": "FULL"
}}
```

RULES:
- critical = findings ≥2 critics independently raised (mark KNOWN)
- high = single-critic findings that Red Team exploit data corroborates (mark UNSURE if not corroborated)
- review = single-critic, not corroborated elsewhere (mark UNSURE)
- Never invent cost figures. Quote Red Team roadmap fields exactly or say "cost not estimated".
- Residual must always be non-empty — controls reduce risk, they do not eliminate it.
- If critics contradict each other, put it in contradictions, do NOT resolve it yourself.
"""

            llm = LLMClient()
            response = llm.generate(
                prompt=prompt.strip(),
                system_message=_ORCHESTRATOR_SYSTEM,
                temperature=0.2,   # low — we want consistent structured output
                max_tokens=4000,
            )

            # Parse JSON from response
            content = response.content if hasattr(response, 'content') else str(response)
            if '```json' in content:
                raw = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content and '{' in content:
                raw = content.split('```')[1].split('```')[0].strip()
            else:
                raw = content.strip()

            result = json.loads(raw)

            # Minimal validation
            required = ["critical", "high", "review", "improvement_tiers"]
            if not all(k in result for k in required):
                logger.warning("Orchestrator: LLM synthesis response missing required keys")
                return None

            logger.info(
                f"Orchestrator: LLM synthesis complete — "
                f"{len(result.get('critical',[]))} critical, "
                f"{len(result.get('high',[]))} high, "
                f"{len(result.get('review',[]))} review, "
                f"{len(result.get('blindspots',[]))} blindspots"
            )
            return result

        except Exception as e:
            logger.warning(f"Orchestrator: LLM synthesis exception: {e}")
            return None

    def _reflect_contradictions(
        self,
        contradictions: List[Dict],
        architect: "ValidationResult",
        tester: "ValidationResult",
        red_team: "ValidationResult",
    ) -> List[Dict]:
        """
        Second-pass LLM call: for each contradiction, ask WHY the critics disagree.
        Possible causes: different scope, stale data reference, JSON field mismatch,
        assessment incomplete.  Returns the enriched contradiction list; falls back
        to the original list if the call fails.
        """
        try:
            items_json = json.dumps(contradictions, indent=2)
            prompt = f"""You are a quality-control reviewer for a multi-expert security assessment.

The three expert critics disagreed on the following topics:

{items_json}

For each contradiction, diagnose WHY the disagreement exists.  Consider:
1. Scope mismatch — each critic only sees their rubric, so one may be correct within their scope and the other correct within theirs
2. JSON/data reference error — one critic may have read a stale field or misidentified a control
3. Assessment confidence — one critic may have guessed while the other had direct evidence
4. Genuine expert disagreement — both are right from different attack angles

Return a JSON array with the SAME length and order as the input, each item having:
{{
  "topic": "<same as input>",
  "architect_view": "<same as input>",
  "tester_or_redteam_view": "<same as input>",
  "resolution": "<original resolution>",
  "disagreement_root_cause": "SCOPE_MISMATCH | DATA_REFERENCE_ERROR | CONFIDENCE_DIFFERENCE | GENUINE_DISAGREEMENT",
  "root_cause_explanation": "1-2 sentences explaining specifically why these critics see it differently",
  "human_action": "what a human reviewer should do to resolve this (e.g. check field X, run test Y)"
}}

Reply with only the JSON array, no other text.
"""
            llm = LLMClient()
            response = llm.generate(
                prompt=prompt.strip(),
                system_message="You are a rigorous security assessment quality reviewer. Return only valid JSON.",
                temperature=0.1,
                max_tokens=2000,
            )
            content = response.content if hasattr(response, 'content') else str(response)
            if '```json' in content:
                raw = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                raw = content.split('```')[1].split('```')[0].strip()
            else:
                raw = content.strip()

            enriched = json.loads(raw)
            if isinstance(enriched, list) and len(enriched) == len(contradictions):
                logger.info(f"Orchestrator: contradiction self-reflection complete ({len(enriched)} items)")
                return enriched
        except Exception as e:
            logger.warning(f"Orchestrator: contradiction reflection failed: {e}")
        return contradictions

    def _extract_risk_transformation(self, ground_truth: Dict) -> Dict:
        """
        Extract risk transformation from ground truth.

        Tries multiple data sources for robustness:
        1. residual_risk (newest format, Phase 3B+)
        2. residual_risks_before/after (Phase 3B format with overall_residual)
        3. risk_analysis (older format, Phase 3A)
        4. expected_risk_score (original format, Phase 1-2)
        """
        residual = ground_truth.get("residual_risk", {})
        before = residual.get("before", {}).get("score")
        after = residual.get("after", {}).get("score")

        # Fallback 1: residual_risks_before/after (Phase 3B format)
        if before is None:
            residual_before = ground_truth.get("residual_risks_before", {})
            residual_after = ground_truth.get("residual_risks_after", {})
            before = residual_before.get("overall_residual")
            after = residual_after.get("overall_residual")

        # Fallback 2: risk_analysis (older format)
        if before is None:
            risk_analysis = ground_truth.get("risk_analysis", {})
            before = risk_analysis.get("overall_risk_score")
            after = risk_analysis.get("overall_risk_score_with_controls")

        # Fallback 3: expected_risk_score (original format)
        if before is None:
            before = ground_truth.get("expected_risk_score")
            # Estimate "after" risk based on controls
            if after is None:
                controls_count = len(ground_truth.get("control_recommendations", []))
                if controls_count > 0:
                    # Rough estimate: each control reduces ~2-3 risk points
                    estimated_reduction = min(controls_count * 2.5, before * 0.6)
                    after = max(0, int(before - estimated_reduction))
                else:
                    after = before  # No controls = no reduction

            logger.info(
                f"Risk data from expected_risk_score: {before} → {after} "
                f"({controls_count} controls, {int(before - after if after else 0)} point reduction)"
            )

        before = before or 0
        after = after or 0
        reduction = int(((before - after) / before * 100) if before > 0 else 0)

        return {
            "current": before,
            "target": after,
            "reduction": reduction
        }

    def _build_improvement_options(self, consensus: Dict, risk_data: Dict) -> Dict:
        """
        Read improvement tier data from the LLM synthesis output (consensus).
        Falls back to count-based summaries without invented cost figures if
        synthesis did not produce tier data.
        """
        tiers = consensus.get("improvement_tiers", {})

        def _tier(key: str, name: str, focus: str) -> Dict:
            t = tiers.get(key, {})
            if t:
                return {
                    "name": name,
                    "items": t.get("items", []),
                    "effort": t.get("effort", "not estimated"),
                    "cost": t.get("cost", "cost not estimated"),
                    "risk_reduction": t.get("risk_reduction", ""),
                    "residual": t.get("residual", ""),
                    "practical_verdict": t.get("practical_verdict", ""),
                    "rationale": t.get("rationale", ""),
                }
            # Fallback — never invent costs
            counts = {
                "quick_win":   len(consensus.get("critical", [])),
                "recommended": len(consensus.get("critical", [])) + len(consensus.get("high", [])),
                "maximum":     len(consensus.get("critical", [])) + len(consensus.get("high", [])) + len(consensus.get("review", [])),
            }
            return {
                "name": name,
                "items": [],
                "effort": "not estimated",
                "cost": "cost not estimated",
                "risk_reduction": f"{risk_data['current']} → {risk_data['target']}",
                "residual": "Residual risk remains — controls reduce exposure but do not eliminate it.",
                "practical_verdict": "not assessed",
                "item_count": counts.get(key, 0),
                "focus": focus,
            }

        return {
            "quick_wins":  _tier("quick_win",   "Quick Wins",         "Critical gaps — highest ROI, lowest friction"),
            "recommended": _tier("recommended",  "Recommended Target", "Critical + High — balanced security/usability/cost"),
            "maximum":     _tier("maximum",      "Maximum Security",   "Full coverage including diminishing-return items"),
        }

    def _save_validation(self, critique: CritiqueScore, output_path: Path):
        """Save validation critique to JSON."""
        with open(output_path, 'w') as f:
            json.dump(critique.to_dict(), f, indent=2)

        logger.debug(f"Saved validation: {output_path}")


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def run_moe_pipeline(report_dir: str, base_confidence: float = 99.5) -> MoEResult:
    """
    Convenience function to run full MoE pipeline.

    Args:
        report_dir: Path to report directory
        base_confidence: Base confidence from deterministic (default: 99.5%)

    Returns:
        MoEResult with unified assessment

    Raises:
        MissingPrerequisiteError: If any prerequisite file missing

    Example:
        >>> result = run_moe_pipeline("report/10_complex_enterprise")
        >>> print(f"Final confidence: {result.final_confidence:.1f}%")
    """
    orchestrator = MoEOrchestrator()
    return orchestrator.run_pipeline(report_dir, base_confidence)


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.moe_orchestrator <report_dir>")
        print("Example: python3 -m chatbot.modules.moe_orchestrator report/10_complex_enterprise")
        sys.exit(1)

    report_dir = sys.argv[1]

    try:
        print(f"\n{'='*70}")
        print("MOE PIPELINE")
        print(f"{'='*70}\n")

        result = run_moe_pipeline(report_dir)

        print(f"\n{'='*70}")
        print("RESULTS")
        print(f"{'='*70}\n")
        print(f"Architecture: {result.architecture_name}")
        print(f"Final Confidence: {result.final_confidence:.1f}%")
        print(f"  Base: {result.base_confidence:.1f}%")
        print(f"  Architect: {result.architect_adjustment*100:+.1f}%")
        print(f"  Tester: {result.tester_adjustment*100:+.1f}%")
        print(f"  Red Team: {result.red_team_adjustment*100:+.1f}%")
        print(f"\nRisk Transformation:")
        print(f"  Current: {result.current_risk}/100")
        print(f"  Target: {result.target_risk}/100")
        print(f"  Reduction: {result.risk_reduction}%")
        print(f"\nConsensus Recommendations:")
        print(f"  Critical: {len(result.critical_recommendations)}")
        print(f"  High: {len(result.high_recommendations)}")
        print(f"  Review: {len(result.review_recommendations)}")
        print(f"\n{'='*70}\n")

    except MissingPrerequisiteError as e:
        print(f"\n❌ ERROR: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
