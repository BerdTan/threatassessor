"""
Threat Pattern Plugins

Available patterns:
- AIPattern: AI/ML-specific threats using ARC Framework + MITRE ATLAS (active)
- CloudPattern: Cloud-specific threats using CSA CAVEAT framework (active)
- ICSPattern: ICS/SCADA threats (future)
- MobilePattern: Mobile app threats (future)
"""

from chatbot.modules.patterns.ai_pattern import AIPattern
from chatbot.modules.patterns.cloud_pattern import CloudPattern

__all__ = ["AIPattern", "CloudPattern"]
