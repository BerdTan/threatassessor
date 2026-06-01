"""
Pattern Registry for Threat Modeling System

Provides pluggable architecture for threat pattern detection.

Design:
- ThreatPattern: Abstract base for pattern implementations
- PatternRegistry: Manages registered patterns, runs assess_all()
- Built-in patterns: RAPIDS (default), AI/ML, Cloud, ICS, Mobile

Patterns can be:
- Domain-specific (Cloud, ICS, AI/ML, Mobile)
- Framework-specific (OWASP, CWE, STRIDE)
- Industry-specific (Financial, Healthcare, Government)

VERSION: 1.0 - Initial implementation for extensible threat modeling
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ThreatAssessment:
    """
    Result from a single threat pattern assessment.

    Contains:
    - Pattern name (e.g., "RAPIDS", "AI/ML", "Cloud")
    - Threats identified (category → risk score)
    - Recommended controls
    - Validation results
    """

    pattern_name: str
    threats: Dict[str, Dict]  # threat_category → {risk, rationale, techniques}
    controls_recommended: List[str]
    validation: Dict  # Pattern-specific validation results
    confidence: float  # 0.0-1.0
    metadata: Dict  # Additional pattern-specific data

    def to_dict(self) -> Dict:
        return asdict(self)


class ThreatPattern(ABC):
    """
    Abstract base class for threat patterns.

    Each pattern implements domain-specific threat detection logic.

    Examples:
    - RAPIDSPattern: Ransomware, Application, Phishing, Insider, DDoS, Supply chain
    - AIPattern: Prompt injection, Model poisoning, Data leakage, Adversarial attacks
    - CloudPattern: IAM misconfiguration, S3 exposure, API abuse, Serverless risks
    - ICSPattern: SCADA attacks, PLC manipulation, Modbus exploitation
    - MobilePattern: iOS/Android-specific vulnerabilities, App store risks
    """

    def __init__(self, name: str, version: str = "1.0"):
        """
        Initialize threat pattern.

        Args:
            name: Pattern name (e.g., "RAPIDS", "AI/ML")
            version: Pattern version for tracking changes
        """
        self.name = name
        self.version = version
        logger.info(f"Initialized {name} pattern (v{version})")

    @abstractmethod
    def get_name(self) -> str:
        """Return pattern name."""
        pass

    @abstractmethod
    def get_threat_categories(self) -> List[str]:
        """
        Return threat categories covered by this pattern.

        Examples:
        - RAPIDS: ["ransomware", "application_vulns", "phishing", "insider", "ddos", "supply_chain"]
        - AI/ML: ["prompt_injection", "model_poisoning", "data_leakage", "adversarial_attacks"]
        - Cloud: ["iam_misconfiguration", "storage_exposure", "api_abuse", "serverless_risks"]
        """
        pass

    @abstractmethod
    def assess_threat(self, node: str, context: Dict) -> Dict:
        """
        Assess threat for a given node in the architecture.

        Args:
            node: Node name (e.g., "Web Server", "AI Model", "S3 Bucket")
            context: Architecture context:
                - node_type: str (inferred type)
                - controls_present: List[str]
                - neighbors: List[str] (connected nodes)
                - architecture_type: str (web_app, ai_system, cloud_native, etc.)
                - full_graph: Dict (complete architecture)

        Returns:
            Dict with threat assessment:
                {
                    "threat_category": {
                        "risk": int (0-100),
                        "rationale": str,
                        "techniques": List[str] (MITRE technique IDs),
                        "affected_nodes": List[str]
                    },
                    ...
                }
        """
        pass

    @abstractmethod
    def recommend_controls(self, threats: Dict, context: Dict) -> List[str]:
        """
        Recommend security controls based on identified threats.

        Args:
            threats: Threat assessment from assess_threat()
            context: Architecture context (same as assess_threat)

        Returns:
            List of recommended control names
            (e.g., ["waf", "mfa", "encryption", "dlp"])
        """
        pass

    @abstractmethod
    def validate(self, ground_truth: Dict) -> Dict:
        """
        Validate completeness of threat assessment.

        Args:
            ground_truth: Complete assessment data

        Returns:
            Validation result:
                {
                    "passed": bool,
                    "confidence": float (0.0-1.0),
                    "checks": Dict[str, bool],
                    "issues": List[str]
                }
        """
        pass

    def get_supported_architecture_types(self) -> Set[str]:
        """
        Return architecture types this pattern supports.

        Default: All types. Override for domain-specific patterns.

        Returns:
            Set of architecture types (e.g., {"ai_system", "ml_pipeline"})
        """
        return {"all"}  # Default: universal pattern


class PatternRegistry:
    """
    Manages threat pattern plugins.

    Usage:
        registry = PatternRegistry()
        registry.register(RAPIDSPattern())
        registry.register(AIPattern())

        # Run all patterns on architecture
        results = registry.assess_all(nodes, context)
    """

    def __init__(self):
        """Initialize empty registry."""
        self.patterns: Dict[str, ThreatPattern] = {}
        logger.info("Initialized PatternRegistry")

    def register(self, pattern: ThreatPattern):
        """
        Register a threat pattern.

        Args:
            pattern: ThreatPattern implementation to register
        """
        name = pattern.get_name()
        if name in self.patterns:
            logger.warning(f"Pattern '{name}' already registered, replacing")

        self.patterns[name] = pattern
        logger.info(f"Registered pattern: {name} (v{pattern.version})")

    def unregister(self, pattern_name: str):
        """
        Unregister a threat pattern.

        Args:
            pattern_name: Name of pattern to remove
        """
        if pattern_name in self.patterns:
            del self.patterns[pattern_name]
            logger.info(f"Unregistered pattern: {pattern_name}")
        else:
            logger.warning(f"Pattern '{pattern_name}' not found in registry")

    def get_pattern(self, pattern_name: str) -> Optional[ThreatPattern]:
        """
        Get a registered pattern by name.

        Args:
            pattern_name: Pattern name

        Returns:
            ThreatPattern instance or None if not found
        """
        return self.patterns.get(pattern_name)

    def list_patterns(self) -> List[str]:
        """
        List all registered pattern names.

        Returns:
            List of pattern names
        """
        return list(self.patterns.keys())

    def assess_all(self, nodes: List[str], context: Dict) -> Dict[str, ThreatAssessment]:
        """
        Run all registered patterns on architecture.

        Args:
            nodes: List of node names in architecture
            context: Architecture context (type, controls, edges, etc.)

        Returns:
            Dict mapping pattern name → ThreatAssessment
        """
        results = {}
        architecture_type = context.get("architecture_type", "unknown")

        for name, pattern in self.patterns.items():
            # Check if pattern supports this architecture type
            supported_types = pattern.get_supported_architecture_types()
            if "all" not in supported_types and architecture_type not in supported_types:
                logger.info(f"Skipping {name} pattern (not supported for {architecture_type})")
                continue

            logger.info(f"Running {name} pattern on {len(nodes)} nodes")

            try:
                # Assess each node
                all_threats = {}
                all_controls = set()

                for node in nodes:
                    node_context = {**context, "current_node": node}
                    node_threats = pattern.assess_threat(node, node_context)

                    # Merge threats
                    for threat_cat, threat_data in node_threats.items():
                        if threat_cat not in all_threats:
                            all_threats[threat_cat] = threat_data
                        else:
                            # Aggregate risks (max risk across nodes)
                            current_risk = all_threats[threat_cat].get("risk", 0)
                            new_risk = threat_data.get("risk", 0)
                            if new_risk > current_risk:
                                all_threats[threat_cat] = threat_data

                # Recommend controls
                controls = pattern.recommend_controls(all_threats, context)
                all_controls.update(controls)

                # Validate (if ground truth available)
                validation = {}
                if "ground_truth" in context:
                    validation = pattern.validate(context["ground_truth"])

                # Build assessment
                assessment = ThreatAssessment(
                    pattern_name=name,
                    threats=all_threats,
                    controls_recommended=list(all_controls),
                    validation=validation,
                    confidence=validation.get("confidence", 1.0),
                    metadata={
                        "version": pattern.version,
                        "architecture_type": architecture_type,
                        "nodes_analyzed": len(nodes)
                    }
                )

                results[name] = assessment
                logger.info(f"{name} complete: {len(all_threats)} threats, {len(all_controls)} controls")

            except Exception as e:
                logger.error(f"Pattern {name} failed: {e}")
                # Continue with other patterns

        return results


# Convenience functions
def create_default_registry() -> PatternRegistry:
    """
    Create registry with patterns enabled in the live config.

    Only patterns whose ID appears in get_settings().patterns.enabled_patterns
    and whose status is 'active' in AVAILABLE_PATTERNS are registered.
    Falls back to registering AIPattern if config is unavailable.
    """
    from chatbot.modules.patterns.ai_pattern import AIPattern
    from chatbot.modules.patterns.cloud_pattern import CloudPattern

    registry = PatternRegistry()

    try:
        from chatbot.config import get_settings
        from chatbot.config.patterns_catalog import AVAILABLE_PATTERNS
        enabled = get_settings().patterns.enabled_patterns
    except Exception:
        # Config not yet available (e.g. CLI use before app startup)
        enabled = ["ai_ml_arc", "cloud"]

    if "ai_ml_arc" in enabled:
        registry.register(AIPattern())
    if "cloud" in enabled:
        registry.register(CloudPattern())

    return registry


_registry_instance: Optional[PatternRegistry] = None


def get_pattern_registry() -> PatternRegistry:
    """Return the shared PatternRegistry singleton (built once at first call)."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = create_default_registry()
    return _registry_instance


def reset_pattern_registry() -> None:
    """Invalidate the singleton so the next get_pattern_registry() call rebuilds it.

    Called by update_settings() whenever the patterns section changes, ensuring
    the registry reflects the new enabled_patterns list on the next analysis.
    """
    global _registry_instance
    _registry_instance = None


__all__ = [
    'ThreatPattern', 'ThreatAssessment', 'PatternRegistry',
    'create_default_registry', 'get_pattern_registry', 'reset_pattern_registry',
]
