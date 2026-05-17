"""
Threat Analyst Agent - Deterministic Threat Assessment

Wraps the deterministic engine (ground_truth_generator) as an AnalystAgent.

This agent:
- Parses architecture diagrams (.mmd)
- Runs RAPIDS threat assessment (99.5% confidence)
- Maps MITRE techniques per node
- Recommends security controls
- Calculates residual risk (before/after)

Future: Will integrate PatternRegistry for Cloud/ICS/Mobile patterns

VERSION: 1.0 - Initial implementation wrapping deterministic engine
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from chatbot.modules.analyst_agent import AnalystAgent, AnalysisResult

logger = logging.getLogger(__name__)


class ThreatAnalyst(AnalystAgent):
    """
    Deterministic threat analyst using ground truth generator.

    Wraps existing deterministic engine as an AnalystAgent for:
    - Unified agent interface
    - Future PatternRegistry integration
    - Consistency with critic agents

    Confidence: 99.5% (6-factor validation)
    """

    def __init__(self, model: Optional[str] = None):
        """
        Initialize threat analyst.

        Args:
            model: Unused for deterministic analyst (for API compatibility)
        """
        super().__init__(role="Threat Analyst (Deterministic)", model=model)

        # Import deterministic engine functions
        from chatbot.modules import ground_truth_generator
        from chatbot.modules import completeness_validator

        self.generator_module = ground_truth_generator
        self.validator_module = completeness_validator

        logger.info(f"Initialized {self.role} with deterministic engine")

    def execute(self, context: Dict) -> AnalysisResult:
        """
        Generate threat assessment from architecture.

        Args:
            context: Must contain "architecture_path" (path to .mmd file)

        Returns:
            AnalysisResult with complete threat assessment (ground truth data)
        """
        # Validate context
        validated_context = self._validate_context(context)
        architecture_path = validated_context.get("architecture_path")

        if not architecture_path:
            raise ValueError("ThreatAnalyst requires 'architecture_path' in context")

        architecture_name = self._extract_architecture_name(validated_context)

        logger.info(f"{self.role}: Generating threat assessment for {architecture_name}")

        # Generate ground truth using deterministic engine
        try:
            # Call the generate function directly
            ground_truth = self.generator_module.generate_ground_truth(architecture_path)
        except Exception as e:
            logger.error(f"{self.role}: Ground truth generation failed: {e}")
            raise

        # Validate completeness (6 checks)
        try:
            # Extract architecture name for validator
            arch_name = Path(architecture_path).stem
            validation_result = self.validator_module.validate_completeness(arch_name)
            confidence = validation_result.get("confidence", 0.995)
            checks_passed = validation_result.get("checks", {})
        except Exception as e:
            logger.warning(f"{self.role}: Validation failed: {e}")
            confidence = 0.95  # Lower confidence if validation fails
            checks_passed = {}

        # Extract key data from ground truth
        threats = ground_truth.get("rapids_assessment", {})
        attack_paths = ground_truth.get("expected_attack_paths", [])
        techniques = self._extract_techniques(attack_paths)

        controls_present = ground_truth.get("controls_present", [])
        controls_missing = ground_truth.get("controls_missing", [])
        control_recommendations = ground_truth.get("control_recommendations", [])

        residual_risk = ground_truth.get("residual_risks", {})
        residual_risk_before = residual_risk.get("before", {})
        residual_risk_after = residual_risk.get("after", {})

        # Build AnalysisResult
        result = AnalysisResult(
            agent_name=self.role,
            data=ground_truth,  # Full ground truth for backward compatibility
            architecture_name=architecture_name,
            threats=threats,
            attack_paths=attack_paths,
            techniques=techniques,
            controls_present=controls_present,
            controls_missing=controls_missing,
            control_recommendations=control_recommendations,
            residual_risk_before=residual_risk_before,
            residual_risk_after=residual_risk_after,
            confidence=confidence,
            validation_checks=checks_passed,
            pattern_sources=["RAPIDS"]  # Currently only RAPIDS, future: Cloud, ICS, etc.
        )

        logger.info(
            f"{self.role}: Assessment complete - "
            f"{len(techniques)} techniques, {len(control_recommendations)} controls, "
            f"confidence={confidence:.1%}"
        )

        return result

    def _extract_techniques(self, attack_paths: List[Dict]) -> List[str]:
        """
        Extract unique MITRE techniques from attack paths.

        Args:
            attack_paths: List of attack path dicts with 'techniques' key

        Returns:
            Sorted list of unique technique IDs
        """
        techniques = set()
        for path in attack_paths:
            techniques.update(path.get("techniques", []))

        return sorted(list(techniques))

    # ========================================================================
    # Future: PatternRegistry integration
    # ========================================================================

    def set_pattern_registry(self, registry):
        """
        Set pattern registry for multi-pattern analysis.

        Future enhancement for Phase 2:
        - Currently: Only RAPIDS pattern
        - Future: RAPIDS + Cloud + ICS + Mobile patterns

        Args:
            registry: PatternRegistry with registered patterns
        """
        self.pattern_registry = registry
        logger.info(f"{self.role}: Pattern registry updated with {len(registry.patterns)} patterns")


# Convenience function for backward compatibility
def generate_threat_analysis(architecture_path: str) -> Dict:
    """
    Generate threat analysis for architecture (legacy API).

    Args:
        architecture_path: Path to .mmd architecture file

    Returns:
        Ground truth dictionary (same format as ground_truth_generator)
    """
    analyst = ThreatAnalyst()
    result = analyst.execute({"architecture_path": architecture_path})
    return result.data  # Returns full ground truth dict


__all__ = ['ThreatAnalyst', 'generate_threat_analysis']
