"""
Analyst Agent Base Class - DEPRECATED MODULE

⚠️ DEPRECATION WARNING:
This module is deprecated. New code should import from:
- chatbot.modules.agents.analysts.ThreatAnalyst (for threat analysis)
- chatbot.modules.base_agent.BaseAgent (for base functionality)

This file is kept for backward compatibility with existing imports.
Will be removed in v2.0.
"""

import warnings
from dataclasses import dataclass
from typing import Dict, List
from chatbot.modules.base_agent import BaseAgent

warnings.warn(
    "chatbot.modules.analyst_agent is deprecated. "
    "Use chatbot.modules.base_agent.BaseAgent or chatbot.modules.agents.analysts.ThreatAnalyst instead.",
    DeprecationWarning,
    stacklevel=2
)

@dataclass
class AnalysisResult:
    """Result from threat analysis (backward compatibility)."""
    architecture_name: str
    threats: Dict
    attack_paths: List[Dict]
    techniques: List[str]
    controls_present: List[str]
    controls_missing: List[str]
    control_recommendations: List[Dict]
    residual_risk_before: Dict
    residual_risk_after: Dict
    confidence: float
    validation_checks: Dict
    pattern_sources: List[str]
    data: Dict = None

class AnalystAgent(BaseAgent):
    """
    Base class for analyst agents (backward compatibility).
    
    Analysts generate threat assessments.
    Implementations should override execute() method.
    """
    
    def get_capabilities(self) -> List[str]:
        """Return list of agent capabilities (default implementation)."""
        return ["threat_analysis"]

__all__ = ['AnalystAgent', 'AnalysisResult']
