"""
AI/ML Threat Pattern using ARC Framework + MITRE ATLAS

Combines two complementary frameworks:
1. **ARC Framework** (46 risks, 88 controls) - Agentic AI risk categories
   Source: https://govtech-responsibleai.github.io/agentic-risk-capability-framework/
2. **MITRE ATLAS** (51+ techniques, 46+ mitigations) - Adversarial ML attacks
   Source: https://atlas.mitre.org/

ARC Framework Categories (9 major areas):
- Integrity (7 risks): Hallucination, bias, prompt injection, data poisoning
- Safety (8 risks): Harmful content, self-harm, violence, CSAM
- Security (10 risks): Unauthorized access, data breaches, supply chain
- Privacy (6 risks): PII leakage, training data extraction, re-identification
- Transparency (4 risks): Explainability, audit trails, model cards
- Accountability (3 risks): Human oversight, responsibility, redress
- Fairness (4 risks): Discrimination, representation bias, disparate impact
- Resilience (2 risks): Model degradation, adversarial robustness
- Societal Impact (2 risks): Job displacement, misinformation

MITRE ATLAS Techniques (real attack techniques):
- AML.T0051: LLM Prompt Injection (Direct, Indirect)
- AML.T0054: LLM Jailbreak
- AML.T0043: Model Inversion
- AML.T0020: Poison Training Data
- AML.T0018: Backdoor ML Model
- And 46+ more

VERSION: 1.1 - MITRE ATLAS integration for real attack techniques
"""

import logging
from typing import Dict, List, Set

from chatbot.modules.pattern_registry import ThreatPattern
from chatbot.modules.atlas_helper import get_atlas_helper

logger = logging.getLogger(__name__)


class AIPattern(ThreatPattern):
    """
    AI/ML-specific threat pattern using ARC Framework + MITRE ATLAS.

    **Framework Selection:**
    - Use **ARC Framework** (46 risks, 88 controls) as primary for agentic AI
    - Use **MITRE ATLAS** as secondary for adversarial ML attacks
    - Combined approach: ARC for risk identification + ATLAS for technique mapping

    **ARC Framework - 9 Risk Categories (46 total risks):**

    **1. INTEGRITY (7 risks)**
    - INT-001: Hallucination & factual inaccuracy
    - INT-002: Bias in outputs
    - INT-003: Prompt injection & jailbreaking
    - INT-004: Data/model poisoning
    - INT-005: Output manipulation
    - INT-006: Context window exploitation
    - INT-007: Model drift & degradation

    **2. SAFETY (8 risks)**
    - SAF-001: Generation of harmful content
    - SAF-002: Self-harm promotion
    - SAF-003: Violence & dangerous content
    - SAF-004: CSAM & illegal content
    - SAF-005: Dangerous capabilities (bioweapons, hacking)
    - SAF-006: Autonomous harmful actions
    - SAF-007: Unsafe tool use
    - SAF-008: Reward hacking

    **3. SECURITY (10 risks)**
    - SEC-001: Unauthorized data access
    - SEC-002: Data breach & exfiltration
    - SEC-003: API key exposure
    - SEC-004: System prompt extraction
    - SEC-005: Model weight theft
    - SEC-006: Supply chain compromise
    - SEC-007: Adversarial evasion
    - SEC-008: Backdoor attacks
    - SEC-009: Denial of service
    - SEC-010: Multi-agent collusion

    **4. PRIVACY (6 risks)**
    - PRIV-001: PII leakage
    - PRIV-002: Training data extraction
    - PRIV-003: Membership inference
    - PRIV-004: Re-identification attacks
    - PRIV-005: Sensitive context retention
    - PRIV-006: Cross-session information leakage

    **5. TRANSPARENCY (4 risks)**
    - TRANS-001: Lack of explainability
    - TRANS-002: Missing audit trails
    - TRANS-003: Incomplete model cards
    - TRANS-004: Hidden reasoning steps

    **6. ACCOUNTABILITY (3 risks)**
    - ACC-001: Insufficient human oversight
    - ACC-002: Unclear responsibility attribution
    - ACC-003: Lack of redress mechanisms

    **7. FAIRNESS (4 risks)**
    - FAIR-001: Discrimination & bias
    - FAIR-002: Representation bias
    - FAIR-003: Disparate impact
    - FAIR-004: Accessibility barriers

    **8. RESILIENCE (2 risks)**
    - RES-001: Model degradation under distribution shift
    - RES-002: Brittleness to adversarial inputs

    **9. SOCIETAL IMPACT (2 risks)**
    - SOC-001: Job displacement concerns
    - SOC-002: Misinformation amplification

    **88 ARC Controls (mapped to risks):**
    - Integrity: Input validation, output filtering, context grounding
    - Safety: Content moderation, human-in-loop, capability restrictions
    - Security: Access control, encryption, monitoring, rate limiting
    - Privacy: Differential privacy, data minimization, anonymization
    - Transparency: Logging, explainability tools, documentation
    - Accountability: Oversight mechanisms, incident response
    - Fairness: Bias testing, diverse datasets, fairness metrics
    - Resilience: Robustness testing, adversarial training, monitoring
    - Societal: Impact assessments, stakeholder engagement

    **MITRE ATLAS Threat Categories (legacy, for reference):**
    1. **Prompt Injection** (MITRE AML.T0051)
       - Risk: 70-90 for LLM systems
       - Controls: Input filtering, output validation, sandboxing
       - Techniques: T0051.001 (Direct), T0051.002 (Indirect)

    2. **Model Poisoning** (MITRE AML.T0020)
       - Risk: 60-80 for ML training pipelines
       - Controls: Data validation, provenance tracking, integrity checks
       - Techniques: T0020.001 (Training data), T0020.002 (Model weights)

    3. **Data Leakage** (MITRE AML.T0024)
       - Risk: 70-90 for models trained on sensitive data
       - Controls: Differential privacy, federated learning, data anonymization
       - Techniques: T0024.001 (Training data extraction), T0024.002 (Model inversion)

    4. **Adversarial Attacks** (MITRE AML.T0043)
       - Risk: 50-70 for deployed models
       - Controls: Adversarial training, input validation, ensemble models
       - Techniques: T0043.001 (Evasion), T0043.002 (Poisoning)

    5. **Model Inversion** (MITRE AML.T0024.002)
       - Risk: 40-60 for black-box models
       - Controls: Output randomization, query limiting, differential privacy
       - Techniques: T0024.002

    6. **Membership Inference** (MITRE AML.T0024.001)
       - Risk: 30-50 for models on sensitive datasets
       - Controls: Differential privacy, output perturbation
       - Techniques: T0024.001

    Node Type Detection:
    - LLM API (GPT, Claude, Gemini)
    - ML Training Pipeline
    - Model Serving Endpoint
    - Vector Database (embeddings)
    - Fine-tuning Service

    Control Recommendations:
    - Input sanitization (prompt filtering)
    - Output validation (PII detection)
    - Rate limiting (abuse prevention)
    - Model monitoring (drift detection)
    - Data governance (training data lineage)
    - Differential privacy (membership inference protection)
    - Adversarial training (robustness)

    Future Implementation: Phase 4 or 5
    """

    def __init__(self):
        super().__init__(name="AI/ML (ARC Framework)", version="1.1")
        self.atlas = get_atlas_helper()
        logger.info(f"{self.name} pattern initialized - ready for use (ATLAS: {len(self.atlas.get_techniques())} techniques)")

    def get_name(self) -> str:
        return "AI/ML (ARC)"

    def get_threat_categories(self) -> List[str]:
        """
        Return ARC Framework risk categories (46 risks across 9 categories).

        Primary categories for RAPIDS-style scoring:
        """
        return [
            # Primary threat categories (ARC Framework)
            "integrity",        # Hallucination, bias, prompt injection (7 risks)
            "safety",           # Harmful content, dangerous capabilities (8 risks)
            "security",         # Unauthorized access, data breach (10 risks)
            "privacy",          # PII leakage, data extraction (6 risks)
            "transparency",     # Explainability, audit (4 risks)
            "accountability",   # Oversight, responsibility (3 risks)
            "fairness",         # Discrimination, bias (4 risks)
            "resilience",       # Robustness, degradation (2 risks)
            "societal_impact"   # Job displacement, misinformation (2 risks)
        ]

    def get_supported_architecture_types(self) -> Set[str]:
        """AI pattern only applies to AI/ML systems."""
        return {"ai_system", "ml_pipeline", "llm_application"}

    def assess_threat(self, node: str, context: Dict) -> Dict:
        """
        Assess AI/ML-specific threats for node using ARC Framework.

        Implementation:
        1. Detect AI/ML component type (LLM API, Vector DB, Agent, etc.)
        2. Assess 9 ARC risk categories (0-100 each)
        3. Map to MITRE ATLAS techniques
        4. Return threat assessment

        Args:
            node: Node name (e.g., "OpenAI API", "Vector Database")
            context: Architecture context:
                - controls_present: List[str] (security controls deployed)
                - neighbors: List[str] (connected nodes)
                - architecture_type: str (should be "ai_system")
                - node_type: str (optional, inferred type)

        Returns:
            Dict with ARC risk assessment:
                {
                    "integrity": {"risk": 85, "rationale": "...", "techniques": [...]},
                    "safety": {"risk": 75, ...},
                    ...
                }
        """
        logger.debug(f"{self.name}: assess_threat() for node '{node}'")

        # Step 1: Detect AI component type
        component_type = self._detect_component_type(node)

        if component_type == "unknown":
            # Not an AI component, skip
            return {}

        logger.info(f"{self.name}: Detected {component_type} component: {node}")

        # Step 2: Get controls present (from context)
        controls_present = context.get("controls_present", [])
        controls_present_lower = [c.lower() for c in controls_present]

        # Step 2.5: Get ATLAS techniques for this component
        atlas_techniques = self.atlas.get_techniques_by_component(component_type)
        logger.debug(f"{self.name}: {len(atlas_techniques)} ATLAS techniques for {component_type}")

        # Step 3: Assess 9 ARC risk categories
        threats = {}

        # INTEGRITY (Hallucination, Prompt Injection, Bias)
        integrity_risk, integrity_rationale, integrity_techniques = self._assess_integrity_risk(
            component_type, node, controls_present_lower
        )
        if integrity_risk > 0:
            threats["integrity"] = {
                "risk": integrity_risk,
                "rationale": integrity_rationale,
                "techniques": integrity_techniques,
                "affected_nodes": [node]
            }

        # SAFETY (Harmful Content, Dangerous Capabilities)
        safety_risk, safety_rationale, safety_techniques = self._assess_safety_risk(
            component_type, node, controls_present_lower
        )
        if safety_risk > 0:
            threats["safety"] = {
                "risk": safety_risk,
                "rationale": safety_rationale,
                "techniques": safety_techniques,
                "affected_nodes": [node]
            }

        # SECURITY (API Exposure, Data Breach, Access Control)
        security_risk, security_rationale, security_techniques = self._assess_security_risk(
            component_type, node, controls_present_lower
        )
        if security_risk > 0:
            threats["security"] = {
                "risk": security_risk,
                "rationale": security_rationale,
                "techniques": security_techniques,
                "affected_nodes": [node]
            }

        # PRIVACY (PII Leakage, Data Extraction)
        privacy_risk, privacy_rationale, privacy_techniques = self._assess_privacy_risk(
            component_type, node, controls_present_lower
        )
        if privacy_risk > 0:
            threats["privacy"] = {
                "risk": privacy_risk,
                "rationale": privacy_rationale,
                "techniques": privacy_techniques,
                "affected_nodes": [node]
            }

        # Other categories (lower risk for MVP, default scores)
        # TRANSPARENCY
        transparency_risk = 60 if "logging" not in controls_present_lower else 30
        threats["transparency"] = {
            "risk": transparency_risk,
            "rationale": "Logging present" if transparency_risk == 30 else "No logging detected",
            "techniques": [],
            "affected_nodes": [node]
        }

        # ACCOUNTABILITY
        accountability_risk = 70 if "human_oversight" not in controls_present_lower else 40
        threats["accountability"] = {
            "risk": accountability_risk,
            "rationale": "Human oversight present" if accountability_risk == 40 else "No human oversight",
            "techniques": [],
            "affected_nodes": [node]
        }

        # FAIRNESS (default medium risk)
        threats["fairness"] = {
            "risk": 50,
            "rationale": "Fairness controls unknown (default risk)",
            "techniques": [],
            "affected_nodes": [node]
        }

        # RESILIENCE
        resilience_risk = 50 if "monitoring" in controls_present_lower else 60
        threats["resilience"] = {
            "risk": resilience_risk,
            "rationale": "Monitoring present" if resilience_risk == 50 else "No monitoring",
            "techniques": [],
            "affected_nodes": [node]
        }

        # SOCIETAL IMPACT (low risk by default)
        threats["societal_impact"] = {
            "risk": 30,
            "rationale": "Standard AI deployment (moderate societal impact)",
            "techniques": [],
            "affected_nodes": [node]
        }

        return threats

    # ========================================================================
    # Component Detection (Rule-Based, Deterministic)
    # ========================================================================

    def _detect_component_type(self, node: str) -> str:
        """
        Detect AI component type from node name (rule-based).

        Returns:
            Component type: llm_api, vector_db, agent_orchestrator,
                           embedding_service, code_execution, unknown
        """
        node_lower = node.lower()

        # LLM API
        llm_keywords = ["llm", "gpt", "openai", "anthropic", "claude", "gemini",
                       "api gateway", "language model", "chat api"]
        if any(kw in node_lower for kw in llm_keywords):
            return "llm_api"

        # Vector Database
        vector_keywords = ["vector", "embedding", "pinecone", "weaviate", "chroma",
                          "faiss", "milvus", "qdrant"]
        if any(kw in node_lower for kw in vector_keywords):
            return "vector_db"

        # Agent Orchestrator
        agent_keywords = ["agent", "orchestrator", "coordinator", "workflow"]
        if any(kw in node_lower for kw in agent_keywords):
            return "agent_orchestrator"

        # Embedding Service
        embed_keywords = ["embedding service", "embedder", "vectorizer"]
        if any(kw in node_lower for kw in embed_keywords):
            return "embedding_service"

        # Code Execution
        code_keywords = ["code execution", "sandbox", "interpreter", "jupyter"]
        if any(kw in node_lower for kw in code_keywords):
            return "code_execution"

        # Prompt Manager
        prompt_keywords = ["prompt", "template", "prompt manager"]
        if any(kw in node_lower for kw in prompt_keywords):
            return "prompt_manager"

        # Tool Registry
        tool_keywords = ["tool registry", "tool", "function calling"]
        if any(kw in node_lower for kw in tool_keywords):
            return "tool_registry"

        return "unknown"

    # ========================================================================
    # ARC Risk Assessment Methods
    # ========================================================================

    def _assess_integrity_risk(self, component_type: str, node: str, controls: List[str]) -> tuple:
        """
        Assess INTEGRITY risk (ARC Category 1): Hallucination, Prompt Injection, Bias

        High risk if:
        - No input validation (prompt injection)
        - No output filtering (hallucination)
        - No grounding/RAG (factual inaccuracy)

        Returns: (risk_score, rationale, techniques)
        """
        risk = 50  # Default medium risk
        rationale = []
        techniques = []

        if component_type == "llm_api":
            # LLM API has high integrity risk by default
            risk = 85

            if "input_validation" not in controls and "prompt_filtering" not in controls:
                risk = max(risk, 90)
                rationale.append("No input validation (prompt injection risk)")
                techniques.extend(["AML.T0051", "AML.T0051.000"])  # LLM Prompt Injection (Direct)

            if "output_filtering" not in controls and "content_validation" not in controls:
                risk = max(risk, 85)
                rationale.append("No output filtering (hallucination risk)")

            if "rag" not in controls and "grounding" not in controls:
                risk = max(risk, 80)
                rationale.append("No RAG/grounding (factual inaccuracy)")

            # Controls present reduce risk
            if "input_validation" in controls:
                risk -= 20
                rationale.append("Input validation present (reduces prompt injection)")

            if "output_filtering" in controls:
                risk -= 15
                rationale.append("Output filtering present (reduces hallucination)")

        elif component_type == "prompt_manager":
            risk = 70
            if "prompt_injection_defense" not in controls:
                rationale.append("Prompt manager without injection defense")
                techniques.append("AML.T0051.001")  # Indirect Prompt Injection
            else:
                risk -= 30

        elif component_type == "agent_orchestrator":
            risk = 75
            rationale.append("Agent orchestrator can amplify integrity risks")

        return (max(0, min(100, risk)), " | ".join(rationale) if rationale else f"Default {component_type} integrity risk", techniques)

    def _assess_safety_risk(self, component_type: str, node: str, controls: List[str]) -> tuple:
        """
        Assess SAFETY risk (ARC Category 2): Harmful Content, Dangerous Capabilities

        High risk if:
        - No content moderation
        - Autonomous actions enabled
        - Tool use unrestricted

        Returns: (risk_score, rationale, techniques)
        """
        risk = 40  # Default lower risk
        rationale = []
        techniques = []

        if component_type == "llm_api":
            risk = 75

            if "content_moderation" not in controls:
                risk = max(risk, 85)
                rationale.append("No content moderation (harmful content risk)")
                techniques.append("AML.T0051")  # LLM Prompt Injection (can generate harmful content)

            if "capability_restrictions" not in controls:
                risk = max(risk, 70)
                rationale.append("No capability restrictions")

            # Controls reduce risk
            if "content_moderation" in controls:
                risk -= 30
                rationale.append("Content moderation present")

        elif component_type == "code_execution":
            risk = 90  # Code execution is inherently high risk
            if "sandbox" not in controls:
                risk = 95
                rationale.append("Code execution without sandbox (critical safety risk)")
                techniques.append("AML.T0054")  # ARC: Unsafe tool use
            else:
                risk -= 40
                rationale.append("Sandbox present (reduces risk)")

        elif component_type == "agent_orchestrator":
            risk = 80
            if "human_oversight" not in controls and "human_in_loop" not in controls:
                risk = 85
                rationale.append("Autonomous agent without human oversight")
                techniques.append("AML.T0054")  # ARC: Autonomous harmful actions
            else:
                risk -= 25

        elif component_type == "tool_registry":
            risk = 70
            if "tool_allowlist" not in controls:
                rationale.append("Tool registry without allowlist")
            else:
                risk -= 20

        return (max(0, min(100, risk)), " | ".join(rationale) if rationale else f"Default {component_type} safety risk", techniques)

    def _assess_security_risk(self, component_type: str, node: str, controls: List[str]) -> tuple:
        """
        Assess SECURITY risk (ARC Category 3): API Exposure, Data Breach, Access Control

        High risk if:
        - No API key protection
        - No rate limiting
        - No access control

        Returns: (risk_score, rationale, techniques)
        """
        risk = 60  # Default medium risk
        rationale = []
        techniques = []

        if component_type == "llm_api":
            risk = 70

            if "api_key_rotation" not in controls and "secrets_management" not in controls:
                risk = max(risk, 90)
                rationale.append("No API key protection (exposure risk)")
                techniques.append("AML.T0040")  # ARC: API key exposure

            if "rate_limiting" not in controls:
                risk = max(risk, 75)
                rationale.append("No rate limiting (DoS risk)")
                techniques.append("AML.T0029")  # ARC: Denial of service
            else:
                risk -= 20
                rationale.append("Rate limiting present")

            if "access_control" not in controls and "authentication" not in controls:
                risk = max(risk, 80)
                rationale.append("No access control")
                techniques.append("AML.T0040")  # ARC: Unauthorized access
            else:
                risk -= 15

            if "encryption" in controls:
                risk -= 10
                rationale.append("Encryption present")

        elif component_type == "vector_db":
            risk = 70
            if "access_control" not in controls:
                risk = 85
                rationale.append("Vector DB without access control (data breach risk)")
                techniques.append("AML.T0024")  # ARC: Data breach
            else:
                risk -= 25

        elif component_type == "code_execution":
            risk = 95  # Extremely high security risk
            rationale.append("Code execution is high security risk")
            techniques.append("AML.T0043")  # ARC: Adversarial evasion

        return (max(0, min(100, risk)), " | ".join(rationale) if rationale else f"Default {component_type} security risk", techniques)

    def _assess_privacy_risk(self, component_type: str, node: str, controls: List[str]) -> tuple:
        """
        Assess PRIVACY risk (ARC Category 4): PII Leakage, Data Extraction

        High risk if:
        - No PII detection
        - Chat history stored
        - Training data contains PII

        Returns: (risk_score, rationale, techniques)
        """
        risk = 50  # Default medium risk
        rationale = []
        techniques = []

        if component_type == "llm_api":
            risk = 75

            if "pii_detection" not in controls and "data_loss_prevention" not in controls:
                risk = max(risk, 85)
                rationale.append("No PII detection (leakage risk)")
                techniques.append("AML.T0048")  # ARC: PII leakage
            else:
                risk -= 25
                rationale.append("PII detection present")

            if "data_minimization" not in controls:
                risk = max(risk, 70)
                rationale.append("No data minimization")

            if "differential_privacy" in controls:
                risk -= 20
                rationale.append("Differential privacy present")

        elif component_type == "vector_db":
            risk = 80
            rationale.append("Vector DB stores embeddings (potential data extraction)")
            techniques.append("AML.T0043")  # ARC: Training data extraction

            if "encryption" in controls:
                risk -= 20
            if "access_control" in controls:
                risk -= 15

        elif component_type == "embedding_service":
            risk = 65
            rationale.append("Embedding service processes sensitive data")

        return (max(0, min(100, risk)), " | ".join(rationale) if rationale else f"Default {component_type} privacy risk", techniques)

    def recommend_controls(self, threats: Dict, context: Dict) -> List[str]:
        """
        Recommend AI/ML-specific controls based on ARC Framework (88 controls).

        Maps high-risk areas to specific controls:
        - Integrity → input_validation, output_filtering, rag_verification
        - Safety → content_moderation, human_in_loop, sandbox
        - Security → api_key_rotation, rate_limiting, access_control
        - Privacy → pii_detection, differential_privacy, data_minimization

        Args:
            threats: Threat assessment from assess_threat()
            context: Architecture context

        Returns:
            List of recommended control names (prioritized)
        """
        logger.debug(f"{self.name}: recommend_controls() for {len(threats)} threat categories")

        controls = []
        priority_controls = []  # High priority (risk > 75)
        medium_controls = []    # Medium priority (risk 50-75)

        # INTEGRITY controls
        if "integrity" in threats and threats["integrity"]["risk"] > 50:
            risk = threats["integrity"]["risk"]
            if risk >= 80:
                priority_controls.extend(["input_validation", "prompt_filtering"])
            if risk >= 75:
                priority_controls.append("output_filtering")
            if risk >= 70:
                medium_controls.extend(["context_grounding", "rag_verification"])

        # SAFETY controls
        if "safety" in threats and threats["safety"]["risk"] > 50:
            risk = threats["safety"]["risk"]
            if risk >= 85:
                priority_controls.extend(["content_moderation", "sandbox"])
            if risk >= 75:
                priority_controls.append("human_in_loop")
            if risk >= 70:
                medium_controls.extend(["capability_restrictions", "tool_allowlist"])

        # SECURITY controls
        if "security" in threats and threats["security"]["risk"] > 50:
            risk = threats["security"]["risk"]
            if risk >= 85:
                priority_controls.extend(["api_key_rotation", "secrets_management"])
            if risk >= 70:
                priority_controls.extend(["rate_limiting", "access_control"])
            if risk >= 60:
                medium_controls.extend(["encryption", "authentication", "monitoring"])

        # PRIVACY controls
        if "privacy" in threats and threats["privacy"]["risk"] > 50:
            risk = threats["privacy"]["risk"]
            if risk >= 80:
                priority_controls.extend(["pii_detection", "data_loss_prevention"])
            if risk >= 70:
                medium_controls.extend(["differential_privacy", "data_minimization"])
            if risk >= 60:
                medium_controls.append("anonymization")

        # TRANSPARENCY controls (if risk > 60)
        if "transparency" in threats and threats["transparency"]["risk"] > 60:
            medium_controls.extend(["logging", "audit_trails"])

        # ACCOUNTABILITY controls (if risk > 70)
        if "accountability" in threats and threats["accountability"]["risk"] > 70:
            medium_controls.extend(["human_oversight", "incident_response"])

        # RESILIENCE controls (if risk > 60)
        if "resilience" in threats and threats["resilience"]["risk"] > 60:
            medium_controls.extend(["monitoring", "robustness_testing"])

        # Combine: priority first, then medium, deduplicate
        controls = list(dict.fromkeys(priority_controls + medium_controls))

        logger.info(f"{self.name}: Recommended {len(controls)} controls ({len(priority_controls)} priority)")
        return controls

    def get_arc_control_benchmark(self) -> Dict[str, List[str]]:
        """
        Get complete ARC Framework control set (88 controls) for gap analysis.

        Returns benchmark showing ALL available ARC controls by category,
        which can be compared against deployed controls to identify gaps.

        Returns:
            Dict mapping category to list of control names
        """
        return {
            "integrity": [
                "input_validation",
                "prompt_filtering",
                "output_filtering",
                "context_grounding",
                "rag_verification",
                "prompt_injection_defense",
                "factuality_checking",
                "bias_detection",
                "hallucination_detection",
                "model_versioning",
                "drift_monitoring"
            ],
            "safety": [
                "content_moderation",
                "sandbox",
                "human_in_loop",
                "capability_restrictions",
                "tool_allowlist",
                "safety_classifier",
                "toxicity_filtering",
                "harm_detection",
                "intent_classification",
                "refusal_mechanisms",
                "safety_guidelines",
                "red_teaming"
            ],
            "security": [
                "api_key_rotation",
                "secrets_management",
                "rate_limiting",
                "access_control",
                "encryption",
                "authentication",
                "monitoring",
                "vulnerability_scanning",
                "penetration_testing",
                "threat_modeling",
                "security_headers",
                "input_sanitization",
                "output_encoding",
                "session_management",
                "audit_logging"
            ],
            "privacy": [
                "pii_detection",
                "data_loss_prevention",
                "differential_privacy",
                "data_minimization",
                "anonymization",
                "pseudonymization",
                "data_retention_policy",
                "right_to_deletion",
                "consent_management",
                "privacy_impact_assessment",
                "data_classification",
                "secure_data_storage"
            ],
            "transparency": [
                "logging",
                "audit_trails",
                "explainability",
                "model_cards",
                "documentation",
                "decision_tracing",
                "version_control",
                "change_management",
                "disclosure_policies"
            ],
            "accountability": [
                "human_oversight",
                "incident_response",
                "escalation_procedures",
                "responsibility_assignment",
                "complaint_mechanisms",
                "redress_procedures",
                "governance_framework",
                "ethics_review"
            ],
            "fairness": [
                "bias_testing",
                "fairness_metrics",
                "diverse_datasets",
                "representation_analysis",
                "disparate_impact_assessment",
                "fairness_constraints",
                "bias_mitigation",
                "inclusive_design",
                "accessibility_testing"
            ],
            "resilience": [
                "monitoring",
                "robustness_testing",
                "adversarial_training",
                "input_validation",
                "anomaly_detection",
                "degradation_monitoring",
                "fallback_mechanisms",
                "redundancy",
                "disaster_recovery"
            ],
            "societal_impact": [
                "impact_assessment",
                "stakeholder_engagement",
                "public_consultation",
                "social_benefit_analysis",
                "harm_mitigation_plan",
                "workforce_transition_support"
            ]
        }

    def get_arc_control_gaps(self, controls_present: List[str], threats: Dict) -> Dict:
        """
        Calculate ARC control gaps - which of 88 controls are missing.

        Compares deployed controls against full ARC benchmark to identify
        critical gaps for AI/ML systems.

        Args:
            controls_present: List of deployed control names
            threats: Threat assessment with risk scores

        Returns:
            Dict with gap analysis:
                {
                    "controls_present": List[str],
                    "controls_missing": List[str],
                    "critical_gaps": List[str],  # High-risk categories
                    "coverage_by_category": Dict[str, float],
                    "overall_coverage": float
                }
        """
        benchmark = self.get_arc_control_benchmark()
        controls_present_lower = [c.lower().replace(" ", "_") for c in controls_present]

        controls_present_arc = []
        controls_missing_arc = []
        critical_gaps = []
        coverage_by_category = {}

        # Calculate coverage per category
        for category, arc_controls in benchmark.items():
            present = [c for c in arc_controls if c in controls_present_lower]
            missing = [c for c in arc_controls if c not in controls_present_lower]

            controls_present_arc.extend(present)
            controls_missing_arc.extend(missing)

            # Calculate coverage percentage
            coverage = len(present) / len(arc_controls) * 100 if arc_controls else 0
            coverage_by_category[category] = coverage

            # Mark as critical gap if high risk (>75) but low coverage (<30%)
            if category in threats:
                risk = threats[category].get("risk", 0)
                if risk > 75 and coverage < 30:
                    critical_gaps.append({
                        "category": category,
                        "risk": risk,
                        "coverage": coverage,
                        "missing_controls": missing[:5]  # Top 5
                    })

        # Overall coverage
        total_controls = sum(len(controls) for controls in benchmark.values())
        overall_coverage = len(controls_present_arc) / total_controls * 100 if total_controls else 0

        return {
            "controls_present": controls_present_arc,
            "controls_missing": controls_missing_arc,
            "critical_gaps": critical_gaps,
            "coverage_by_category": coverage_by_category,
            "overall_coverage": overall_coverage,
            "total_arc_controls": total_controls,
            "deployed_arc_controls": len(controls_present_arc)
        }

    def validate(self, ground_truth: Dict) -> Dict:
        """
        Validate AI/ML threat assessment completeness.

        Checks:
        1. AI components detected (at least 1)
        2. All 9 ARC categories assessed
        3. Controls recommended for high-risk areas
        4. Techniques mapped where applicable

        Args:
            ground_truth: Complete assessment with AI pattern results

        Returns:
            Validation result:
                {
                    "passed": bool,
                    "confidence": float (0.0-1.0),
                    "checks": Dict[str, bool],
                    "issues": List[str]
                }
        """
        logger.debug(f"{self.name}: validate() called")

        checks = {}
        issues = []

        # Check 1: AI components detected
        ai_threats = ground_truth.get("ai_ml_assessment", {})
        if not ai_threats:
            # Look for AI pattern in alternative locations
            ai_threats = ground_truth.get("pattern_assessments", {}).get("AI/ML (ARC)", {})

        ai_components_found = len(ai_threats) > 0
        checks["ai_components_detected"] = ai_components_found
        if not ai_components_found:
            issues.append("No AI components detected in architecture")

        # Check 2: 9 ARC categories assessed
        expected_categories = ["integrity", "safety", "security", "privacy",
                              "transparency", "accountability", "fairness",
                              "resilience", "societal_impact"]
        categories_present = []
        for cat in expected_categories:
            if cat in ai_threats:
                categories_present.append(cat)

        checks["arc_categories_complete"] = len(categories_present) == 9
        if len(categories_present) < 9:
            missing = set(expected_categories) - set(categories_present)
            issues.append(f"Missing ARC categories: {', '.join(missing)}")

        # Check 3: High-risk areas have controls recommended
        controls_recommended = ground_truth.get("ai_controls_recommended", [])
        high_risk_categories = [cat for cat, data in ai_threats.items()
                               if isinstance(data, dict) and data.get("risk", 0) > 75]

        checks["controls_for_high_risk"] = len(controls_recommended) > 0 if high_risk_categories else True
        if high_risk_categories and not controls_recommended:
            issues.append(f"High-risk categories but no controls recommended: {high_risk_categories}")

        # Check 4: Techniques mapped for critical risks
        techniques_mapped = any(
            isinstance(data, dict) and data.get("techniques", [])
            for data in ai_threats.values()
        )
        checks["techniques_mapped"] = techniques_mapped
        if not techniques_mapped:
            issues.append("No MITRE ATLAS techniques mapped")

        # Calculate confidence
        passed_checks = sum(1 for v in checks.values() if v)
        total_checks = len(checks)
        confidence = passed_checks / total_checks if total_checks > 0 else 0.0

        passed = confidence >= 0.75  # 3/4 checks must pass

        logger.info(f"{self.name}: Validation {'PASSED' if passed else 'FAILED'} - "
                   f"{passed_checks}/{total_checks} checks passed, confidence={confidence:.1%}")

        return {
            "passed": passed,
            "confidence": confidence,
            "checks": checks,
            "issues": issues
        }


# ============================================================================
# IMPLEMENTATION GUIDE FOR FUTURE DEVELOPERS
# ============================================================================
#
# **Primary Framework: ARC (Agentic Risk & Capability)**
# Source: https://govtech-responsibleai.github.io/agentic-risk-capability-framework/
# - 46 risks across 9 categories (Integrity, Safety, Security, Privacy, etc.)
# - 88 controls mapped to risks
# - Designed for agentic AI systems (LLM apps, autonomous agents, multi-agent)
# - **Deterministic-friendly:** Clear risk definitions, measurable controls
#
# **Secondary Framework: MITRE ATLAS**
# Source: https://atlas.mitre.org/
# - ~15 adversarial ML techniques
# - Good for mapping specific attack techniques
# - Use for technique IDs (e.g., AML.T0051 = Prompt Injection)
#
# **Tertiary: OWASP Top 10 for LLM**
# Source: https://owasp.org/www-project-top-10-for-large-language-model-applications/
# - 10 common LLM vulnerabilities
# - Use for web-facing LLM applications
#
# ============================================================================
# IMPLEMENTATION APPROACH (Deterministic)
# ============================================================================
#
# **1. Node Type Detection (similar to RAPIDS)**
# Detect AI/ML components in architecture:
#   - LLM API endpoint (OpenAI, Anthropic, Azure OpenAI)
#   - Vector database (Pinecone, Weaviate, Chroma)
#   - ML training pipeline
#   - Model serving endpoint
#   - Fine-tuning service
#   - Agent orchestrator (LangChain, LlamaIndex, CrewAI)
#   - RAG system (retrieval-augmented generation)
#
# **2. Risk Scoring (ARC Framework)**
# For each detected AI component, score 9 risk categories:
#
#   a. INTEGRITY risk (0-100)
#      - If no input validation → 80-90 (high hallucination risk)
#      - If no grounding/RAG → 70-80 (factual inaccuracy)
#      - If no prompt injection defense → 90-100 (critical)
#
#   b. SAFETY risk (0-100)
#      - If no content moderation → 70-90 (harmful content)
#      - If autonomous actions enabled → 80-100 (unsafe tool use)
#      - If no capability restrictions → 60-80
#
#   c. SECURITY risk (0-100)
#      - If API keys in code → 90-100 (critical)
#      - If no rate limiting → 70-80 (DoS risk)
#      - If no access control → 80-90
#
#   d. PRIVACY risk (0-100)
#      - If PII in training data → 80-90
#      - If no differential privacy → 70-80
#      - If chat history stored → 60-70
#
#   e-i. Similar scoring for Transparency, Accountability, Fairness, Resilience, Societal
#
# **3. Control Recommendations (88 ARC Controls)**
# Map high-risk areas to specific controls:
#
#   Integrity → input_validation, output_filtering, context_grounding, rag_verification
#   Safety → content_moderation, human_in_loop, capability_restrictions, tool_allowlist
#   Security → api_key_rotation, rate_limiting, access_control, encryption, monitoring
#   Privacy → differential_privacy, data_minimization, anonymization, pii_detection
#   Transparency → logging, explainability_tools, model_cards, audit_trails
#   Accountability → human_oversight, incident_response, escalation_procedures
#   Fairness → bias_testing, diverse_datasets, fairness_metrics, disparate_impact_analysis
#   Resilience → robustness_testing, adversarial_training, monitoring, fallback_mechanisms
#   Societal → impact_assessments, stakeholder_engagement, transparency_reports
#
# **4. Technique Mapping (MITRE ATLAS)**
# Map risks to specific ATLAS techniques:
#   - INT-003 (Prompt Injection) → AML.T0051.001 (Direct), AML.T0051.002 (Indirect)
#   - INT-004 (Data Poisoning) → AML.T0020.001 (Training data)
#   - PRIV-002 (Data Extraction) → AML.T0024.001 (Membership inference)
#   - SEC-007 (Adversarial Evasion) → AML.T0043.001 (Evasion attacks)
#
# **5. Validation**
# Check completeness:
#   - All AI components detected
#   - All 9 ARC categories assessed
#   - Controls mapped to high-risk areas
#   - ATLAS techniques assigned where applicable
#
# ============================================================================
# EXAMPLE: LLM API Endpoint Assessment
# ============================================================================
#
# Node: "OpenAI GPT-4 API"
# Controls present: ["rate_limiting", "api_key_rotation"]
# Controls missing: ["input_validation", "content_moderation", "pii_detection"]
#
# Risk Scores:
#   Integrity: 85/100 (no input validation → hallucination risk)
#   Safety: 75/100 (no content moderation → harmful content risk)
#   Security: 40/100 (rate limiting + key rotation present)
#   Privacy: 80/100 (no PII detection → data leakage risk)
#   Transparency: 60/100 (no logging)
#   Accountability: 70/100 (no human oversight)
#   Fairness: 50/100 (unknown, default)
#   Resilience: 50/100 (unknown, default)
#   Societal: 40/100 (low risk)
#
# Recommended Controls:
#   - input_validation (reduce Integrity risk 85→50)
#   - content_moderation (reduce Safety risk 75→40)
#   - pii_detection (reduce Privacy risk 80→50)
#   - logging (reduce Transparency risk 60→30)
#   - human_in_loop (reduce Accountability risk 70→40)
#
# ATLAS Techniques:
#   - AML.T0051.001 (Direct prompt injection) - HIGH risk
#   - AML.T0024.001 (PII extraction) - HIGH risk
#
# ============================================================================

__all__ = ['AIPattern']
