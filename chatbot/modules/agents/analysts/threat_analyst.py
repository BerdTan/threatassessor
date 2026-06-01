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
from typing import Dict, List, Optional, Tuple

from chatbot.modules.analyst_agent import AnalystAgent, AnalysisResult

logger = logging.getLogger(__name__)


def _compute_base_confidence(ground_truth: dict) -> Tuple[float, dict]:
    """
    Compute architecture-sensitive base confidence (0.72–0.995).

    Core principle: complexity penalises confidence; coverage signals recover it.
    A large, complex architecture starts lower because there are more ways to
    miss attack paths. It can only reach a high base if coverage proves the
    complexity was thoroughly mapped.

    Returns:
        (base_confidence, breakdown_dict) where breakdown_dict contains
        the intermediate signals for transparent reporting.
    """
    meta       = ground_truth.get("metadata", {})
    paths      = ground_truth.get("expected_attack_paths", [])
    validation = ground_truth.get("validation_report", {}).get("checks", {})

    node_count       = meta.get("node_count", 0)
    edge_count       = meta.get("edge_count", 0)
    path_count       = len(paths)
    technique_count  = sum(len(p.get("techniques", [])) for p in paths)
    control_coverage = float(meta.get("control_coverage", 0.0))

    checks    = [v for v in validation.values() if isinstance(v, dict)]
    pass_rate = sum(1 for c in checks if c.get("passed")) / max(len(checks), 1)

    # ── 1. Complexity penalty ─────────────────────────────────────────────────
    from chatbot.config import get_settings as _gs
    _cc = _gs().confidence
    node_penalty = min(node_count / _cc.node_saturation, 1.0) * _cc.node_penalty_factor
    edge_penalty = min(edge_count / _cc.edge_saturation, 1.0) * _cc.edge_penalty_factor
    complexity_penalty = round(min(node_penalty + edge_penalty, _cc.max_complexity_penalty), 4)

    # ── 2. Coverage recovery ──────────────────────────────────────────────────
    # Paths and techniques are normalised against expected minimums for this size.
    expected_paths      = max(node_count * 0.3, 1)
    expected_techniques = max(node_count * 1.5, 5)
    path_coverage = min(path_count / expected_paths, 1.0)
    tech_coverage = min(technique_count / expected_techniques, 1.0)

    coverage_recovery = round(
        control_coverage * 0.40 +
        pass_rate        * 0.30 +
        path_coverage    * 0.20 +
        tech_coverage    * 0.10,
        4
    )

    # ── 3. Compose base ───────────────────────────────────────────────────────
    _floor   = _cc.base_confidence_floor
    _ceiling_cfg = _cc.base_confidence_ceiling
    ceiling  = _ceiling_cfg - complexity_penalty
    base     = round(
        min(_ceiling_cfg, max(_floor,
            _floor + (ceiling - _floor) * coverage_recovery
        )),
        4
    )

    breakdown = {
        "complexity_penalty": complexity_penalty,
        "coverage_recovery":  coverage_recovery,
        "signals": {
            "node_count":         node_count,
            "edge_count":         edge_count,
            "path_count":         path_count,
            "technique_count":    technique_count,
            "control_coverage":   round(control_coverage, 4),
            "validation_pass_rate": round(pass_rate, 4),
        },
    }
    return base, breakdown


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
            ssp_profile = validated_context.get("ssp_profile", "low_risk_cloud")
            enable_ssp  = validated_context.get("enable_ssp", True)
            ground_truth = self.generator_module.generate_ground_truth(
                architecture_path,
                ssp_profile=ssp_profile,
                enable_ssp=enable_ssp,
                architecture_name=architecture_name,
            )
        except Exception as e:
            logger.error(f"{self.role}: Ground truth generation failed: {e}")
            raise

        # Validate completeness (6 checks)
        try:
            # Pass ground_truth dict to validator (not arch_name string)
            validation_result = self.validator_module.validate_completeness(ground_truth)
            # Complexity-biased base: complex architecture starts penalised;
            # coverage signals (control %, validation pass rate, path depth) recover it.
            base_confidence, confidence_breakdown = _compute_base_confidence(ground_truth)
            adjustment = validation_result.get("confidence_adjustment", 1.0)  # 0.0-1.0 scale
            confidence = base_confidence * adjustment
            checks_passed = validation_result.get("checks", {})
            logger.info(
                f"{self.role}: Confidence — base={base_confidence:.1%}, "
                f"validation_adj={adjustment:.3f}, final={confidence:.1%} "
                f"(complexity_penalty={confidence_breakdown['complexity_penalty']:.3f}, "
                f"coverage_recovery={confidence_breakdown['coverage_recovery']:.3f})"
            )
        except Exception as e:
            logger.warning(f"{self.role}: Validation failed: {e}")
            base_confidence = 0.95
            adjustment = 1.0
            confidence = 0.95  # Lower confidence if validation fails
            checks_passed = {}
            confidence_breakdown = {"complexity_penalty": 0.0, "coverage_recovery": 0.0, "signals": {}}

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
        cloud_assessment = {}
        nodes: List[str] = []  # shared across AI + Cloud pattern blocks

        if self._is_ai_architecture(architecture_path, ground_truth):
            logger.info(f"{self.role}: AI architecture detected, running AI pattern")

            try:
                from chatbot.modules.pattern_registry import get_pattern_registry

                # Always fetch from the module-level singleton rather than caching
                # on self — reset_pattern_registry() replaces the singleton when
                # enabled_patterns changes, so a cached self.pattern_registry would
                # keep running the old set of patterns.
                _registry = get_pattern_registry()
                logger.info(f"{self.role}: Using PatternRegistry ({_registry.list_patterns()})")

                # Run AI pattern assessment
                nodes = []
                for path in attack_paths:
                    nodes.extend(path.get("path", []))
                nodes = list(set(nodes))

                logger.info(f"{self.role}: Extracted {len(nodes)} unique nodes for AI assessment")

                context = {
                    "architecture_type": "ai_system",
                    "controls_present": controls_present,
                    "ground_truth": ground_truth
                }

                ai_results = _registry.assess_all(nodes, context)

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

                    # Enrich AI controls with GenAI SSP profile (GA-1–GA-8)
                    try:
                        from chatbot.modules.ssp_control_mapper import get_ssp_mapper
                        enriched_ai_controls = get_ssp_mapper().enrich_recommendations(
                            enriched_ai_controls, target_profile="generative_ai"
                        )
                        logger.info(f"{self.role}: AI controls enriched with generative_ai SSP profile")
                    except Exception as _ssp_err:
                        logger.warning(f"{self.role}: GenAI SSP enrichment failed: {_ssp_err}")

                    # Add enriched AI controls to recommendations
                    for enriched_ctrl in enriched_ai_controls:
                        ctrl_name = enriched_ctrl["control"]
                        if ctrl_name not in [c.get("control") for c in control_recommendations]:
                            control_recommendations.append(enriched_ctrl)

                    logger.info(f"{self.role}: AI pattern added {len(ai_controls)} controls (enriched with paths/placement)")

            except Exception as e:
                logger.warning(f"{self.role}: AI pattern failed: {e}")

        if self._is_cloud_architecture(architecture_path, ground_truth):
            logger.info(f"{self.role}: Cloud architecture detected, running Cloud (CAVEAT) pattern")

            try:
                from chatbot.modules.pattern_registry import get_pattern_registry

                _registry = get_pattern_registry()
                csp = self._detect_csp(ground_truth)

                if not nodes:
                    nodes = list({
                        n for path in attack_paths for n in path.get("path", [])
                    })

                cloud_context = {
                    "architecture_type": "cloud",
                    "controls_present": controls_present,
                    "csp": csp,
                    "ground_truth": ground_truth,
                }

                cloud_results = _registry.assess_all(nodes, cloud_context)

                if "Cloud Infrastructure (CAVEAT)" in cloud_results:
                    cloud_assessment = cloud_results["Cloud Infrastructure (CAVEAT)"]
                    pattern_sources.append("Cloud (CAVEAT)")

                    cloud_controls = cloud_assessment.controls_recommended
                    enriched_cloud_controls = self._enrich_cloud_controls(
                        cloud_controls,
                        cloud_assessment.threats,
                        attack_paths,
                        nodes,
                        controls_present,
                        csp,
                    )

                    # Enrich cloud controls with SSP cloud profile
                    try:
                        from chatbot.modules.ssp_control_mapper import get_ssp_mapper
                        cloud_ssp_profile = self._infer_cloud_ssp_profile(ground_truth)
                        enriched_cloud_controls = get_ssp_mapper().enrich_recommendations(
                            enriched_cloud_controls, target_profile=cloud_ssp_profile
                        )
                        logger.info(
                            f"{self.role}: Cloud controls enriched with SSP profile '{cloud_ssp_profile}'"
                        )
                    except Exception as _ssp_err:
                        logger.warning(f"{self.role}: Cloud SSP enrichment failed: {_ssp_err}")

                    for enriched_ctrl in enriched_cloud_controls:
                        ctrl_name = enriched_ctrl["control"]
                        if ctrl_name not in [c.get("control") for c in control_recommendations]:
                            control_recommendations.append(enriched_ctrl)

                    logger.info(
                        f"{self.role}: Cloud (CAVEAT) pattern added "
                        f"{len(cloud_controls)} controls (CSP={csp or 'generic'})"
                    )

            except Exception as e:
                logger.warning(f"{self.role}: Cloud pattern failed: {e}")

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

        # Attach confidence breakdown to result for API consumers
        result.data["confidence_breakdown"] = {
            "base":                  base_confidence,
            "complexity_penalty":    confidence_breakdown["complexity_penalty"],
            "coverage_recovery":     confidence_breakdown["coverage_recovery"],
            "validation_adjustment": round(adjustment, 4),
            "final":                 round(confidence, 4),
            "signals":               confidence_breakdown["signals"],
        }

        # Add AI assessment to result data if present
        if ai_assessment:
            result.data["ai_ml_assessment"] = ai_assessment.threats
            result.data["ai_controls_recommended"] = ai_assessment.controls_recommended

            # Calculate ARC control gaps (benchmark)
            try:
                from chatbot.modules.pattern_registry import get_pattern_registry
                ai_pattern = get_pattern_registry().get_pattern("AI/ML (ARC)")  # fresh fetch
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

        # Add Cloud (CAVEAT) assessment to result data if present
        if cloud_assessment:
            result.data["cloud_assessment"] = cloud_assessment.threats
            result.data["cloud_controls_recommended"] = cloud_assessment.controls_recommended

            # Attach CCM compliance controls (additive — keyed off T#### already in threats)
            try:
                from chatbot.modules.pattern_registry import get_pattern_registry
                _cloud_pattern = get_pattern_registry().get_pattern("Cloud Infrastructure (CAVEAT)")
                if _cloud_pattern:
                    ccm_controls = _cloud_pattern.get_ccm_controls(cloud_assessment.threats)
                    result.data["cloud_ccm_controls"] = ccm_controls
                    logger.info(
                        f"{self.role}: CCM compliance layer — {len(ccm_controls)} controls mapped"
                    )
            except Exception as e:
                logger.warning(f"{self.role}: CCM enrichment failed: {e}")

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

            # Get ATLAS techniques from threat categories
            atlas_techniques = []
            for cat in categories:
                if cat in ai_threats:
                    cat_techniques = ai_threats[cat].get("techniques", [])
                    atlas_techniques.extend(cat_techniques)
            atlas_techniques = list(set(atlas_techniques))  # Unique

            # Map control to ATLAS mitigations
            atlas_mitigations = self._get_atlas_mitigations_for_control(ctrl_name)

            # Build detailed rationale
            detailed_rationale = []
            for rat in risk_rationales[:3]:  # Top 3
                detailed_rationale.append(rat)

            detailed_rationale.append(f"Depth: {dir_category.upper()} at {layer} layer ({placement})")

            # Add ATLAS technique mitigation info if available
            if atlas_techniques:
                tech_str = ", ".join(atlas_techniques[:3])
                detailed_rationale.append(f"ATLAS: Mitigates {tech_str}")

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
                "techniques": atlas_techniques,  # ATLAS technique IDs
                "mitigations": atlas_mitigations,  # ATLAS mitigation IDs
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

    def _get_atlas_mitigations_for_control(self, control_name: str) -> List[str]:
        """
        Map AI control to ATLAS mitigation IDs.

        Returns:
            List of ATLAS mitigation IDs (e.g., ['AML.M0000', 'AML.M0015'])
        """
        # Map common AI controls to ATLAS mitigations
        control_to_mitigations = {
            # Input/Output controls
            "input_validation": ["AML.M0015"],  # Adversarial Input Detection
            "output_filtering": ["AML.M0015"],  # Adversarial Input Detection
            "prompt_filtering": ["AML.M0015"],  # Adversarial Input Detection

            # Access & Auth controls
            "access_control": ["AML.M0013", "AML.M0005"],  # Code Signing, Control Access to ML Models
            "authentication": ["AML.M0013"],  # Code Signing
            "api_key_rotation": ["AML.M0005"],  # Control Access to ML Models

            # Monitoring & Detection
            "monitoring": ["AML.M0016", "AML.M0004"],  # Vulnerability Scanning, Restrict Number of ML Model Queries
            "pii_detection": ["AML.M0017"],  # Model Distribution Methods
            "anomaly_detection": ["AML.M0016"],  # Vulnerability Scanning

            # Data Protection
            "encryption": ["AML.M0012"],  # Encrypt Sensitive Information
            "data_minimization": ["AML.M0017"],  # Model Distribution Methods
            "differential_privacy": ["AML.M0017", "AML.M0012"],  # Model Distribution Methods, Encrypt
            "anonymization": ["AML.M0012"],  # Encrypt Sensitive Information

            # Safety & Content
            "content_moderation": ["AML.M0015"],  # Adversarial Input Detection
            "sandbox": ["AML.M0014"],  # Limit Hardware & Software
            "human_in_loop": ["AML.M0007"],  # Sanitize Training Data (human oversight)

            # Rate limiting & Resilience
            "rate_limiting": ["AML.M0004"],  # Restrict Number of ML Model Queries
            "capability_restrictions": ["AML.M0014"],  # Limit Hardware & Software

            # Supply chain & Integrity
            "model_signing": ["AML.M0013"],  # Code Signing
            "secrets_management": ["AML.M0012"],  # Encrypt Sensitive Information

            # Training & Development
            "data_validation": ["AML.M0007"],  # Sanitize Training Data
            "adversarial_training": ["AML.M0002"],  # Passive ML Output Obfuscation
        }

        return control_to_mitigations.get(control_name, [])

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
        3. AI components in description
        4. AI components in node names (NEW - prevents blind spots)

        Args:
            architecture_path: Path to architecture file
            ground_truth: Ground truth data

        Returns:
            True if AI architecture detected
        """
        ai_keywords = ["ai", "ml", "llm", "agent", "gpt", "embedding", "vector",
                       "model", "inference", "training", "transformer", "openai",
                       "anthropic", "claude", "gemini", "mistral", "huggingface",
                       "pytorch", "tensorflow", "keras", "scikit"]

        # Method 1: Check metadata
        arch_type = ground_truth.get("metadata", {}).get("architecture_type", "")
        if arch_type in ["ai_system", "ml_pipeline", "llm_application"]:
            logger.info("AI architecture detected via metadata")
            return True

        # Method 2: Check filename
        arch_name = Path(architecture_path).stem.lower()
        if any(kw in arch_name for kw in ai_keywords):
            logger.info(f"AI architecture detected via filename: {arch_name}")
            return True

        # Method 3: Check for AI components in description
        description = ground_truth.get("description", "").lower()
        if any(kw in description for kw in ai_keywords):
            logger.info("AI architecture detected via description")
            return True

        # Method 4: Check actual node names in attack paths (prevents blind spots)
        attack_paths = ground_truth.get("expected_attack_paths", [])
        all_nodes = []
        for path in attack_paths:
            all_nodes.extend(path.get("path", []))

        # Check node names for AI components
        for node in all_nodes:
            node_lower = node.lower()
            if any(kw in node_lower for kw in ai_keywords):
                logger.info(f"AI architecture detected via node name: {node}")
                return True

        return False

    def _is_cloud_architecture(self, architecture_path: str, ground_truth: Dict) -> bool:
        """Detect if architecture contains cloud components."""
        cloud_keywords = [
            "aws", "azure", "gcp", "cloud", "s3", "ec2", "lambda", "kubernetes",
            "k8s", "docker", "container", "serverless", "iam", "vpc", "blob",
            "fargate", "gke", "aks", "eks", "cloudfront", "cloudtrail",
        ]

        arch_type = ground_truth.get("metadata", {}).get("architecture_type", "")
        if arch_type in ["cloud", "cloud_native", "hybrid_cloud"]:
            logger.info("Cloud architecture detected via metadata")
            return True

        arch_name = Path(architecture_path).stem.lower()
        if any(kw in arch_name for kw in cloud_keywords):
            logger.info(f"Cloud architecture detected via filename: {arch_name}")
            return True

        description = ground_truth.get("description", "").lower()
        if any(kw in description for kw in cloud_keywords):
            logger.info("Cloud architecture detected via description")
            return True

        attack_paths = ground_truth.get("expected_attack_paths", [])
        for path in attack_paths:
            for node in path.get("path", []):
                node_lower = node.lower()
                if any(kw in node_lower for kw in cloud_keywords):
                    logger.info(f"Cloud architecture detected via node name: {node}")
                    return True

        return False

    def _infer_cloud_ssp_profile(self, ground_truth: Dict) -> str:
        """
        Auto-select the most appropriate SSP cloud profile based on architecture cues.

        Priority:
        1. Explicit ssp_profile in request metadata → respect it
        2. CII keywords (gov, finance, health, critical) → high_risk_cloud_cii
        3. Default → low_risk_cloud

        Returns one of the SSP_PROFILES strings.
        """
        # Respect explicitly-set profile from API request
        meta_profile = ground_truth.get("metadata", {}).get("ssp_profile")
        if meta_profile:
            return meta_profile

        # Scan description + architecture name for CII indicators
        cii_keywords = [
            "government", "gov", "ministry", "finance", "banking", "health",
            "hospital", "critical", "cii", "utilities", "energy", "transport",
        ]
        text = " ".join([
            ground_truth.get("description", ""),
            ground_truth.get("metadata", {}).get("architecture_name", ""),
        ]).lower()

        if any(kw in text for kw in cii_keywords):
            return "high_risk_cloud_cii"

        return "low_risk_cloud"

    def _detect_csp(self, ground_truth: Dict) -> Optional[str]:
        """Infer CSP (aws/azure/gcp) from node names and description."""
        aws_kw = ["aws", "amazon", "ec2", "s3", "lambda", "cloudtrail",
                  "cloudfront", "cloudwatch", "eks", "fargate"]
        azure_kw = ["azure", "microsoft", "aks", "blob", "cosmos", "vnet"]
        gcp_kw = ["gcp", "google", "gke", "spanner", "bigquery", "cloud run"]

        text_parts = [ground_truth.get("description", "").lower()]
        for path in ground_truth.get("expected_attack_paths", []):
            text_parts.extend(n.lower() for n in path.get("path", []))
        combined = " ".join(text_parts)

        aws = sum(1 for kw in aws_kw if kw in combined)
        azure = sum(1 for kw in azure_kw if kw in combined)
        gcp = sum(1 for kw in gcp_kw if kw in combined)

        if aws == 0 and azure == 0 and gcp == 0:
            return None
        counts = {"aws": aws, "azure": azure, "gcp": gcp}
        return max(counts, key=lambda k: counts[k])

    def _enrich_cloud_controls(
        self,
        cloud_controls: List[str],
        cloud_threats: Dict,
        attack_paths: List[Dict],
        nodes: List[str],
        controls_present: List[str],
        csp: Optional[str],
    ) -> List[Dict]:
        """Enrich Cloud (CAVEAT) controls to match RAPIDS control structure."""
        from chatbot.modules.rapids_driven_controls import infer_dir_category
        from chatbot.modules.caveat_helper import get_caveat_helper

        caveat = get_caveat_helper()
        enriched = []

        # Category → threat category mapping for Cloud
        category_for_control = {
            "mfa": "iam_abuse",
            "least_privilege": "iam_abuse",
            "privileged_access_management": "iam_abuse",
            "iam_audit": "iam_abuse",
            "session_management": "iam_abuse",
            "encryption": "data_exposure",
            "bucket_policy": "data_exposure",
            "dlp": "data_exposure",
            "data_classification": "data_exposure",
            "api_gateway_auth": "api_abuse",
            "waf": "api_abuse",
            "rate_limiting": "api_abuse",
            "tls": "api_abuse",
            "container_scanning": "compute_abuse",
            "runtime_security": "compute_abuse",
            "function_permissions": "compute_abuse",
            "network_segmentation": "network_lateral",
            "vpc_flow_logs": "network_lateral",
            "zero_trust": "network_lateral",
            "image_signing": "supply_chain",
            "pipeline_security": "supply_chain",
            "sbom": "supply_chain",
            "cloudtrail": "logging_gaps",
            "log_integrity": "logging_gaps",
            "siem": "logging_gaps",
        }

        for ctrl_name in cloud_controls:
            category = category_for_control.get(ctrl_name, "")
            threat_data = cloud_threats.get(category, {}) if category else {}
            risk = threat_data.get("risk", 50) if isinstance(threat_data, dict) else 50

            if risk >= 75:
                priority = "critical"
            elif risk >= 65:
                priority = "high"
            else:
                priority = "medium"

            dir_category = infer_dir_category(ctrl_name)

            relevant_paths = [
                i for i, path in enumerate(attack_paths)
                if any(n in path.get("path", []) for n in nodes)
            ]

            # Get CAVEAT mitigation text for this control as rationale
            caveat_mits: List[str] = []
            for title in caveat.get_techniques_for_component(
                _CTRL_TO_COMPONENT.get(ctrl_name, "")
            )[:2]:
                mits = caveat.get_mitigations(title, csp=csp)
                caveat_mits.extend(mits[:1])

            techniques = []
            if category and category in cloud_threats:
                techniques = cloud_threats[category].get("techniques", [])

            rationale = (
                f"Cloud (CAVEAT): {category.replace('_', ' ').title()} | "
                f"CSP={csp or 'generic'} | "
                f"Attack path(s) #{', #'.join(str(i + 1) for i in relevant_paths[:3])}"
            )

            detailed_rationale = [rationale]
            if caveat_mits:
                detailed_rationale.append(f"CAVEAT: {caveat_mits[0][:150]}")

            enriched.append({
                "control": ctrl_name,
                "priority": priority,
                "score": risk,
                "rapids_threats": [f"Cloud:{category}"] if category else [],
                "attack_paths": relevant_paths,
                "rationale": rationale,
                "detailed_rationale": detailed_rationale,
                "dir_category": dir_category,
                "layer": _CTRL_LAYER.get(ctrl_name, "application"),
                "placement": f"At cloud {_CTRL_TO_COMPONENT.get(ctrl_name, 'infrastructure')} layer",
                "control_type": dir_category.upper(),
                "techniques": techniques,
                "mitigations": [],
                "confidence": {
                    "score": 0.80,
                    "level": "HIGH",
                    "breakdown": {"overall": 0.80, "caveat_validation": 0.80},
                },
                "source": "cloud_caveat",
            })

        return enriched


# Control metadata tables for _enrich_cloud_controls
_CTRL_TO_COMPONENT: Dict[str, str] = {
    "mfa": "iam",
    "least_privilege": "iam",
    "privileged_access_management": "iam",
    "iam_audit": "iam",
    "session_management": "api",
    "encryption": "storage",
    "bucket_policy": "storage",
    "dlp": "storage",
    "data_classification": "storage",
    "api_gateway_auth": "api",
    "waf": "api",
    "rate_limiting": "api",
    "tls": "api",
    "container_scanning": "compute",
    "runtime_security": "compute",
    "function_permissions": "compute",
    "network_segmentation": "network",
    "vpc_flow_logs": "network",
    "zero_trust": "network",
    "image_signing": "supply_chain",
    "pipeline_security": "supply_chain",
    "sbom": "supply_chain",
    "cloudtrail": "logging",
    "log_integrity": "logging",
    "siem": "logging",
}

_CTRL_LAYER: Dict[str, str] = {
    "mfa": "identity",
    "least_privilege": "identity",
    "privileged_access_management": "identity",
    "iam_audit": "identity",
    "session_management": "identity",
    "encryption": "data",
    "bucket_policy": "data",
    "dlp": "data",
    "data_classification": "data",
    "api_gateway_auth": "network",
    "waf": "network",
    "rate_limiting": "network",
    "tls": "network",
    "container_scanning": "application",
    "runtime_security": "application",
    "function_permissions": "application",
    "network_segmentation": "network",
    "vpc_flow_logs": "network",
    "zero_trust": "network",
    "image_signing": "application",
    "pipeline_security": "application",
    "sbom": "application",
    "cloudtrail": "data",
    "log_integrity": "data",
    "siem": "data",
}


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
