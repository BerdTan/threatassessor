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

from chatbot.modules.agents.critics import (
    EnhancedArchitectCritic,
    TesterCritic,
    RedTeamerCritic
)
from chatbot.modules.artifact_extractor import extract_artifacts, ArtifactSet
from chatbot.modules.agent_framework import CritiqueScore

logger = logging.getLogger(__name__)


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

    # Consensus recommendations (unified)
    critical_recommendations: List[Dict]  # All 3 agree
    high_recommendations: List[Dict]      # 2 agree
    review_recommendations: List[Dict]    # 1 only (may be false positive)

    # Risk transformation (from deterministic)
    current_risk: int  # 0-100
    target_risk: int   # After critical + high
    risk_reduction: int  # Percentage

    # Improvement options
    quick_wins: Dict      # Critical only (1-2 weeks)
    recommended: Dict     # Critical + High (1-3 months)
    maximum: Dict         # All recommendations (6+ months)

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
                "review": self.review_recommendations
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

        # Synthesize consensus recommendations
        consensus = self._synthesize_consensus(
            ground_truth,
            architect_result,
            tester_result,
            red_team_result
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
            current_risk=risk_data["current"],
            target_risk=risk_data["target"],
            risk_reduction=risk_data["reduction"],
            quick_wins=improvement_options["quick_wins"],
            recommended=improvement_options["recommended"],
            maximum=improvement_options["maximum"]
        )

        # Save orchestrator result
        orch_path = report_path / "07_moe_orchestrator.json"
        with open(orch_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"MoE Pipeline: ✓ Layer 3 complete - saved to {orch_path}")
        logger.info(f"MoE Pipeline: COMPLETE - {final_confidence:.1f}% confidence")

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
        # Determine validation status
        critical_gaps = len([g for g in critique.gaps if g.get("severity") in ["CRITICAL", "HIGH"]])

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
            original_score=critique.score
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
        red_team: ValidationResult
    ) -> Dict:
        """
        Synthesize consensus recommendations from all experts.

        Prioritization:
        - CRITICAL: All 3 experts agree (high confidence)
        - HIGH: 2 experts agree (medium confidence)
        - REVIEW: 1 expert only (may be false positive)
        """
        # Extract gaps from each expert
        all_gaps = {
            "architect": architect.gaps,
            "tester": tester.gaps,
            "red_team": red_team.gaps
        }

        # Group by similarity (simple: exact description match)
        # TODO: Enhance with semantic similarity
        gap_groups = {}

        for expert_name, gaps in all_gaps.items():
            for gap in gaps:
                desc = gap.get("description", "")[:100]  # First 100 chars

                if desc not in gap_groups:
                    gap_groups[desc] = {
                        "description": gap.get("description"),
                        "category": gap.get("category"),
                        "severity": gap.get("severity"),
                        "experts": []
                    }

                gap_groups[desc]["experts"].append(expert_name)

        # Categorize by consensus
        critical = []  # 3 experts
        high = []      # 2 experts
        review = []    # 1 expert

        for desc, group in gap_groups.items():
            expert_count = len(group["experts"])

            recommendation = {
                "description": group["description"],
                "category": group["category"],
                "severity": group["severity"],
                "source": " + ".join(group["experts"]),
                "confidence": expert_count * 33  # 33%, 66%, or 99%
            }

            if expert_count == 3:
                critical.append(recommendation)
            elif expert_count == 2:
                high.append(recommendation)
            else:
                review.append(recommendation)

        return {
            "critical": critical,
            "high": high,
            "review": review
        }

    def _extract_risk_transformation(self, ground_truth: Dict) -> Dict:
        """Extract risk transformation from ground truth."""
        residual = ground_truth.get("residual_risk", {})
        before = residual.get("before", {}).get("score", 0)
        after = residual.get("after", {}).get("score", 0)
        reduction = int(((before - after) / before * 100) if before > 0 else 0)

        return {
            "current": before,
            "target": after,
            "reduction": reduction
        }

    def _build_improvement_options(self, consensus: Dict, risk_data: Dict) -> Dict:
        """
        Build 3 improvement options (quick/recommended/maximum).
        """
        critical_count = len(consensus["critical"])
        high_count = len(consensus["high"])
        review_count = len(consensus["review"])

        # Quick wins: Critical only
        quick_wins = {
            "name": "Quick Wins",
            "timeline": "1-2 weeks",
            "cost": "$10-50K",
            "items": critical_count,
            "risk_reduction": f"{risk_data['current']} → ~{risk_data['current'] - 15}",
            "focus": "Critical gaps only"
        }

        # Recommended: Critical + High
        recommended = {
            "name": "Recommended Target",
            "timeline": "1-3 months",
            "cost": "$75-200K",
            "items": critical_count + high_count,
            "risk_reduction": f"{risk_data['current']} → {risk_data['target']}",
            "focus": "Critical + High priority"
        }

        # Maximum: All recommendations
        maximum = {
            "name": "Maximum Security",
            "timeline": "6+ months",
            "cost": "$300-600K",
            "items": critical_count + high_count + review_count,
            "risk_reduction": f"{risk_data['current']} → {max(0, risk_data['target'] - 5)}",
            "focus": "All recommendations (diminishing returns)"
        }

        return {
            "quick_wins": quick_wins,
            "recommended": recommended,
            "maximum": maximum
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
