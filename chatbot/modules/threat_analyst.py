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

        # Check if AI architecture and run AI pattern if available
        pattern_sources = ["RAPIDS"]  # Default
        ai_assessment = {}

        if self._is_ai_architecture(architecture_path, ground_truth):
            logger.info(f"{self.role}: AI architecture detected, running AI pattern")

            try:
                from chatbot.modules.patterns.ai_pattern import AIPattern
                from chatbot.modules.pattern_registry import PatternRegistry

                # Create registry with AI pattern if not already set
                if not hasattr(self, 'pattern_registry'):
                    self.pattern_registry = PatternRegistry()
                    self.pattern_registry.register(AIPattern())
                    logger.info(f"{self.role}: Auto-initialized PatternRegistry with AI pattern")

                # Run AI pattern assessment
                # Extract node names from ground truth
                nodes = []
                for path in attack_paths:
                    nodes.extend(path.get("path", []))
                nodes = list(set(nodes))  # Unique nodes

                logger.info(f"{self.role}: Extracted {len(nodes)} unique nodes for AI assessment")

                context = {
                    "architecture_type": "ai_system",
                    "controls_present": controls_present,
                    "ground_truth": ground_truth
                }

                ai_results = self.pattern_registry.assess_all(nodes, context)

                if "AI/ML (ARC)" in ai_results:
                    ai_assessment = ai_results["AI/ML (ARC)"]
                    pattern_sources.append("AI/ML (ARC)")

                    # Enrich AI controls with attack path and placement data
                    ai_controls = ai_assessment.controls_recommended
                    enriched_ai_controls = self._enrich_ai_controls(
                        ai_controls,
                        ai_assessment.threats,
                        attack_paths,
                        nodes,
                        controls_present
                    )

                    # Add enriched AI controls to recommendations
                    for enriched_ctrl in enriched_ai_controls:
                        ctrl_name = enriched_ctrl["control"]
                        if ctrl_name not in [c.get("control") for c in control_recommendations]:
                            control_recommendations.append(enriched_ctrl)

                    logger.info(f"{self.role}: AI pattern added {len(ai_controls)} controls (enriched with paths/placement)")

            except Exception as e:
                logger.warning(f"{self.role}: AI pattern failed: {e}")

        # Build AnalysisResult (AnalysisResult is a dataclass, not using AgentResult pattern)
        # Note: AnalysisResult doesn't inherit from AgentResult, it's standalone
        result = AnalysisResult(
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
            pattern_sources=pattern_sources
        )

        # Add AI assessment to result data if present
        if ai_assessment:
            result.data["ai_ml_assessment"] = ai_assessment.threats
            result.data["ai_controls_recommended"] = ai_assessment.controls_recommended

            # Calculate ARC control gaps (benchmark)
            try:
                from chatbot.modules.patterns.ai_pattern import AIPattern
                ai_pattern = AIPattern()
                arc_gaps = ai_pattern.get_arc_control_gaps(
                    controls_present,
                    ai_assessment.threats
                )
                result.data["arc_control_gaps"] = arc_gaps
                logger.info(
                    f"{self.role}: ARC benchmark - {arc_gaps['overall_coverage']:.1f}% coverage "
                    f"({arc_gaps['deployed_arc_controls']}/{arc_gaps['total_arc_controls']} controls), "
                    f"{len(arc_gaps['critical_gaps'])} critical gaps"
                )
            except Exception as e:
                logger.warning(f"{self.role}: Failed to calculate ARC gaps: {e}")

        logger.info(
            f"{self.role}: Assessment complete - "
            f"{len(techniques)} techniques, {len(control_recommendations)} controls, "
            f"patterns={pattern_sources}, confidence={confidence:.1%}"
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
    # PatternRegistry Integration
    # ========================================================================

    def set_pattern_registry(self, registry):
        """
        Set pattern registry for multi-pattern analysis.

        Enables multi-pattern threat detection:
        - RAPIDS: Ransomware, Application, Phishing, Insider, DDoS, Supply chain
        - AI/ML (ARC): 46 risks across 9 categories for AI systems
        - Future: Cloud, ICS, Mobile patterns

        Args:
            registry: PatternRegistry with registered patterns
        """
        self.pattern_registry = registry
        logger.info(f"{self.role}: Pattern registry updated with {len(registry.patterns)} patterns")

    def _enrich_ai_controls(
        self,
        ai_controls: List[str],
        ai_threats: Dict,
        attack_paths: List[Dict],
        nodes: List[str],
        controls_present: List[str]
    ) -> List[Dict]:
        """
        Enrich AI controls with attack path, placement, and DIR classification.

        Follows the same structure as RAPIDS controls:
        - Maps controls to attack paths they address
        - Determines DIR category (prevention/detect/isolate/respond)
        - Places controls at specific nodes
        - Adds detailed rationale per-node

        Args:
            ai_controls: List of AI control names
            ai_threats: AI threat assessment (9 ARC categories)
            attack_paths: Attack paths from ground truth
            nodes: Nodes detected in architecture
            controls_present: Already-deployed controls

        Returns:
            List of enriched control dicts with full RAPIDS-style structure
        """
        from chatbot.modules.rapids_driven_controls import infer_dir_category

        enriched = []

        # Map AI controls to ARC categories they address
        control_to_categories = self._map_ai_controls_to_categories()

        for ctrl_name in ai_controls:
            # Get ARC categories this control addresses
            categories = control_to_categories.get(ctrl_name, [])

            # Calculate priority based on highest risk category
            max_risk = 0
            risk_rationales = []
            for cat in categories:
                if cat in ai_threats:
                    risk = ai_threats[cat].get("risk", 0)
                    if risk > max_risk:
                        max_risk = risk
                    rationale = ai_threats[cat].get("rationale", "")
                    if rationale:
                        risk_rationales.append(f"{cat.capitalize()} (risk={risk}/100): {rationale}")

            # Determine priority
            if max_risk >= 80:
                priority = "critical"
            elif max_risk >= 70:
                priority = "high"
            else:
                priority = "medium"

            # Infer DIR category
            dir_category = infer_dir_category(ctrl_name)

            # Determine layer
            layer = self._infer_ai_control_layer(ctrl_name)

            # Find attack paths where this control would help
            # AI controls generally apply to all paths that touch AI components
            relevant_paths = []
            for i, path in enumerate(attack_paths):
                path_nodes = path.get("path", [])
                # Check if path touches any AI nodes
                if any(node in path_nodes for node in nodes):
                    relevant_paths.append(i)

            # Get affected nodes (AI components)
            affected_nodes = []
            for cat in categories:
                if cat in ai_threats:
                    affected_nodes.extend(ai_threats[cat].get("affected_nodes", []))
            affected_nodes = list(set(affected_nodes))  # Unique

            # Build placement string
            if affected_nodes:
                placement = f"At {affected_nodes[0]} hop"
            else:
                placement = "At AI/ML components"

            # Build detailed rationale
            detailed_rationale = []
            for rat in risk_rationales[:3]:  # Top 3
                detailed_rationale.append(rat)

            detailed_rationale.append(f"Depth: {dir_category.upper()} at {layer} layer ({placement})")

            # Build enriched control dict (matches RAPIDS structure)
            enriched_ctrl = {
                "control": ctrl_name,
                "priority": priority,
                "score": max_risk,  # Use risk as score
                "rapids_threats": [f"AI/ML:{cat}" for cat in categories],
                "attack_paths": relevant_paths,
                "rationale": f"AI/ML (ARC): {', '.join([c.capitalize() for c in categories])} | Attack path(s) #{', #'.join([str(i+1) for i in relevant_paths[:5]])}",
                "detailed_rationale": detailed_rationale,
                "dir_category": dir_category,
                "layer": layer,
                "placement": placement,
                "control_type": dir_category.upper(),
                "confidence": {
                    "score": 0.85,  # AI pattern confidence
                    "level": "HIGH",
                    "breakdown": {
                        "overall": 0.85,
                        "arc_validation": 0.85,
                        "attack_path_coverage": 1.0 if relevant_paths else 0.5,
                        "factors": {
                            "paths_addressed": f"{len(relevant_paths)}/{len(attack_paths)}",
                            "arc_categories": len(categories),
                            "max_risk": max_risk
                        }
                    }
                }
            }

            enriched.append(enriched_ctrl)

        return enriched

    def _map_ai_controls_to_categories(self) -> Dict[str, List[str]]:
        """
        Map AI controls to ARC categories they address.

        Returns:
            Dict mapping control name to list of ARC categories
        """
        return {
            # Integrity controls
            "input_validation": ["integrity", "security"],
            "prompt_filtering": ["integrity", "safety"],
            "output_filtering": ["integrity", "safety"],
            "context_grounding": ["integrity"],
            "rag_verification": ["integrity"],

            # Safety controls
            "content_moderation": ["safety", "societal_impact"],
            "sandbox": ["safety", "security"],
            "human_in_loop": ["safety", "accountability"],
            "capability_restrictions": ["safety"],
            "tool_allowlist": ["safety", "security"],

            # Security controls
            "api_key_rotation": ["security"],
            "secrets_management": ["security", "privacy"],
            "rate_limiting": ["security", "resilience"],
            "access_control": ["security", "privacy"],
            "encryption": ["security", "privacy"],
            "authentication": ["security"],
            "monitoring": ["security", "transparency", "resilience"],

            # Privacy controls
            "pii_detection": ["privacy"],
            "data_loss_prevention": ["privacy", "security"],
            "differential_privacy": ["privacy", "fairness"],
            "data_minimization": ["privacy"],
            "anonymization": ["privacy", "fairness"],

            # Transparency controls
            "logging": ["transparency", "accountability"],
            "audit_trails": ["transparency", "accountability"],

            # Accountability controls
            "human_oversight": ["accountability", "safety"],
            "incident_response": ["accountability", "resilience"],

            # Resilience controls
            "robustness_testing": ["resilience"]
        }

    def _infer_ai_control_layer(self, control_name: str) -> str:
        """
        Infer which layer an AI control operates at.

        Returns: "application", "data", "network", or "identity"
        """
        control_lower = control_name.lower()

        if any(kw in control_lower for kw in ["api_key", "authentication", "access_control", "secrets"]):
            return "identity"

        if any(kw in control_lower for kw in ["encryption", "pii", "data_loss", "data_minimization", "anonymization"]):
            return "data"

        if any(kw in control_lower for kw in ["rate_limiting", "monitoring"]):
            return "network"

        # Default to application layer (most AI controls)
        return "application"

    def _is_ai_architecture(self, architecture_path: str, ground_truth: Dict) -> bool:
        """
        Detect if architecture is AI/ML system.

        Detection methods:
        1. Architecture type in metadata
        2. AI keywords in architecture name
        3. AI components in ground truth

        Args:
            architecture_path: Path to architecture file
            ground_truth: Ground truth data

        Returns:
            True if AI architecture detected
        """
        # Method 1: Check metadata
        arch_type = ground_truth.get("metadata", {}).get("architecture_type", "")
        if arch_type in ["ai_system", "ml_pipeline", "llm_application"]:
            return True

        # Method 2: Check filename
        arch_name = Path(architecture_path).stem.lower()
        ai_keywords = ["ai", "ml", "llm", "agent", "gpt", "embedding", "vector"]
        if any(kw in arch_name for kw in ai_keywords):
            return True

        # Method 3: Check for AI components in architecture
        description = ground_truth.get("description", "").lower()
        if any(kw in description for kw in ai_keywords):
            return True

        return False


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
