"""
Canonical registry of available threat-analysis patterns.

Each entry describes a pattern module — whether it is implemented (active),
what architecture types it targets, and what it requires.  The enabled_patterns
list in PatternsSettings controls which active patterns are actually registered
at runtime.
"""

AVAILABLE_PATTERNS: dict = {
    "ai_ml_arc": {
        "name": "AI/ML (ARC Framework)",
        "status": "active",
        "arch_types": ["ai_system", "ml_pipeline", "llm_application"],
        "requires": ["ATLAS data (chatbot/data/atlas/)", "ARC YAML (chatbot/data/arc/)"],
        "description": (
            "Detects AI-specific threats using the ARC Framework v1.2 — 46 risks "
            "across 9 categories: integrity, safety, security, privacy, transparency, "
            "accountability, fairness, resilience, and societal impact. "
            "Activated automatically when AI/ML components are detected in the diagram."
        ),
        "default_enabled": True,
    },
    "cloud": {
        "name": "Cloud Infrastructure",
        "status": "planned",
        "arch_types": ["cloud", "web_app"],
        "requires": [],
        "description": (
            "Detects cloud-specific misconfigurations: IAM privilege escalation, "
            "S3/blob exposure, API gateway abuse, serverless cold-start attacks, "
            "and cross-account trust exploitation. Coming in a future release."
        ),
        "default_enabled": False,
    },
    "ics": {
        "name": "ICS / OT / SCADA",
        "status": "planned",
        "arch_types": ["ics", "ot", "industrial"],
        "requires": [],
        "description": (
            "Covers industrial control system threats: SCADA attacks, PLC manipulation, "
            "Modbus/DNP3 protocol abuse, historian compromise, and safety system bypass. "
            "Coming in a future release."
        ),
        "default_enabled": False,
    },
    "mobile": {
        "name": "Mobile Application",
        "status": "planned",
        "arch_types": ["mobile", "web_app"],
        "requires": [],
        "description": (
            "iOS and Android threat surface: insecure local storage, certificate pinning "
            "bypass, deep-link hijacking, and app-store supply chain risks. "
            "Coming in a future release."
        ),
        "default_enabled": False,
    },
}
