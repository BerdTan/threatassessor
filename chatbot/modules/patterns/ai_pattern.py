"""
AI/ML Threat Pattern using ARC Framework + MITRE ATLAS

Combines two complementary frameworks:
1. **ARC Framework** (46 risks, 88 controls) - Agentic AI risk categories
   Source: https://govtech-responsibleai.github.io/agentic-risk-capability-framework/
2. **MITRE ATLAS** (51+ techniques, 46+ mitigations) - Adversarial ML attacks
   Source: https://atlas.mitre.org/

Risk data and control benchmarks are loaded from YAML at init time:
  chatbot/data/arc/risks.yaml    — per-component scoring rules
  chatbot/data/arc/controls.yaml — 88 ARC controls for gap analysis

VERSION: 1.2 - YAML-driven data extraction
"""

import logging
from pathlib import Path
from typing import Dict, List, Set

import yaml

from chatbot.modules.pattern_registry import ThreatPattern
from chatbot.modules.atlas_helper import get_atlas_helper

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "arc"


def _load_yaml(filename: str) -> dict:
    path = _DATA_DIR / filename
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class AIPattern(ThreatPattern):
    """
    AI/ML-specific threat pattern using ARC Framework + MITRE ATLAS.

    Risk scoring rules and the 88-control benchmark are read from:
      chatbot/data/arc/risks.yaml
      chatbot/data/arc/controls.yaml

    Public API is identical to v1.1 — callers are unaffected.
    """

    def __init__(self):
        super().__init__(name="AI/ML (ARC Framework)", version="1.2")
        self.atlas = get_atlas_helper()

        risks_data = _load_yaml("risks.yaml")
        self._risk_categories: List[Dict] = risks_data["categories"]
        # Index by name for O(1) lookup in assess_threat
        self._risk_by_name: Dict[str, Dict] = {
            cat["name"]: cat for cat in self._risk_categories
        }

        self._controls_benchmark: Dict[str, List[str]] = _load_yaml("controls.yaml")

        logger.info(
            f"{self.name} pattern initialized (ATLAS: {len(self.atlas.get_techniques())} techniques, "
            f"{len(self._risk_categories)} ARC categories, "
            f"{sum(len(v) for v in self._controls_benchmark.values())} controls)"
        )

    def get_name(self) -> str:
        return "AI/ML (ARC)"

    def get_threat_categories(self) -> List[str]:
        return [cat["name"] for cat in self._risk_categories]

    def get_supported_architecture_types(self) -> Set[str]:
        return {"ai_system", "ml_pipeline", "llm_application"}

    def assess_threat(self, node: str, context: Dict) -> Dict:
        """
        Assess AI/ML-specific threats for a node using ARC Framework rules.

        Returns a dict keyed by ARC category name, each value:
            {"risk": int, "rationale": str, "techniques": List[str], "affected_nodes": List[str]}
        """
        logger.debug(f"{self.name}: assess_threat() for node '{node}'")

        component_type = self._detect_component_type(node)
        if component_type == "unknown":
            return {}

        logger.info(f"{self.name}: Detected {component_type} component: {node}")

        controls = [c.lower() for c in context.get("controls_present", [])]
        atlas_techniques = self.atlas.get_techniques_by_component(component_type)
        logger.debug(f"{self.name}: {len(atlas_techniques)} ATLAS techniques for {component_type}")

        threats = {}
        for cat in self._risk_categories:
            risk, rationale, techniques = self._score_category(cat, component_type, controls)
            if risk > 0:
                threats[cat["name"]] = {
                    "risk": risk,
                    "rationale": rationale,
                    "techniques": techniques,
                    "affected_nodes": [node],
                }

        return threats

    # ── Component detection ──────────────────────────────────────────────────

    def _detect_component_type(self, node: str) -> str:
        node_lower = node.lower()

        keyword_map = [
            ("llm_api",           ["llm", "gpt", "openai", "anthropic", "claude", "gemini",
                                   "api gateway", "language model", "chat api"]),
            ("vector_db",         ["vector", "embedding", "pinecone", "weaviate", "chroma",
                                   "faiss", "milvus", "qdrant"]),
            ("agent_orchestrator",["agent", "orchestrator", "coordinator", "workflow"]),
            ("embedding_service", ["embedding service", "embedder", "vectorizer"]),
            ("code_execution",    ["code execution", "sandbox", "interpreter", "jupyter"]),
            ("prompt_manager",    ["prompt", "template", "prompt manager"]),
            ("tool_registry",     ["tool registry", "tool", "function calling"]),
        ]
        for component_type, keywords in keyword_map:
            if any(kw in node_lower for kw in keywords):
                return component_type
        return "unknown"

    # ── Generic category scorer ──────────────────────────────────────────────

    def _score_category(self, cat: Dict, component_type: str, controls: List[str]) -> tuple:
        """
        Apply YAML-defined rules for one ARC category and return (risk, rationale, techniques).

        Handles three rule patterns found in risks.yaml:
          - components:    per-component detailed rules (integrity, safety, security, privacy)
          - simple_rule:   single control presence/absence toggle (transparency, accountability, resilience)
          - static_rationale only: fixed score (fairness, societal_impact)

        Evaluation order: present_controls reductions first, then missing_controls floors (raise_to).
        This ensures that missing a critical control establishes a minimum floor even when
        other controls are present (e.g. missing access_control floors security at 80 regardless
        of rate_limiting being present).
        """
        rationale_parts: List[str] = []
        techniques: List[str] = []

        # ── Pattern A: per-component detailed rules ──────────────────────────
        if "components" in cat:
            comp_rules = cat["components"].get(component_type)
            if comp_rules is None:
                return (cat.get("default_risk", 50), f"Default {component_type} {cat['name']} risk", [])

            risk = comp_rules.get("default_risk", cat.get("default_risk", 50))

            # Static rationale / techniques from YAML (code_execution security, vector_db privacy, etc.)
            if "static_rationale" in comp_rules:
                rationale_parts.append(comp_rules["static_rationale"])
            if "static_techniques" in comp_rules:
                techniques.extend(comp_rules["static_techniques"])

            # present_controls reductions run first so raise_to floors apply after
            for rule in comp_rules.get("present_controls", []):
                if rule["control"] in controls:
                    risk -= rule.get("reduce_by", 0)
                    if rule.get("rationale"):
                        rationale_parts.append(rule["rationale"])

            # missing_controls floors: fires when ALL listed controls are absent
            for rule in comp_rules.get("missing_controls", []):
                rule_controls = rule.get("controls", [])
                if all(c not in controls for c in rule_controls):
                    risk = max(risk, rule.get("raise_to", risk))
                    if rule.get("rationale"):
                        rationale_parts.append(rule["rationale"])
                    techniques.extend(rule.get("techniques", []))

            risk = max(0, min(100, risk))
            rationale = " | ".join(rationale_parts) if rationale_parts else f"Default {component_type} {cat['name']} risk"
            return (risk, rationale, techniques)

        # ── Pattern B: simple present/absent toggle ──────────────────────────
        if "simple_rule" in cat:
            sr = cat["simple_rule"]
            if sr["if_control_absent"] in controls:
                return (sr["present_risk"], sr["present_rationale"], [])
            return (sr["absent_risk"], sr["absent_rationale"], [])

        # ── Pattern C: fixed score ────────────────────────────────────────────
        static_rationale = cat.get("static_rationale", f"Default {cat['name']} risk")
        return (cat.get("default_risk", 50), static_rationale, [])

    # ── Control recommendations ──────────────────────────────────────────────

    def recommend_controls(self, threats: Dict, context: Dict) -> List[str]:
        """
        Recommend AI/ML-specific controls based on ARC risk scores.

        Priority controls (risk > 75) are returned first; medium (50-75) second.
        """
        logger.debug(f"{self.name}: recommend_controls() for {len(threats)} threat categories")

        priority: List[str] = []
        medium: List[str] = []

        # INTEGRITY
        if "integrity" in threats and threats["integrity"]["risk"] > 50:
            risk = threats["integrity"]["risk"]
            if risk >= 80:
                priority.extend(["input_validation", "prompt_filtering"])
            if risk >= 75:
                priority.append("output_filtering")
            if risk >= 70:
                medium.extend(["context_grounding", "rag_verification"])

        # SAFETY
        if "safety" in threats and threats["safety"]["risk"] > 50:
            risk = threats["safety"]["risk"]
            if risk >= 85:
                priority.extend(["content_moderation", "sandbox"])
            if risk >= 75:
                priority.append("human_in_loop")
            if risk >= 70:
                medium.extend(["capability_restrictions", "tool_allowlist"])

        # SECURITY
        if "security" in threats and threats["security"]["risk"] > 50:
            risk = threats["security"]["risk"]
            if risk >= 85:
                priority.extend(["api_key_rotation", "secrets_management"])
            if risk >= 70:
                priority.extend(["rate_limiting", "access_control"])
            if risk >= 60:
                medium.extend(["encryption", "authentication", "monitoring"])

        # PRIVACY
        if "privacy" in threats and threats["privacy"]["risk"] > 50:
            risk = threats["privacy"]["risk"]
            if risk >= 80:
                priority.extend(["pii_detection", "data_loss_prevention"])
            if risk >= 70:
                medium.extend(["differential_privacy", "data_minimization"])
            if risk >= 60:
                medium.append("anonymization")

        # TRANSPARENCY
        if "transparency" in threats and threats["transparency"]["risk"] > 60:
            medium.extend(["logging", "audit_trails"])

        # ACCOUNTABILITY
        if "accountability" in threats and threats["accountability"]["risk"] > 70:
            medium.extend(["human_oversight", "incident_response"])

        # RESILIENCE
        if "resilience" in threats and threats["resilience"]["risk"] > 60:
            medium.extend(["monitoring", "robustness_testing"])

        controls = list(dict.fromkeys(priority + medium))
        logger.info(f"{self.name}: Recommended {len(controls)} controls ({len(priority)} priority)")
        return controls

    # ── ARC control benchmark / gap analysis ────────────────────────────────

    def get_arc_control_benchmark(self) -> Dict[str, List[str]]:
        """Return complete ARC control set (88 controls) for gap analysis."""
        return self._controls_benchmark

    def get_arc_control_gaps(self, controls_present: List[str], threats: Dict) -> Dict:
        """
        Calculate which of the 88 ARC controls are missing.

        Returns a gap-analysis dict with overall coverage and critical gaps
        (high-risk category + low control coverage).
        """
        controls_lower = [c.lower().replace(" ", "_") for c in controls_present]
        benchmark = self._controls_benchmark

        controls_present_arc: List[str] = []
        controls_missing_arc: List[str] = []
        critical_gaps: List[Dict] = []
        coverage_by_category: Dict[str, float] = {}

        for category, arc_controls in benchmark.items():
            present = [c for c in arc_controls if c in controls_lower]
            missing = [c for c in arc_controls if c not in controls_lower]

            controls_present_arc.extend(present)
            controls_missing_arc.extend(missing)

            coverage = len(present) / len(arc_controls) * 100 if arc_controls else 0
            coverage_by_category[category] = coverage

            if category in threats:
                risk = threats[category].get("risk", 0)
                if risk > 75 and coverage < 30:
                    critical_gaps.append({
                        "category": category,
                        "risk": risk,
                        "coverage": coverage,
                        "missing_controls": missing[:5],
                    })

        total_controls = sum(len(v) for v in benchmark.values())
        overall_coverage = len(controls_present_arc) / total_controls * 100 if total_controls else 0

        return {
            "controls_present": controls_present_arc,
            "controls_missing": controls_missing_arc,
            "critical_gaps": critical_gaps,
            "coverage_by_category": coverage_by_category,
            "overall_coverage": overall_coverage,
            "total_arc_controls": total_controls,
            "deployed_arc_controls": len(controls_present_arc),
        }

    # ── Validation ───────────────────────────────────────────────────────────

    def validate(self, ground_truth: Dict) -> Dict:
        """
        Validate AI/ML threat assessment completeness.

        Checks:
        1. AI components detected (at least 1)
        2. All 9 ARC categories assessed
        3. Controls recommended for high-risk areas
        4. Techniques mapped where applicable
        """
        logger.debug(f"{self.name}: validate() called")

        checks: Dict[str, bool] = {}
        issues: List[str] = []

        ai_threats = ground_truth.get("ai_ml_assessment", {})
        if not ai_threats:
            ai_threats = ground_truth.get("pattern_assessments", {}).get("AI/ML (ARC)", {})

        checks["ai_components_detected"] = len(ai_threats) > 0
        if not checks["ai_components_detected"]:
            issues.append("No AI components detected in architecture")

        expected_categories = [cat["name"] for cat in self._risk_categories]
        categories_present = [c for c in expected_categories if c in ai_threats]
        checks["arc_categories_complete"] = len(categories_present) == len(expected_categories)
        if not checks["arc_categories_complete"]:
            missing = set(expected_categories) - set(categories_present)
            issues.append(f"Missing ARC categories: {', '.join(missing)}")

        controls_recommended = ground_truth.get("ai_controls_recommended", [])
        high_risk = [c for c, d in ai_threats.items() if isinstance(d, dict) and d.get("risk", 0) > 75]
        checks["controls_for_high_risk"] = bool(controls_recommended) if high_risk else True
        if high_risk and not controls_recommended:
            issues.append(f"High-risk categories but no controls recommended: {high_risk}")

        checks["techniques_mapped"] = any(
            isinstance(d, dict) and d.get("techniques") for d in ai_threats.values()
        )
        if not checks["techniques_mapped"]:
            issues.append("No MITRE ATLAS techniques mapped")

        passed_checks = sum(1 for v in checks.values() if v)
        confidence = passed_checks / len(checks) if checks else 0.0
        passed = confidence >= 0.75

        logger.info(
            f"{self.name}: Validation {'PASSED' if passed else 'FAILED'} - "
            f"{passed_checks}/{len(checks)} checks passed, confidence={confidence:.1%}"
        )

        return {"passed": passed, "confidence": confidence, "checks": checks, "issues": issues}


__all__ = ['AIPattern']
