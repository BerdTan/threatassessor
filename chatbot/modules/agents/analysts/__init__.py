"""
Analyst Agents - Generate Threat Assessments

Analyst agents generate threat assessments from architecture diagrams.

Available Analysts:
- **ThreatAnalyst**: Deterministic engine (99.5% confidence)
  - RAPIDS threat assessment (6 categories)
  - MITRE ATT&CK technique mapping
  - Per-node control recommendations
  - Residual risk calculation (before/after)

Pattern System:
- **PatternRegistry**: Manages threat patterns for different architectures
  - MITRE + RAPIDS: Core pattern (all architectures)
  - ATLAS + ARC: AI/ML pattern (LLM, agents, RAG, vector DB)
  - Cloud patterns: AWS/Azure/GCP (future)
  - ICS patterns: OT/SCADA (future)

Version: 1.0 (Phase 3D)
"""

from chatbot.modules.agents.analysts.threat_analyst import ThreatAnalyst
from chatbot.modules.agents.analysts.pattern_registry import (
    PatternRegistry,
    ThreatPattern
)

__all__ = [
    # Analysts
    "ThreatAnalyst",

    # Pattern System
    "PatternRegistry",
    "ThreatPattern",
]
