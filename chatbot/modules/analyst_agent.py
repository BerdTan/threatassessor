"""
Analyst Agent for MITRE Threat Modeling System

Abstract base class for agents that generate threat assessments.

AnalystAgent generates assessments (what threats exist?)
vs CriticAgent evaluates assessments (is the analysis good?)

Implementations:
- ThreatAnalyst: Wraps deterministic engine (ground_truth_generator)
- HybridThreatAnalyst: Deterministic + LLM enhancement (future, Phase 6)

VERSION: 1.0 - Initial implementation for agent hierarchy completion
"""

import logging
from abc import abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from chatbot.modules.base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """
    Result from threat analysis agent.

    Contains:
    - Threat assessment (RAPIDS scores, attack paths, techniques)
    - Control recommendations (what to deploy)
    - Residual risk (before/after)
    - Validation metadata (confidence, checks passed)

    Note: Does not inherit from AgentResult (dataclass incompatibility)
    """

    # Core analysis
    architecture_name: str
    threats: Dict  # RAPIDS assessment
    attack_paths: List[Dict]  # Expected attack paths
    techniques: List[str]  # MITRE techniques

    # Recommendations
    controls_present: List[str]
    controls_missing: List[str]
    control_recommendations: List[Dict]

    # Risk assessment
    residual_risk_before: Dict
    residual_risk_after: Dict

    # Metadata
    confidence: float  # 0.0-1.0
    validation_checks: Dict  # Which checks passed
    pattern_sources: List[str]  # Which patterns used (RAPIDS, Cloud, ICS, etc.)
    data: Dict = None  # Full ground truth for backward compatibility

    def to_dict(self) -> Dict:
        """Convert to dictionary (ground_truth.json format)."""
        result = asdict(self)
        # If data is present, merge it (for backward compatibility)
        if self.data:
            result.update(self.data)
        return result


class AnalystAgent(BaseAgent):
    """
    Abstract base class for threat analysis agents.

    Analyst agents generate threat assessments from architecture diagrams.

    Responsibilities:
    - Parse architecture (nodes, edges, components)
    - Identify threats (RAPIDS, Cloud, ICS, Mobile patterns)
    - Map MITRE techniques to components
    - Recommend security controls
    - Calculate residual risk (before/after)

    Subclasses:
    - ThreatAnalyst: Deterministic engine (99.5% confidence)
    - HybridThreatAnalyst: Deterministic + LLM (future)
    """

    def __init__(self, role: str = "Threat Analyst", model: Optional[str] = None):
        """
        Initialize analyst agent.

        Args:
            role: Agent role (default: "Threat Analyst")
            model: Optional model for LLM-based analysts (unused for deterministic)
        """
        super().__init__(role=role, model=model)
        logger.info(f"Initialized {role} analyst agent")

    @abstractmethod
    def execute(self, context: Dict) -> AnalysisResult:
        """
        Generate threat assessment from architecture.

        Args:
            context: Must contain one of:
                - "architecture_path": Path to .mmd file
                - "architecture_content": MMD content as string
                - "architecture_data": Pre-parsed architecture dict

        Returns:
            AnalysisResult with complete threat assessment
        """
        pass

    def get_capabilities(self) -> List[str]:
        """Return analyst capabilities."""
        return [
            "generate_assessment",
            "identify_threats",
            "map_techniques",
            "recommend_controls",
            "calculate_risk"
        ]

    # ========================================================================
    # Helper methods for subclasses
    # ========================================================================

    def _validate_context(self, context: Dict) -> Dict:
        """
        Validate context contains required architecture data.

        Args:
            context: Input context

        Returns:
            Validated context with architecture data

        Raises:
            ValueError: If required fields missing
        """
        if "architecture_path" in context:
            return context
        elif "architecture_content" in context:
            return context
        elif "architecture_data" in context:
            return context
        else:
            raise ValueError(
                "Context must contain one of: "
                "architecture_path, architecture_content, architecture_data"
            )

    def _extract_architecture_name(self, context: Dict) -> str:
        """
        Extract architecture name from context.

        Args:
            context: Input context

        Returns:
            Architecture name (filename without extension or custom name)
        """
        if "architecture_path" in context:
            from pathlib import Path
            return Path(context["architecture_path"]).stem
        elif "architecture_name" in context:
            return context["architecture_name"]
        else:
            return "unknown_architecture"


# For backward compatibility with imports
__all__ = ['AnalystAgent', 'AnalysisResult']
