"""
Threat Patterns for Different Architectures

Threat patterns provide architecture-specific threat assessments:

1. **MITRE + RAPIDS Pattern** (Core - all architectures)
   - 6 RAPIDS categories (Ransomware, Application, Phishing, Insider, DoS, Supply Chain)
   - 703 MITRE ATT&CK techniques
   - 44 MITRE mitigations
   - Prevention + DIR framework

2. **ATLAS + ARC Pattern** (AI/ML architectures)
   - 170 MITRE ATLAS techniques
   - 35 MITRE ATLAS mitigations
   - 88 ARC Framework controls (9 risk categories)
   - AI-specific threats: prompt injection, model theft, data poisoning

3. **Cloud Patterns** (Future - AWS/Azure/GCP)
   - Cloud-specific threats (IAM, S3, Lambda, etc.)
   - Cloud Security Alliance controls
   - Multi-cloud considerations

4. **ICS Patterns** (Future - OT/SCADA)
   - Industrial control system threats
   - ICS-specific MITRE techniques
   - Safety vs security tradeoffs

Version: 1.0 (Phase 3D)
"""

from chatbot.modules.agents.analysts.patterns.atlas_arc_pattern import AIPattern

__all__ = [
    "AIPattern",
]
