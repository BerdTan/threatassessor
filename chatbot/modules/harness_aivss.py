"""AIVSS v4 flow scorer and per-agent gate for ThreatAssessor harness."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Industry weight profiles
# ---------------------------------------------------------------------------

_INDUSTRY_WEIGHTS: Dict[str, Dict[str, float]] = {
    "government_public": {"w_inbound": 0.25, "w_internal": 0.50, "w_outbound": 0.25},
    "financial":         {"w_inbound": 0.30, "w_internal": 0.40, "w_outbound": 0.30},
    "healthcare":        {"w_inbound": 0.30, "w_internal": 0.40, "w_outbound": 0.30},
    "general":           {"w_inbound": 0.33, "w_internal": 0.34, "w_outbound": 0.33},
}

_DEFAULT_INDUSTRY = "government_public"


def _severity(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# MITRE technique → AIVSS sub-score mapping (top-15 calibration stub)
# Format: technique_id → list of (metric, sub_category, score)
# ---------------------------------------------------------------------------

_TECHNIQUE_AIVSS_MAP: Dict[str, List[Tuple[str, str, float]]] = {
    "T1566": [("LL", "prompt_injection", 0.70), ("CS", "model_manipulation", 0.55)],
    "T1190": [("CS", "insecure_apps_plugins", 0.70), ("AA", "decision_authority", 0.50)],
    "T1078": [("DS", "data_confidentiality", 0.70), ("AA", "goal_misalignment", 0.50)],
    "T1059": [("LL", "jailbreak", 0.70), ("CS", "insecure_apps_plugins", 0.50)],
    "T1203": [("MR", "evasion_resistance", 0.70), ("CS", "insecure_apps_plugins", 0.70)],
    "T1213": [("DS", "PII_exposure", 0.70), ("DS", "data_confidentiality", 0.70)],
    "T1005": [("DS", "data_confidentiality", 0.70), ("CS", "sensitive_data_disclosure", 0.70)],
    "T1486": [("DC", "operational_disruption", 0.90), ("DC", "reversibility", 0.90)],
    "T1485": [("DC", "operational_disruption", 0.90), ("DC", "reversibility", 0.90)],
    "T1490": [("DC", "operational_disruption", 0.90), ("AD", "concept_drift", 0.70)],
    "T1567": [("DS", "data_provenance", 0.70), ("CS", "sensitive_data_disclosure", 0.70)],
    "T1133": [("CS", "insecure_apps_plugins", 0.55), ("LL", "deployment_security", 0.55)],
    "T1195": [("CS", "insecure_supply_chain", 0.90), ("LL", "development_security", 0.90)],
    "T1055": [("MR", "evasion_resistance", 0.70), ("CS", "insecure_apps_plugins", 0.55)],
    "T1027": [("MR", "evasion_resistance", 0.70), ("MR", "gradient_masking", 0.70)],
}

# ---------------------------------------------------------------------------
# RAPIDS category → AIVSS metric mapping
# ---------------------------------------------------------------------------

_RAPIDS_AIVSS_MAP: Dict[str, List[Tuple[str, str]]] = {
    "ransomware":        [("DC", "operational_disruption"), ("DC", "reversibility")],
    "application_vulns": [("CS", "insecure_apps_plugins"), ("LL", "deployment_security")],
    "phishing":          [("LL", "prompt_injection"), ("CS", "model_manipulation")],
    "insider_threat":    [("DS", "data_confidentiality"), ("AA", "goal_misalignment")],
    "dos":               [("DC", "operational_disruption"), ("CS", "denial_of_service")],
    "supply_chain":      [("CS", "insecure_supply_chain"), ("LL", "development_security")],
}


def _rapids_risk_to_score(risk_pct: float) -> float:
    if risk_pct >= 81:
        return 0.90
    if risk_pct >= 61:
        return 0.70
    if risk_pct >= 31:
        return 0.50
    return 0.20


def _defensibility_to_multiplier(defensibility: float) -> float:
    if defensibility >= 81:
        return 1.00
    if defensibility >= 61:
        return 1.20
    if defensibility >= 31:
        return 1.35
    return 1.50


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AIVSSMetricScore:
    metric: str
    sub_scores: Dict[str, float] = field(default_factory=dict)
    composite: float = 0.0
    coverage: int = 0

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "sub_scores": self.sub_scores,
            "composite": round(self.composite, 2),
            "coverage": self.coverage,
        }


@dataclass
class AIVSSFlowScore:
    metrics: Dict[str, AIVSSMetricScore] = field(default_factory=dict)
    composite: float = 0.0
    severity: str = "LOW"
    coverage_pct: int = 0

    def to_dict(self) -> dict:
        return {
            "composite": round(self.composite, 2),
            "severity": self.severity,
            "coverage_pct": self.coverage_pct,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
        }


@dataclass
class AIVSSThreatScore:
    technique_id: str
    technique_name: str
    composite: float
    severity: str
    top_metric: str
    mitigation_multiplier: float

    def to_dict(self) -> dict:
        return {
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "composite": round(self.composite, 2),
            "severity": self.severity,
            "top_metric": self.top_metric,
            "mitigation_multiplier": round(self.mitigation_multiplier, 2),
        }


@dataclass
class AIVSSScore:
    inbound: AIVSSFlowScore
    internal: AIVSSFlowScore
    outbound: AIVSSFlowScore
    per_threat: List[AIVSSThreatScore] = field(default_factory=list)
    per_agent: Dict[str, AIVSSFlowScore] = field(default_factory=dict)
    overall: float = 0.0
    overall_severity: str = "LOW"
    industry: str = _DEFAULT_INDUSTRY
    coverage_pct: int = 0

    def to_dict(self) -> dict:
        return {
            "industry": self.industry,
            "inbound": self.inbound.to_dict(),
            "internal": self.internal.to_dict(),
            "outbound": self.outbound.to_dict(),
            "overall": {"composite": round(self.overall, 2), "severity": self.overall_severity},
            "per_threat": [t.to_dict() for t in self.per_threat],
            "per_agent": {k: v.to_dict() for k, v in self.per_agent.items()},
            "coverage_pct": self.coverage_pct,
        }


@dataclass
class AIVSSAgentContext:
    critic_name: str
    allowed_models: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    aivss_threshold: float = 10.0
    current_score: float = 0.0
    blocked: bool = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _composite(sub_scores: Dict[str, float]) -> float:
    if not sub_scores:
        return 0.0
    return min(10.0, max(sub_scores.values()) * 10.0)


def _flow_composite(metrics: Dict[str, AIVSSMetricScore]) -> float:
    composites = [m.composite for m in metrics.values() if m.composite > 0]
    if not composites:
        return 0.0
    return min(10.0, sum(composites) / len(composites))


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

class AIVSSFlowScorer:
    """Score AIVSS v4 across three flow directions from existing GovernanceSignals."""

    def __init__(self, industry: str = _DEFAULT_INDUSTRY):
        self.industry = industry if industry in _INDUSTRY_WEIGHTS else _DEFAULT_INDUSTRY

    # ---- inbound -----------------------------------------------------------

    def score_inbound(
        self,
        governance_signals: dict,
        architecture_path: str = "",
    ) -> AIVSSFlowScore:
        metrics: Dict[str, AIVSSMetricScore] = {}
        coverage = 0

        exploit = governance_signals.get("exploitation", {})
        d3 = governance_signals.get("data_leakage", {})
        d4 = governance_signals.get("identity_integrity", {})
        d5 = governance_signals.get("data_sovereignty", {})

        cs_subs: Dict[str, float] = {}
        if exploit.get("path_traversal"):
            cs_subs["model_manipulation"] = 0.90
            coverage += 1
        if exploit.get("injection_patterns"):
            cs_subs["insecure_apps_plugins"] = 0.70
            coverage += 1
        if d3.get("supply_chain_risk") or d4.get("supply_chain_modified_modules"):
            cs_subs["insecure_supply_chain"] = 0.90
            coverage += 1
        if cs_subs:
            metrics["CS"] = AIVSSMetricScore("CS", cs_subs, _composite(cs_subs), len(cs_subs))

        ll_subs: Dict[str, float] = {}
        if exploit.get("injection_patterns"):
            ll_subs["prompt_injection"] = 0.70
            coverage += 1
        if ll_subs:
            metrics["LL"] = AIVSSMetricScore("LL", ll_subs, _composite(ll_subs), len(ll_subs))

        mr_subs: Dict[str, float] = {}
        if exploit.get("homoglyph_count", 0) > 0 or exploit.get("url_encoded_count", 0) > 0:
            mr_subs["evasion_resistance"] = 0.70
            coverage += 1
        if mr_subs:
            metrics["MR"] = AIVSSMetricScore("MR", mr_subs, _composite(mr_subs), len(mr_subs))

        ds_subs: Dict[str, float] = {}
        if d3.get("pii_indicators"):
            ds_subs["data_provenance"] = 0.55
            coverage += 1
        if ds_subs:
            metrics["DS"] = AIVSSMetricScore("DS", ds_subs, _composite(ds_subs), len(ds_subs))

        gv_subs: Dict[str, float] = {}
        if d5.get("cross_boundary_nodes"):
            gv_subs["compliance"] = 0.55
            coverage += 1
        if gv_subs:
            metrics["GV"] = AIVSSMetricScore("GV", gv_subs, _composite(gv_subs), len(gv_subs))

        composite = _flow_composite(metrics)
        return AIVSSFlowScore(metrics, composite, _severity(composite), min(100, coverage * 10))

    # ---- internal ----------------------------------------------------------

    def score_internal(
        self,
        governance_signals: dict,
        moe_result=None,
        sm_result=None,
    ) -> AIVSSFlowScore:
        metrics: Dict[str, AIVSSMetricScore] = {}
        coverage = 0

        d2 = governance_signals.get("manipulation_resistance", {})
        d4 = governance_signals.get("identity_integrity", {})

        aa_subs: Dict[str, float] = {}
        if d2.get("confidence_swing_detected"):
            aa_subs["decision_authority"] = 0.70
            coverage += 1
        if d2.get("divergence_detected"):
            aa_subs["goal_misalignment"] = 0.70
            coverage += 1
        if aa_subs:
            metrics["AA"] = AIVSSMetricScore("AA", aa_subs, _composite(aa_subs), len(aa_subs))

        dc_subs: Dict[str, float] = {}
        if d2.get("confidence_swing_detected"):
            dc_subs["human_oversight"] = 0.55
            coverage += 1
        if dc_subs:
            metrics["DC"] = AIVSSMetricScore("DC", dc_subs, _composite(dc_subs), len(dc_subs))

        gv_subs: Dict[str, float] = {}
        tool_errors = d4.get("tool_errors", [])
        if tool_errors:
            gv_subs["audit_logging"] = 0.40
            coverage += 1
        critic_calls = d4.get("critic_tool_calls", {})
        if critic_calls:
            gv_subs["incident_response"] = 0.20
            coverage += 1
        if gv_subs:
            metrics["GV"] = AIVSSMetricScore("GV", gv_subs, _composite(gv_subs), len(gv_subs))

        ad_subs: Dict[str, float] = {}
        if sm_result is not None:
            retriggers = getattr(sm_result, "retrigger_count", 0)
            if not isinstance(retriggers, int):
                retriggers = 0
            if retriggers > 1:
                ad_subs["concept_drift"] = min(0.70, retriggers * 0.20)
                coverage += 1
        if ad_subs:
            metrics["AD"] = AIVSSMetricScore("AD", ad_subs, _composite(ad_subs), len(ad_subs))

        ll_subs: Dict[str, float] = {}
        if tool_errors:
            ll_subs["operational_security"] = min(0.70, len(tool_errors) * 0.15)
            coverage += 1
        if ll_subs:
            metrics["LL"] = AIVSSMetricScore("LL", ll_subs, _composite(ll_subs), len(ll_subs))

        composite = _flow_composite(metrics)
        return AIVSSFlowScore(metrics, composite, _severity(composite), min(100, coverage * 10))

    # ---- outbound ----------------------------------------------------------

    def score_outbound(
        self,
        governance_signals: dict,
        arc_scores: Optional[dict] = None,
    ) -> AIVSSFlowScore:
        metrics: Dict[str, AIVSSMetricScore] = {}
        coverage = 0

        d3 = governance_signals.get("data_leakage", {})
        d4 = governance_signals.get("identity_integrity", {})
        d5 = governance_signals.get("data_sovereignty", {})

        ds_subs: Dict[str, float] = {}
        pii = d3.get("pii_indicators", [])
        if pii:
            ds_subs["PII_exposure"] = min(0.90, 0.40 + len(pii) * 0.10)
            ds_subs["data_confidentiality"] = 0.55
            coverage += 2
        if ds_subs:
            metrics["DS"] = AIVSSMetricScore("DS", ds_subs, _composite(ds_subs), len(ds_subs))

        cs_subs: Dict[str, float] = {}
        if pii:
            cs_subs["sensitive_data_disclosure"] = 0.70
            coverage += 1
        if d5.get("cross_boundary_nodes"):
            cs_subs["loss_governance"] = 0.55
            coverage += 1
        if cs_subs:
            metrics["CS"] = AIVSSMetricScore("CS", cs_subs, _composite(cs_subs), len(cs_subs))

        ei_subs: Dict[str, float] = {}
        if d5.get("cross_boundary_nodes"):
            ei_subs["privacy_violation"] = 0.40
            coverage += 1
        if arc_scores:
            soc_score = arc_scores.get("SOC", arc_scores.get("FAIR", 0))
            if isinstance(soc_score, (int, float)) and float(soc_score) > 60:
                ei_subs["societal_harm"] = 0.55
                coverage += 1
        if ei_subs:
            metrics["EI"] = AIVSSMetricScore("EI", ei_subs, _composite(ei_subs), len(ei_subs))

        gv_subs: Dict[str, float] = {}
        if d4.get("tool_errors"):
            gv_subs["compliance"] = 0.30
            coverage += 1
        if gv_subs:
            metrics["GV"] = AIVSSMetricScore("GV", gv_subs, _composite(gv_subs), len(gv_subs))

        composite = _flow_composite(metrics)
        return AIVSSFlowScore(metrics, composite, _severity(composite), min(100, coverage * 8))

    # ---- per-threat --------------------------------------------------------

    def score_per_threat(self, ground_truth: dict) -> List[AIVSSThreatScore]:
        results: List[AIVSSThreatScore] = []
        rapids = ground_truth.get("rapids_scores", {})
        attack_paths = ground_truth.get("expected_attack_paths", [])

        for path in attack_paths:
            techniques = path.get("techniques", [])
            path_id = path.get("id", "")
            path_name = path.get("title", path_id)

            metric_max: Dict[str, Dict[str, float]] = {}
            for tech in techniques:
                tid = tech if isinstance(tech, str) else tech.get("id", "")
                for (metric, sub, score) in _TECHNIQUE_AIVSS_MAP.get(tid, []):
                    current = metric_max.setdefault(metric, {}).get(sub, 0.0)
                    metric_max[metric][sub] = max(current, score)

            for rapids_cat, mappings in _RAPIDS_AIVSS_MAP.items():
                risk_val = rapids.get(rapids_cat, {})
                if isinstance(risk_val, dict):
                    risk_pct = risk_val.get("score", risk_val.get("risk_score", 0))
                elif isinstance(risk_val, (int, float)):
                    risk_pct = risk_val
                else:
                    continue
                r_score = _rapids_risk_to_score(float(risk_pct))
                for (metric, sub) in mappings:
                    current = metric_max.setdefault(metric, {}).get(sub, 0.0)
                    metric_max[metric][sub] = max(current, r_score)

            if not metric_max:
                continue

            def_val = rapids.get("defensibility", rapids.get("overall_defensibility", 50))
            if isinstance(def_val, dict):
                def_val = def_val.get("score", 50)
            mult = _defensibility_to_multiplier(float(def_val))

            metric_composites = [_composite(subs) for subs in metric_max.values()]
            raw_composite = max(metric_composites) if metric_composites else 0.0
            adjusted = min(10.0, raw_composite * mult)

            top_metric = max(metric_max, key=lambda m: _composite(metric_max[m]))

            results.append(AIVSSThreatScore(
                technique_id=path_id,
                technique_name=path_name,
                composite=adjusted,
                severity=_severity(adjusted),
                top_metric=top_metric,
                mitigation_multiplier=mult,
            ))

        return results

    # ---- per-agent ---------------------------------------------------------

    def score_per_agent(
        self,
        critic_name: str,
        identity_signals: dict,
        moe_result=None,
    ) -> AIVSSFlowScore:
        metrics: Dict[str, AIVSSMetricScore] = {}
        coverage = 0

        tool_calls = identity_signals.get("critic_tool_calls", {}).get(critic_name, 0)
        tool_errors = [
            e for e in identity_signals.get("tool_errors", [])
            if critic_name in str(e)
        ]

        aa_subs: Dict[str, float] = {}
        if tool_calls > 5:
            aa_subs["multi_step_authority"] = min(0.70, tool_calls * 0.05)
            coverage += 1
        if aa_subs:
            metrics["AA"] = AIVSSMetricScore("AA", aa_subs, _composite(aa_subs), len(aa_subs))

        ll_subs: Dict[str, float] = {}
        if tool_errors:
            ll_subs["operational_security"] = min(0.70, len(tool_errors) * 0.20)
            coverage += 1
        if ll_subs:
            metrics["LL"] = AIVSSMetricScore("LL", ll_subs, _composite(ll_subs), len(ll_subs))

        composite = _flow_composite(metrics)
        return AIVSSFlowScore(metrics, composite, _severity(composite), min(100, coverage * 20))

    # ---- main compute ------------------------------------------------------

    def compute(
        self,
        governance_signals: dict,
        ground_truth: dict,
        moe_result=None,
        sm_result=None,
    ) -> AIVSSScore:
        inbound  = self.score_inbound(governance_signals)
        internal = self.score_internal(governance_signals, moe_result, sm_result)
        outbound = self.score_outbound(
            governance_signals,
            arc_scores=ground_truth.get("arc_scores"),
        )
        per_threat = self.score_per_threat(ground_truth)

        identity = governance_signals.get("identity_integrity", {})
        per_agent: Dict[str, AIVSSFlowScore] = {}
        for critic in ["architect", "tester", "red_team", "purple_team", "blackhat"]:
            agent_score = self.score_per_agent(critic, identity, moe_result)
            if agent_score.composite > 0 or agent_score.metrics:
                per_agent[critic] = agent_score

        weights = _INDUSTRY_WEIGHTS.get(self.industry, _INDUSTRY_WEIGHTS[_DEFAULT_INDUSTRY])
        overall = (
            inbound.composite  * weights["w_inbound"]  +
            internal.composite * weights["w_internal"] +
            outbound.composite * weights["w_outbound"]
        )
        overall = min(10.0, overall)

        avg_cov = (inbound.coverage_pct + internal.coverage_pct + outbound.coverage_pct) // 3

        return AIVSSScore(
            inbound=inbound,
            internal=internal,
            outbound=outbound,
            per_threat=per_threat,
            per_agent=per_agent,
            overall=round(overall, 2),
            overall_severity=_severity(overall),
            industry=self.industry,
            coverage_pct=avg_cov,
        )


# ---------------------------------------------------------------------------
# Per-agent gate
# ---------------------------------------------------------------------------

class AIVSSAgentGate:
    """Apply standing per-critic config; tighten critics when inbound score is HIGH/CRITICAL."""

    def __init__(self, critic_settings: Optional[dict] = None):
        self.critic_settings: dict = critic_settings or {}

    def configure_critic(self, critic_agent, critic_role: str) -> None:
        cs = self.critic_settings.get(critic_role)
        if not cs:
            return
        allowed_models = getattr(cs, "allowed_models", [])
        if allowed_models and hasattr(critic_agent, "model"):
            if critic_agent.model and critic_agent.model not in allowed_models:
                logger.info(
                    f"AIVSS gate: constraining {critic_role} model to {allowed_models[0]}"
                )
                critic_agent.model = allowed_models[0]
        allowed_tools = getattr(cs, "allowed_tools", [])
        if allowed_tools and hasattr(critic_agent, "tools") and critic_agent.tools:
            critic_agent.tools = [t for t in critic_agent.tools if t.name in allowed_tools]

    def tighten(self, orchestrator, inbound: AIVSSFlowScore) -> None:
        if orchestrator is None:
            return
        score = inbound.composite
        critics = [
            getattr(orchestrator, "architect", None),
            getattr(orchestrator, "tester", None),
            getattr(orchestrator, "red_team", None),
            getattr(orchestrator, "purple_team", None),
        ]
        if score >= 9.0:
            logger.warning(
                f"AIVSS inbound {score:.1f} CRITICAL — disabling tools + forcing smallest allowed model"
            )
            for c in critics:
                if c is None:
                    continue
                c._tools_enabled = False
                cs = self.critic_settings.get(getattr(c, "role", ""))
                if cs:
                    allowed = getattr(cs, "allowed_models", [])
                    if allowed:
                        c.model = allowed[-1]
        elif score >= 7.0:
            logger.warning(f"AIVSS inbound {score:.1f} HIGH — disabling tools on all critics")
            for c in critics:
                if c is not None:
                    c._tools_enabled = False

    def check_tool_allowed(
        self,
        critic_name: str,
        tool_name: str,
        critic_settings=None,
    ) -> bool:
        cs = critic_settings or self.critic_settings.get(critic_name)
        if not cs:
            return True
        allowed = getattr(cs, "allowed_tools", [])
        return not allowed or tool_name in allowed
