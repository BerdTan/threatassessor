"""
Orchestrator Agent for Phase 3C+

Role: Coordinates 3 critic agents and synthesizes unified assessment

Workflow:
1. Run Architect (design quality)
2. Run Tester with Architect's roadmap (validation)
3. Run Red Team with Tester's gaps (exploit difficulty)
4. Calculate weighted composite score
5. Apply two-layer confidence model
6. Synthesize unified improvement roadmap

Scoring Formula:
- Architect: 30%
- Tester: 30%
- Red Team (defense): 40% (inverted from exploit score)

Confidence Model:
- Layer 1: Deterministic base (99.5%)
- Layer 2: Gap penalty (2% per critical gap)
- Layer 3: Consensus bonus (agents agree → +5-10%)

VERSION: 1.0 - Full 3-agent integration
"""

import json
import logging
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict

from chatbot.modules.architect_critic import EnhancedArchitectCritic
from chatbot.modules.tester_critic import TesterCritic
from chatbot.modules.red_teamer_critic import RedTeamerCritic
from chatbot.modules.artifact_extractor import extract_artifacts, ArtifactSet
from chatbot.modules.agent_framework import CritiqueScore

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Unified result from 3-agent orchestration."""

    # Individual agent scores
    architect_score: int
    tester_score: int
    red_team_exploit_score: int  # Raw exploit difficulty
    red_team_defense_score: int  # Inverted (100 - exploit)

    # Composite
    composite_score: int
    composite_rating: str

    # Confidence
    deterministic_confidence: float  # 99.5% base
    gap_penalty: float
    validated_confidence: float
    consensus_bonus: float
    final_confidence: float

    # Agent details
    architect_critique: CritiqueScore
    tester_critique: CritiqueScore
    red_team_critique: CritiqueScore

    # Unified roadmap
    unified_roadmap: List[Dict]
    recommended_target: Dict

    # Metadata
    architecture_name: str
    agent_agreement: str  # HIGH/MEDIUM/LOW


class Orchestrator:
    """
    Orchestrates 3 critic agents and produces unified assessment.
    """

    def __init__(self, model: str = None):
        """
        Initialize orchestrator with 3 agents.

        Args:
            model: Optional model override for all agents
        """
        self.model = model

        # Initialize agents
        self.architect = EnhancedArchitectCritic(model=model)
        self.tester = TesterCritic(model=model)
        self.red_team = RedTeamerCritic(model=model)

        logger.info("Orchestrator initialized with 3 agents")

    def orchestrate(
        self,
        report_dir: str,
        deterministic_confidence: float = 99.5
    ) -> OrchestratorResult:
        """
        Run full 3-agent orchestration.

        Args:
            report_dir: Path to report directory
            deterministic_confidence: Base confidence from deterministic engine

        Returns:
            OrchestratorResult with unified assessment
        """
        logger.info(f"Orchestrator: Starting 3-agent orchestration for {report_dir}")

        # Load artifacts
        architecture_name = Path(report_dir).name
        artifacts = extract_artifacts(report_dir)

        # Load ground truth
        gt_path = Path(report_dir) / "ground_truth.json"
        with open(gt_path) as f:
            ground_truth = json.load(f)

        # Step 1: Run Architect
        logger.info("Orchestrator: Running Architect agent...")
        architect_critique = self.architect.critique(artifacts)
        logger.info(f"Orchestrator: Architect complete - {architect_critique.score}/100")

        # Step 2: Run Tester (with Architect's roadmap)
        logger.info("Orchestrator: Running Tester agent...")
        tester_critique = self.tester.critique(artifacts, architect_critique)
        logger.info(f"Orchestrator: Tester complete - {tester_critique.score}/100")

        # Step 3: Run Red Team (with Tester's gaps)
        logger.info("Orchestrator: Running Red Team agent...")
        red_team_critique = self.red_team.critique(artifacts, ground_truth, tester_critique)
        logger.info(f"Orchestrator: Red Team complete - {red_team_critique.score}/100 exploit")

        # Calculate composite score
        composite_score, composite_rating = self._calculate_composite(
            architect_critique.score,
            tester_critique.score,
            red_team_critique.score
        )

        # Calculate final confidence
        confidence_breakdown = self._calculate_confidence(
            deterministic_confidence,
            tester_critique,
            [architect_critique.score, tester_critique.score, 100 - red_team_critique.score]
        )

        # Synthesize unified roadmap
        unified_roadmap, recommended_target = self._synthesize_roadmap(
            architect_critique,
            tester_critique,
            red_team_critique
        )

        # Build result
        result = OrchestratorResult(
            architect_score=architect_critique.score,
            tester_score=tester_critique.score,
            red_team_exploit_score=red_team_critique.score,
            red_team_defense_score=100 - red_team_critique.score,
            composite_score=composite_score,
            composite_rating=composite_rating,
            deterministic_confidence=deterministic_confidence,
            gap_penalty=confidence_breakdown["gap_penalty"],
            validated_confidence=confidence_breakdown["validated"],
            consensus_bonus=confidence_breakdown["consensus_bonus"],
            final_confidence=confidence_breakdown["final"],
            architect_critique=architect_critique,
            tester_critique=tester_critique,
            red_team_critique=red_team_critique,
            unified_roadmap=unified_roadmap,
            recommended_target=recommended_target,
            architecture_name=architecture_name,
            agent_agreement=confidence_breakdown["agreement"]
        )

        logger.info(f"Orchestrator: Complete - Composite {composite_score}/100, "
                   f"Confidence {confidence_breakdown['final']:.1f}%")

        return result

    def _calculate_composite(
        self,
        architect: int,
        tester: int,
        red_team_exploit: int
    ) -> tuple:
        """
        Calculate weighted composite score.

        Formula:
        - Architect: 30%
        - Tester: 30%
        - Red Team (defense): 40% (inverted from exploit)
        """

        # Invert Red Team score (low exploit = high defense)
        red_team_defense = 100 - red_team_exploit

        # Weighted average
        composite = int(
            architect * 0.30 +
            tester * 0.30 +
            red_team_defense * 0.40
        )

        # Determine rating
        if composite >= 90:
            rating = "EXCEPTIONAL"
        elif composite >= 85:
            rating = "EXCELLENT"
        elif composite >= 75:
            rating = "GOOD"
        elif composite >= 65:
            rating = "ACCEPTABLE"
        else:
            rating = "NEEDS IMPROVEMENT"

        logger.info(f"Orchestrator: Composite = ({architect}×0.3) + ({tester}×0.3) + "
                   f"({red_team_defense}×0.4) = {composite}/100 ({rating})")

        return composite, rating

    def _calculate_confidence(
        self,
        deterministic_base: float,
        tester_critique: CritiqueScore,
        agent_scores: List[int]
    ) -> Dict:
        """
        Apply two-layer confidence model.

        Layer 1: Deterministic base (99.5%)
        Layer 2: Gap penalty (2% per critical gap)
        Layer 3: Consensus bonus (agent agreement)
        """

        # Layer 1: Start with deterministic base
        base = deterministic_base

        # Layer 2: Reduce for critical gaps found by Tester
        critical_gaps = len([g for g in tester_critique.gaps
                            if 'CRITICAL' in str(g) or 'invalid' in str(g).lower()])
        gap_penalty = critical_gaps * 0.02  # 2% per gap
        validated = base * (1 - gap_penalty)

        # Layer 3: Consensus bonus (measure agent agreement)
        consensus = self._calculate_consensus(agent_scores)

        if consensus["std_dev"] < 10:
            agreement = "HIGH"
            consensus_bonus = 0.10  # +10%
        elif consensus["std_dev"] < 20:
            agreement = "MEDIUM"
            consensus_bonus = 0.05  # +5%
        else:
            agreement = "LOW"
            consensus_bonus = 0.00  # No bonus

        final = validated * (1 + consensus_bonus)
        final = min(100, final)  # Cap at 100%

        logger.info(f"Orchestrator: Confidence = {base:.1f}% base "
                   f"- {gap_penalty*100:.1f}% gaps "
                   f"+ {consensus_bonus*100:.1f}% consensus "
                   f"= {final:.1f}% final")

        return {
            "base": base,
            "gap_penalty": gap_penalty,
            "validated": validated,
            "consensus_bonus": consensus_bonus * validated,
            "final": final,
            "agreement": agreement,
            "consensus_details": consensus
        }

    def _calculate_consensus(self, scores: List[int]) -> Dict:
        """
        Measure agreement between agents.

        Args:
            scores: [architect, tester, red_team_defense]

        Returns:
            Dict with mean, std_dev, variance
        """

        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        return {
            "mean": mean,
            "variance": variance,
            "std_dev": std_dev,
            "scores": scores
        }

    def _synthesize_roadmap(
        self,
        architect: CritiqueScore,
        tester: CritiqueScore,
        red_team: CritiqueScore
    ) -> tuple:
        """
        Synthesize unified roadmap from all 3 agents.

        Prioritization:
        1. CRITICAL - Tester gaps (validation issues)
        2. HIGH - Architect + Red Team overlap (design + exploit)
        3. MEDIUM - Architect only (design improvements)
        4. LOW - Red Team impractical suggestions
        """

        recommendations = []

        # Priority 1: Fix validation issues (Tester)
        for gap in tester.gaps:
            gap_text = str(gap)
            recommendations.append({
                "priority": "CRITICAL",
                "source": "Tester",
                "action": f"Fix validation gap: {gap_text[:100]}",
                "impact": "Validation accuracy improvement",
                "effort": "Low (1-2 hours)",
                "quick_win": True,
                "practical": "YES"
            })

        # Priority 2: Exploit mitigation (Red Team practical suggestions)
        red_team_roadmap = red_team.breakdown.get("exploit_mitigation_roadmap", [])
        for step in red_team_roadmap:
            if step.get("practical") == "YES":
                # Check if Architect also recommends similar controls
                architect_overlap = False
                for arch_item in architect.improvement_roadmap:
                    # Simple check: if any requirement keyword overlaps
                    arch_text = str(arch_item).lower()
                    step_reqs = [str(r).lower() for r in step.get("requirements", [])]
                    if any(req_word in arch_text for req in step_reqs for req_word in req.split()):
                        architect_overlap = True
                        break

                priority = "HIGH" if architect_overlap else "MEDIUM"

                recommendations.append({
                    "priority": priority,
                    "source": "Red Team" + (" + Architect" if architect_overlap else ""),
                    "action": f"Reduce exploit difficulty to {step.get('target_score')}/100",
                    "requirements": step.get("requirements", []),
                    "impact": f"Exploit: {red_team.score}→{step.get('target_score')}",
                    "effort": step.get("effort", "Unknown"),
                    "cost": step.get("cost", "Unknown"),
                    "practical": step.get("practical", "UNKNOWN")
                })

        # Priority 3: Design improvements (Architect)
        for item in architect.improvement_roadmap:
            # Avoid duplicates
            already_added = any(
                str(item.get("issue", "")).lower() in str(rec.get("action", "")).lower()
                for rec in recommendations
            )

            if not already_added:
                recommendations.append({
                    "priority": "MEDIUM",
                    "source": "Architect",
                    "action": item.get("issue", "Unknown"),
                    "impact": f"Design quality +{item.get('impact_points', 0)} points",
                    "effort": "Medium",
                    "practical": "YES"
                })

        # Sort by priority
        priority_order = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 5))

        # Calculate recommended target
        current_composite = int(
            architect.score * 0.30 +
            tester.score * 0.30 +
            (100 - red_team.score) * 0.40
        )

        # Estimate improvement from critical + high priority items
        estimated_improvement = 0
        for rec in recommendations:
            if rec["priority"] in ["CRITICAL", "HIGH"]:
                # Estimate +3-5 points per item
                estimated_improvement += 4

        target_composite = min(100, current_composite + estimated_improvement)

        recommended_target = {
            "current_composite": current_composite,
            "target_composite": target_composite,
            "improvement_needed": estimated_improvement,
            "critical_items": len([r for r in recommendations if r["priority"] == "CRITICAL"]),
            "high_priority_items": len([r for r in recommendations if r["priority"] == "HIGH"])
        }

        logger.info(f"Orchestrator: Synthesized {len(recommendations)} recommendations, "
                   f"target {current_composite}→{target_composite}")

        return recommendations, recommended_target

    def save_result(self, result: OrchestratorResult, output_path: str):
        """
        Save orchestrator result to JSON file.

        Args:
            result: OrchestratorResult to save
            output_path: Path to output file
        """

        # Convert to dict
        data = {
            "architecture": result.architecture_name,
            "composite": {
                "score": result.composite_score,
                "rating": result.composite_rating,
                "formula": "Architect×30% + Tester×30% + RedTeam(defense)×40%"
            },
            "individual_scores": {
                "architect": {
                    "score": result.architect_score,
                    "weight": "30%",
                    "focus": "Design quality"
                },
                "tester": {
                    "score": result.tester_score,
                    "weight": "30%",
                    "focus": "Validation correctness"
                },
                "red_team": {
                    "exploit_score": result.red_team_exploit_score,
                    "defense_score": result.red_team_defense_score,
                    "weight": "40%",
                    "focus": "Exploit difficulty (inverted to defense strength)"
                }
            },
            "confidence": {
                "final": round(result.final_confidence, 1),
                "breakdown": {
                    "deterministic_base": result.deterministic_confidence,
                    "gap_penalty": round(result.gap_penalty * 100, 1),
                    "validated": round(result.validated_confidence, 1),
                    "consensus_bonus": round(result.consensus_bonus, 1),
                    "agent_agreement": result.agent_agreement
                }
            },
            "unified_roadmap": result.unified_roadmap,
            "recommended_target": result.recommended_target,
            "agent_critiques": {
                "architect": {
                    "score": result.architect_critique.score,
                    "rating": result.architect_critique.rating,
                    "improvement_roadmap": [asdict(item) if hasattr(item, '__dict__') else item
                                          for item in result.architect_critique.improvement_roadmap]
                },
                "tester": {
                    "score": result.tester_critique.score,
                    "rating": result.tester_critique.rating,
                    "gaps": result.tester_critique.gaps,
                    "strengths": result.tester_critique.strengths
                },
                "red_team": {
                    "exploit_score": result.red_team_critique.score,
                    "defense_score": 100 - result.red_team_critique.score,
                    "rating": result.red_team_critique.rating,
                    "exploit_mitigation_roadmap": result.red_team_critique.breakdown.get(
                        "exploit_mitigation_roadmap", []
                    )
                }
            }
        }

        # Save to file
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Orchestrator: Saved result to {output_path}")


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

def orchestrate_full_critique(report_dir: str, output_file: str = None) -> OrchestratorResult:
    """
    Convenience function to run full 3-agent orchestration.

    Args:
        report_dir: Path to report directory
        output_file: Optional output file path (default: report_dir/07_orchestrator_report.json)

    Returns:
        OrchestratorResult with unified assessment
    """

    # Create orchestrator
    orchestrator = Orchestrator()

    # Run orchestration
    result = orchestrator.orchestrate(report_dir)

    # Save result
    if output_file is None:
        output_file = str(Path(report_dir) / "07_orchestrator_report.json")

    orchestrator.save_result(result, output_file)

    return result
