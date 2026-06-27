"""
ThreatAssessor configuration — persistent, live-editable settings.

Defaults match all previously-hardcoded values so existing behaviour is
unchanged when no user_config.json is present.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

CONFIG_DIR = Path(__file__).parent
USER_CONFIG_PATH = CONFIG_DIR / "user_config.json"


# ---------------------------------------------------------------------------
# Section models
# ---------------------------------------------------------------------------

class RAPIDSCategoryWeights(BaseModel):
    """Per-category multipliers for RAPIDS risk averaging (default 1.0 = equal weight).

    Range 0.5–2.0 per category. A value of 1.1 means that category contributes
    +10% more to the overall risk score. Apply ScrumMaster engine hints here
    to make the baseline engine score specific threat types more aggressively.
    """
    ransomware:       float = Field(default=1.0, ge=0.5, le=2.0, description="Ransomware / encryption attack threat weight")
    application_vulns: float = Field(default=1.0, ge=0.5, le=2.0, description="Application vulnerability / exfiltration threat weight")
    phishing:         float = Field(default=1.0, ge=0.5, le=2.0, description="Phishing / social engineering / detection gap weight")
    insider_threat:   float = Field(default=1.0, ge=0.5, le=2.0, description="Insider threat / lateral movement / privilege escalation weight")
    dos:              float = Field(default=1.0, ge=0.5, le=2.0, description="Denial-of-service / availability threat weight")
    supply_chain:     float = Field(default=1.0, ge=0.5, le=2.0, description="Supply chain / third-party / vendor risk weight")


class AnalysisEngineSettings(BaseModel):
    max_paths: int = Field(default=10, ge=1, le=50,
        description="Maximum attack paths explored during BFS graph traversal")
    top_n: int = Field(default=5, ge=1, le=20,
        description="Top-N critical paths kept after ranking and deduplication")
    weight_target: float = Field(default=0.35, ge=0.0, le=1.0,
        description="Composite score weight for target node sensitivity")
    weight_length: float = Field(default=0.25, ge=0.0, le=1.0,
        description="Composite score weight for path hop count (shorter = riskier)")
    weight_control: float = Field(default=0.25, ge=0.0, le=1.0,
        description="Composite score weight for control coverage on path")
    weight_entry: float = Field(default=0.15, ge=0.0, le=1.0,
        description="Composite score weight for entry point exposure level")
    criticality_critical: float = Field(default=0.80, ge=0.0, le=1.0,
        description="Minimum composite score to classify a path as CRITICAL")
    criticality_high: float = Field(default=0.60, ge=0.0, le=1.0,
        description="Minimum composite score to classify a path as HIGH")
    criticality_medium: float = Field(default=0.40, ge=0.0, le=1.0,
        description="Minimum composite score to classify a path as MEDIUM")
    did_reduction_factor: float = Field(default=40.0, ge=0.0, le=100.0,
        description="Risk reduction points awarded per defense-in-depth tier")
    did_bonus_factor: float = Field(default=35.0, ge=0.0, le=100.0,
        description="Defensibility bonus points per defense-in-depth tier")
    path_risk_per_path: int = Field(default=3, ge=0, le=20,
        description="Risk points added per discovered attack path")
    path_risk_cap: int = Field(default=15, ge=0, le=50,
        description="Maximum total risk points from attack paths combined")
    rapids_category_weights: RAPIDSCategoryWeights = Field(
        default_factory=RAPIDSCategoryWeights,
        description="Per-category RAPIDS risk multipliers. Adjust to reflect architecture-specific "
                    "threat relevance. Apply ScrumMaster engine hints here for the next analysis run."
    )

    @model_validator(mode="after")
    def check_weight_sum(self) -> "AnalysisEngineSettings":
        total = self.weight_target + self.weight_length + self.weight_control + self.weight_entry
        if not (0.95 <= total <= 1.05):
            raise ValueError(
                f"Path criticality weights must sum to ~1.0 (got {total:.3f}). "
                "Adjust weight_target, weight_length, weight_control, weight_entry."
            )
        return self

    @model_validator(mode="after")
    def check_criticality_order(self) -> "AnalysisEngineSettings":
        if not (self.criticality_medium < self.criticality_high < self.criticality_critical):
            raise ValueError(
                "Criticality thresholds must satisfy: medium < high < critical"
            )
        return self


class ConfidenceSettings(BaseModel):
    base_confidence_floor: float = Field(default=0.72, ge=0.5, le=0.99,
        description="Minimum possible base confidence before expert adjustments")
    base_confidence_ceiling: float = Field(default=0.995, ge=0.5, le=1.0,
        description="Maximum possible base confidence before expert adjustments")
    node_penalty_factor: float = Field(default=0.15, ge=0.0, le=0.5,
        description="Confidence penalty weight for node count complexity")
    node_saturation: int = Field(default=20, ge=5, le=100,
        description="Node count at which the node complexity penalty saturates")
    edge_penalty_factor: float = Field(default=0.10, ge=0.0, le=0.5,
        description="Confidence penalty weight for edge count complexity")
    edge_saturation: int = Field(default=40, ge=5, le=200,
        description="Edge count at which the edge complexity penalty saturates")
    max_complexity_penalty: float = Field(default=0.25, ge=0.0, le=0.5,
        description="Maximum total complexity penalty (node + edge combined)")


class CompletenessSettings(BaseModel):
    technique_coverage_threshold: float = Field(default=0.80, ge=0.0, le=1.0,
        description="Fraction of identified MITRE techniques that must have a mapped control")


class ResidualRiskSettings(BaseModel):
    min_failure_probability: float = Field(default=0.10, ge=0.01, le=0.5,
        description="Minimum residual risk floor (10% = 1-in-10 residual failure rate)")
    accept_threshold: int = Field(default=10, ge=0, le=50,
        description="Residual risk score below which risk is ACCEPTED (no action needed)")
    monitor_threshold: int = Field(default=20, ge=0, le=100,
        description="Residual risk score below which risk is MONITORED (above = MITIGATE)")

    @model_validator(mode="after")
    def check_threshold_order(self) -> "ResidualRiskSettings":
        if not (self.accept_threshold < self.monitor_threshold):
            raise ValueError("accept_threshold must be less than monitor_threshold")
        return self


class MoESettings(BaseModel):
    enabled: bool = Field(default=True,
        description="Master switch: enable the full MoE expert review chain (Layer 2A–2D). When False, only the deterministic engine runs.")
    base_confidence: float = Field(default=99.5, ge=50.0, le=100.0,
        description="Starting confidence percentage before expert critic adjustments")
    temperature_synthesis: float = Field(default=0.2, ge=0.0, le=2.0,
        description="LLM temperature for the Layer-3 orchestrator synthesis call")
    max_tokens_synthesis: int = Field(default=4000, ge=500, le=16000,
        description="Max tokens for the synthesis LLM call (higher = more complete reasoning)")
    complexity_threshold: int = Field(default=60, ge=10, le=200,
        description="Complexity score above which 'auto' critic mode uses sequential (not parallel)")
    critic_mode: Literal["sequential", "parallel", "auto"] = Field(default="sequential",
        description="How critic agents are executed: sequential (cross-referenced), parallel (faster), or auto")

    # Architect critic — sensitivity preset (expands to pass/minor/major thresholds)
    architect_sensitivity: Literal["lenient", "balanced", "strict"] = Field(default="balanced",
        description="Architect critic sensitivity. lenient = fewer gaps flagged; strict = more gaps flagged")
    architect_pass_threshold: int = Field(default=90, ge=50, le=100,
        description="Architect score ≥ this = PASS (no confidence penalty). Set automatically by architect_sensitivity.")
    architect_minor_gap_threshold: int = Field(default=80, ge=50, le=100,
        description="Architect score ≥ this (but < pass) = MINOR_GAPS (−2% to −5%). Set automatically by architect_sensitivity.")
    architect_major_gap_threshold: int = Field(default=70, ge=0, le=100,
        description="Architect score < this = MAJOR_GAPS (−10% confidence). Set automatically by architect_sensitivity.")

    # Tester critic — sensitivity preset
    tester_sensitivity: Literal["lenient", "balanced", "strict"] = Field(default="balanced",
        description="Tester critic sensitivity. lenient = fewer MITRE gaps flagged; strict = more gaps flagged")
    tester_pass_threshold: int = Field(default=85, ge=50, le=100,
        description="Tester score ≥ this = PASS. Set automatically by tester_sensitivity.")
    tester_minor_gap_threshold: int = Field(default=75, ge=50, le=100,
        description="Tester score ≥ this (but < pass) = MINOR_GAPS. Set automatically by tester_sensitivity.")
    tester_major_gap_threshold: int = Field(default=65, ge=0, le=100,
        description="Tester score < this = MAJOR_GAPS. Set automatically by tester_sensitivity.")

    # Red team critic — sensitivity preset (inverted: high score = easy to exploit = bad)
    red_team_sensitivity: Literal["lenient", "balanced", "strict"] = Field(default="balanced",
        description="Red Team critic sensitivity. lenient = only obvious exploits flagged; strict = any exploitability flagged")
    red_team_hard_threshold: int = Field(default=40, ge=0, le=100,
        description="Red team score ≤ this = hard to exploit (no penalty). Set automatically by red_team_sensitivity.")
    red_team_medium_threshold: int = Field(default=55, ge=0, le=100,
        description="Red team score ≤ this (but > hard) = medium exploitability. Set automatically by red_team_sensitivity.")
    red_team_easy_threshold: int = Field(default=70, ge=0, le=100,
        description="Red team score > this = easy to exploit (−10% confidence). Set automatically by red_team_sensitivity.")

    @model_validator(mode="after")
    def check_critic_threshold_order(self) -> "MoESettings":
        # Expand sensitivity presets into thresholds
        _arch_presets = {
            "lenient":  (80, 70, 60),   # pass, minor, major
            "balanced": (90, 80, 70),
            "strict":   (95, 85, 75),
        }
        _test_presets = {
            "lenient":  (75, 65, 55),
            "balanced": (85, 75, 65),
            "strict":   (92, 82, 72),
        }
        _rt_presets = {
            # hard, medium, easy — inverted scale (lower = harder to exploit)
            "lenient":  (50, 65, 80),
            "balanced": (40, 55, 70),
            "strict":   (30, 45, 60),
        }
        ap, amin, amaj = _arch_presets[self.architect_sensitivity]
        self.architect_pass_threshold = ap
        self.architect_minor_gap_threshold = amin
        self.architect_major_gap_threshold = amaj

        tp, tmin, tmaj = _test_presets[self.tester_sensitivity]
        self.tester_pass_threshold = tp
        self.tester_minor_gap_threshold = tmin
        self.tester_major_gap_threshold = tmaj

        rh, rm, re = _rt_presets[self.red_team_sensitivity]
        self.red_team_hard_threshold = rh
        self.red_team_medium_threshold = rm
        self.red_team_easy_threshold = re
        return self


class LLMSettings(BaseModel):
    temperature: float = Field(default=0.7, ge=0.0, le=2.0,
        description="Default LLM sampling temperature (lower = more deterministic)")
    max_tokens: int = Field(default=1000, ge=100, le=8000,
        description="Default max tokens per LLM response (higher = more complete)")


class SystemSettings(BaseModel):
    report_dir: str = Field(default="report",
        description="Path to output reports directory (absolute or relative to project root)")
    max_file_size_mb: int = Field(default=10, ge=1, le=100,
        description="Maximum uploaded architecture file size in megabytes")

    @model_validator(mode="after")
    def check_report_dir(self) -> "SystemSettings":
        p = self.report_dir
        if ".." in p or p.startswith("/etc") or p.startswith("/proc") or p.startswith("/sys"):
            raise ValueError(f"report_dir '{p}' is not permitted")
        return self


class PatternsSettings(BaseModel):
    enabled_patterns: List[str] = Field(
        default=["ai_ml_arc", "cloud"],
        description="Pattern IDs to register and run during analysis. Active: ai_ml_arc, cloud."
    )

    @model_validator(mode="after")
    def check_known_patterns(self) -> "PatternsSettings":
        from chatbot.config.patterns_catalog import AVAILABLE_PATTERNS
        unknown = [p for p in self.enabled_patterns if p not in AVAILABLE_PATTERNS]
        if unknown:
            raise ValueError(f"Unknown pattern ID(s): {unknown}. Valid: {list(AVAILABLE_PATTERNS)}")
        return self


class AIPatternSettings(BaseModel):
    """
    Control recommendation thresholds for the AIPattern (ARC Framework + MITRE ATLAS).

    These thresholds govern when a risk score is high enough to recommend a control
    as 'priority' vs 'medium'. The per-component base risks live in
    chatbot/data/arc/risks.yaml and are not exposed here — change the YAML for
    fine-grained per-component tuning.

    Raise thresholds to reduce noise (fewer priority flags) in low-sensitivity
    environments. Lower them for high-sensitivity or regulated AI deployments.
    """

    # ── Category entry threshold (applies to all ARC categories) ─────────────
    category_entry_threshold: int = Field(default=50, ge=0, le=100,
        description="Minimum risk score for a category to produce any control recommendation. "
                    "Categories scoring below this are silently skipped.")

    # ── Per-category priority thresholds ─────────────────────────────────────
    priority_threshold_integrity: int = Field(default=80, ge=0, le=100,
        description="Integrity risk score at or above which input_validation and prompt_filtering "
                    "are recommended as priority controls.")
    priority_threshold_safety: int = Field(default=85, ge=0, le=100,
        description="Safety risk score at or above which content_moderation and sandbox "
                    "are recommended as priority controls.")
    priority_threshold_security: int = Field(default=85, ge=0, le=100,
        description="Security risk score at or above which api_key_rotation and secrets_management "
                    "are recommended as priority controls.")
    priority_threshold_privacy: int = Field(default=80, ge=0, le=100,
        description="Privacy risk score at or above which pii_detection and data_loss_prevention "
                    "are recommended as priority controls.")
    floor_threshold_transparency: int = Field(default=60, ge=0, le=100,
        description="Transparency risk score at or above which logging and audit_trails are recommended.")
    floor_threshold_accountability: int = Field(default=70, ge=0, le=100,
        description="Accountability risk score at or above which human_oversight and incident_response "
                    "are recommended.")
    floor_threshold_resilience: int = Field(default=60, ge=0, le=100,
        description="Resilience risk score at or above which monitoring and robustness_testing "
                    "are recommended.")


class CloudPatternSettings(BaseModel):
    """
    Risk scoring parameters for the CloudPattern (CAVEAT + CCM).

    Base risks are the starting score (0-100) per threat category before any
    control reductions are applied. Control reduction values are subtracted when
    the named control is present. Floor values set the minimum risk when the
    listed controls are ALL absent.

    Adjust base risks upward for high-sensitivity environments (e.g. CII) or
    downward for environments with strong compensating controls already in place.
    """

    # ── Base risks per category ───────────────────────────────────────────
    base_risk_iam_abuse: int = Field(default=80, ge=0, le=100,
        description="Starting risk score for IAM abuse (privilege escalation, credential theft)")
    base_risk_data_exposure: int = Field(default=75, ge=0, le=100,
        description="Starting risk score for data exposure (storage misconfiguration, object ACL)")
    base_risk_api_abuse: int = Field(default=70, ge=0, le=100,
        description="Starting risk score for API abuse (gateway abuse, metadata SSRF, session theft)")
    base_risk_compute_abuse: int = Field(default=65, ge=0, le=100,
        description="Starting risk score for compute abuse (serverless, container escape, cryptomining)")
    base_risk_network_lateral: int = Field(default=60, ge=0, le=100,
        description="Starting risk score for lateral movement (VPC peering, cross-account trust)")
    base_risk_supply_chain: int = Field(default=65, ge=0, le=100,
        description="Starting risk score for supply chain (image poisoning, pipeline compromise)")
    base_risk_logging_gaps: int = Field(default=60, ge=0, le=100,
        description="Starting risk score for logging gaps (audit log tampering, CloudTrail disable)")

    # ── Control reduction amounts ─────────────────────────────────────────
    reduce_mfa: int = Field(default=20, ge=0, le=50,
        description="Risk reduction for iam_abuse when MFA is present")
    reduce_least_privilege: int = Field(default=15, ge=0, le=50,
        description="Risk reduction for iam_abuse when least_privilege is present")
    reduce_privileged_access_management: int = Field(default=15, ge=0, le=50,
        description="Risk reduction for iam_abuse when PAM is present")
    reduce_iam_audit: int = Field(default=10, ge=0, le=50,
        description="Risk reduction for iam_abuse when iam_audit is present")
    reduce_encryption: int = Field(default=15, ge=0, le=50,
        description="Risk reduction for data_exposure when encryption is present")
    reduce_bucket_policy: int = Field(default=20, ge=0, le=50,
        description="Risk reduction for data_exposure when bucket_policy is present")
    reduce_dlp: int = Field(default=10, ge=0, le=50,
        description="Risk reduction for data_exposure when DLP is present")
    reduce_waf: int = Field(default=15, ge=0, le=50,
        description="Risk reduction for api_abuse when WAF is present")
    reduce_api_gateway_auth: int = Field(default=20, ge=0, le=50,
        description="Risk reduction for api_abuse when api_gateway_auth is present")
    reduce_network_segmentation: int = Field(default=20, ge=0, le=50,
        description="Risk reduction for network_lateral when network_segmentation is present")
    reduce_cloudtrail: int = Field(default=20, ge=0, le=50,
        description="Risk reduction for logging_gaps when CloudTrail is present")
    reduce_siem: int = Field(default=10, ge=0, le=50,
        description="Risk reduction for logging_gaps when SIEM is present")

    # ── Missing-control risk floors ───────────────────────────────────────
    floor_iam_no_mfa_pam: int = Field(default=75, ge=0, le=100,
        description="Minimum iam_abuse risk when both MFA and PAM are absent")
    floor_data_no_encryption_policy: int = Field(default=70, ge=0, le=100,
        description="Minimum data_exposure risk when both encryption and bucket_policy are absent")
    floor_logging_no_trail_siem: int = Field(default=60, ge=0, le=100,
        description="Minimum logging_gaps risk when both CloudTrail and SIEM are absent")

    # ── Control recommendation thresholds ────────────────────────────────
    priority_threshold_iam: int = Field(default=75, ge=0, le=100,
        description="IAM risk score at or above which MFA/PAM controls are recommended as priority")
    priority_threshold_data: int = Field(default=70, ge=0, le=100,
        description="Data exposure risk score at or above which encryption/policy are priority")
    priority_threshold_api: int = Field(default=65, ge=0, le=100,
        description="API abuse risk score at or above which auth/WAF controls are priority")
    priority_threshold_compute: int = Field(default=60, ge=0, le=100,
        description="Compute abuse risk score at or above which scanning/runtime controls are priority")
    priority_threshold_network: int = Field(default=60, ge=0, le=100,
        description="Network lateral risk score at or above which segmentation is recommended")
    priority_threshold_logging: int = Field(default=55, ge=0, le=100,
        description="Logging gaps risk score at or above which CloudTrail is recommended")

    @model_validator(mode="after")
    def check_floors_vs_bases(self) -> "CloudPatternSettings":
        pairs = [
            ("floor_iam_no_mfa_pam", "base_risk_iam_abuse"),
            ("floor_data_no_encryption_policy", "base_risk_data_exposure"),
            ("floor_logging_no_trail_siem", "base_risk_logging_gaps"),
        ]
        for floor_field, base_field in pairs:
            floor_val = getattr(self, floor_field)
            base_val = getattr(self, base_field)
            if floor_val > base_val:
                raise ValueError(
                    f"{floor_field} ({floor_val}) must not exceed {base_field} ({base_val}) — "
                    "a floor above the base would always dominate, making the base meaningless"
                )
        return self


class StoryCasterSettings(BaseModel):
    llm_enrichment: bool = Field(default=False,
        description="Use LLM to enrich user story prose (default off — deterministic stories are generated regardless; LLM adds prose quality only)")


class NarrativesSettings(BaseModel):
    enabled: bool = Field(default=True,
        description="Add risk_scenario per AP and mitigation_narrative per control after deterministic analysis")
    llm_polish: bool = Field(default=False,
        description="Use LLM to smooth template narratives into prose (default off — zero extra LLM calls)")


class ThreatModelSettings(BaseModel):
    enabled: bool = Field(default=True,
        description="Build pattern-aware threat_model block in ground_truth and generate 09_threat_model.md")
    llm_polish: bool = Field(default=False,
        description="Use LLM to refine the threat model summary (default off)")


class ADRSettings(BaseModel):
    enabled: bool = Field(default=True,
        description="Generate Architecture Decision Records with risk delta and produce 10_adr_report.md")
    show_risk_delta: bool = Field(default=True,
        description="Include before/after/delta risk table in ADR report")


class BlackhatRubricWeights(BaseModel):
    cross_path_chain_feasibility: int = Field(default=30, ge=0, le=100,
        description="Weight for cross-path chain feasibility (can attacker chain AP-i → AP-j via shared pivot?)")
    least_resistance_path: int = Field(default=25, ge=0, le=100,
        description="Weight for least-resistance path (does partial-path combo bypass per-path controls?)")
    stealth_potential: int = Field(default=25, ge=0, le=100,
        description="Weight for stealth potential (Defense Evasion techniques → undetectable attacker advantage)")
    mitigation_chain_coverage: int = Field(default=20, ge=0, le=100,
        description="Weight for mitigation chain coverage (do per-path mitigations hold against combined chain?)")

    @model_validator(mode="after")
    def check_weights_sum(self) -> "BlackhatRubricWeights":
        total = (
            self.cross_path_chain_feasibility
            + self.least_resistance_path
            + self.stealth_potential
            + self.mitigation_chain_coverage
        )
        if total != 100:
            raise ValueError(f"Blackhat rubric weights must sum to 100 (got {total})")
        return self


class PurpleTeamSettings(BaseModel):
    enabled: bool = Field(default=True,
        description="Enable Purple Team critic (Layer 2D). Runs after 2A/2B/2C — before Blackhat (2E).")
    detection_focus: Literal["balanced", "detection", "coverage", "adr"] = Field(
        default="balanced",
        description="Which Purple Team lens to weight most: balanced | detection | coverage | adr"
    )


class ScrumMasterSettings(BaseModel):
    """ScrumMaster meta-critic (Layer 2F). Reads all critic outputs and works towards harmony."""
    enabled: bool = Field(default=False,
        description="Enable ScrumMaster meta-critic. Requires MoE expert review. "
                    "Reads all critic findings and drives confidence higher through "
                    "targeted re-triggering. Adds ~30–90s per run.")
    confidence_goal: int = Field(default=90, ge=50, le=99,
        description="Confidence % the ScrumMaster aims for before stopping re-triggers. "
                    "If the architecture cannot reach this naturally, redesign guidance is given instead.")
    max_improvement_rounds: int = Field(default=2, ge=1, le=4,
        description="How many rounds of critic re-triggering the ScrumMaster will attempt. "
                    "More rounds = higher potential confidence gain but longer runtime.")
    harmony_mode: Literal["balanced", "quick", "thorough"] = Field(default="balanced",
        description="balanced = up to 2 rounds, standard proposals | "
                    "quick = 1 round, fast turnaround | "
                    "thorough = up to 4 rounds, deeper proposals")

    @model_validator(mode="after")
    def apply_harmony_mode(self) -> "ScrumMasterSettings":
        if self.harmony_mode == "quick":
            self.max_improvement_rounds = 1
        elif self.harmony_mode == "thorough":
            self.max_improvement_rounds = 4
        return self


class BlackhatSettings(BaseModel):
    enabled: bool = Field(default=True,
        description="Enable Blackhat cross-path chain critic (Layer 2E — supreme critic). Requires MoE expert review.")
    stealth_techniques: List[str] = Field(
        default=["T1562", "T1070", "T1078", "T1036", "T1027"],
        description="MITRE technique IDs considered Defense Evasion / stealth indicators for stealth scoring"
    )
    rubric_weights: BlackhatRubricWeights = Field(default_factory=BlackhatRubricWeights)
    rubric_preset: Literal["balanced", "stealth_focused", "chain_focused", "mitigation_stress"] = Field(
        default="balanced",
        description=(
            "Named rubric preset. Setting this overrides rubric_weights: "
            "balanced=default, stealth_focused=stealth×40, chain_focused=chain×40, mitigation_stress=coverage×40"
        )
    )

    @model_validator(mode="after")
    def apply_preset(self) -> "BlackhatSettings":
        _presets = {
            "balanced":          (30, 25, 25, 20),
            "stealth_focused":   (20, 20, 40, 20),
            "chain_focused":     (40, 30, 15, 15),
            "mitigation_stress": (20, 20, 20, 40),
        }
        w = _presets.get(self.rubric_preset)
        if w:
            self.rubric_weights = BlackhatRubricWeights(
                cross_path_chain_feasibility=w[0],
                least_resistance_path=w[1],
                stealth_potential=w[2],
                mitigation_chain_coverage=w[3],
            )
        return self


class CriticSettings(BaseModel):
    allowed_models: List[str] = Field(default_factory=list, description="Allowed model IDs (empty = unrestricted)")
    allowed_tools: List[str] = Field(default_factory=list, description="Allowed tool names (empty = unrestricted)")
    max_aivss_score: float = Field(default=10.0, description="AIVSS gate threshold (10.0 = disabled)")


class AgentModelConfig(BaseModel):
    """Primary model + ordered fallback chain for a single agent."""
    model: str = Field(
        default="",
        description="Primary model string passed to llm_client.generate(model=...). "
                    "Empty string = use env-var LLM_PROVIDER default (backward-compat).",
    )
    fallbacks: List[str] = Field(
        default_factory=list,
        description="Ordered fallback model strings tried after primary fails.",
    )


class AgentSwarmConfig(BaseModel):
    """Per-agent model assignments for the full ThreatAssessor agent swarm.

    Defaults are empty strings so existing env-var behaviour is preserved when
    no explicit config is present — no breakage.
    """
    architect:        AgentModelConfig = Field(default_factory=AgentModelConfig)
    tester:           AgentModelConfig = Field(default_factory=AgentModelConfig)
    red_team:         AgentModelConfig = Field(default_factory=AgentModelConfig)
    purple_team:      AgentModelConfig = Field(default_factory=AgentModelConfig)
    blackhat:         AgentModelConfig = Field(default_factory=AgentModelConfig)
    storycaster:      AgentModelConfig = Field(default_factory=AgentModelConfig)
    scrum_master:     AgentModelConfig = Field(default_factory=AgentModelConfig)
    moe_orchestrator: AgentModelConfig = Field(default_factory=AgentModelConfig)
    threat_analyst:   AgentModelConfig = Field(default_factory=AgentModelConfig)


class GovernanceSettings(BaseModel):
    agt_enabled: bool = Field(
        default=False,
        description="Enable AGT policy engine (requires: pip install agent-governance-toolkit). "
                    "When False, InhouseGovernanceAdapter runs instead.",
    )
    mcp_governance_enabled: bool = Field(
        default=False,
        description="Govern MCP outbound capability calls via wrap_capability() (disabled by default).",
    )
    policy_path: str = Field(
        default="policies/agent_governance.yaml",
        description="Path to the AGT YAML policy file. Ignored when agt_enabled=False.",
    )
    save_signals_per_run: bool = Field(
        default=True,
        description="Write governance_signals.json to each report directory after every pipeline run.",
    )
    industry: str = Field(
        default="government_public",
        description="AIVSS industry profile (government_public | financial | healthcare | general).",
    )
    siem_webhook_url: Optional[str] = Field(
        default=None,
        description="Optional SIEM webhook URL (Splunk/ELK). Events always written to logs/siem.jsonl.",
    )


class AppSettings(BaseModel):
    engine: AnalysisEngineSettings = Field(default_factory=AnalysisEngineSettings)
    confidence: ConfidenceSettings = Field(default_factory=ConfidenceSettings)
    completeness: CompletenessSettings = Field(default_factory=CompletenessSettings)
    residual_risk: ResidualRiskSettings = Field(default_factory=ResidualRiskSettings)
    moe: MoESettings = Field(default_factory=MoESettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    system: SystemSettings = Field(default_factory=SystemSettings)
    patterns: PatternsSettings = Field(default_factory=PatternsSettings)
    ai_pattern: AIPatternSettings = Field(default_factory=AIPatternSettings)
    cloud_pattern: CloudPatternSettings = Field(default_factory=CloudPatternSettings)
    story_caster: StoryCasterSettings = Field(default_factory=StoryCasterSettings)
    narratives: NarrativesSettings = Field(default_factory=NarrativesSettings)
    threat_model: ThreatModelSettings = Field(default_factory=ThreatModelSettings)
    adr: ADRSettings = Field(default_factory=ADRSettings)
    purple_team: PurpleTeamSettings = Field(default_factory=PurpleTeamSettings)
    blackhat: BlackhatSettings = Field(default_factory=BlackhatSettings)
    scrum_master: "ScrumMasterSettings" = Field(default_factory=lambda: ScrumMasterSettings())
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    critics: Dict[str, CriticSettings] = Field(
        default_factory=dict,
        description="Per-critic AIVSS gate config keyed by critic role name.",
    )
    agent_models: AgentSwarmConfig = Field(
        default_factory=AgentSwarmConfig,
        description="Per-agent model assignments. HarnessModelGuardian reads this at pipeline start.",
    )


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

_settings: Optional[AppSettings] = None
_lock = threading.Lock()


def load_settings() -> AppSettings:
    """Load settings from user_config.json merged over defaults. Falls back to defaults on error."""
    global _settings
    with _lock:
        defaults = AppSettings()
        if USER_CONFIG_PATH.exists():
            try:
                overrides = json.loads(USER_CONFIG_PATH.read_text())
                merged = defaults.model_dump()
                for section, values in overrides.items():
                    if section in merged and isinstance(values, dict):
                        merged[section].update(values)
                _settings = AppSettings.model_validate(merged)
            except Exception:
                _settings = defaults
        else:
            _settings = defaults
    return _settings


def get_settings() -> AppSettings:
    """Return the live in-memory settings singleton, loading if not yet initialised."""
    global _settings
    if _settings is None:
        load_settings()
    return _settings


def save_settings(new_settings: AppSettings) -> None:
    """Persist only non-default values to user_config.json and update the singleton."""
    global _settings
    with _lock:
        defaults_dict  = AppSettings().model_dump()
        new_dict       = new_settings.model_dump()  # fully serialised (no nested models)
        diff: dict = {}
        for section_name, new_section in new_dict.items():
            default_section = defaults_dict.get(section_name, {})
            if not isinstance(new_section, dict) or not isinstance(default_section, dict):
                if new_section != default_section:
                    diff[section_name] = new_section
                continue
            section_diff: dict = {}
            for field_name, value in new_section.items():
                if value != default_section.get(field_name):
                    section_diff[field_name] = value
            if section_diff:
                diff[section_name] = section_diff
        USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_CONFIG_PATH.write_text(json.dumps(diff, indent=2))
        _settings = new_settings


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def update_settings(partial: dict) -> AppSettings:
    """Merge a partial dict into current settings, validate, persist, and reload singleton."""
    current = get_settings().model_dump()
    patterns_changed = "patterns" in partial
    cloud_pattern_changed = "cloud_pattern" in partial
    ai_pattern_changed = "ai_pattern" in partial
    for section, values in partial.items():
        if section in current and isinstance(values, dict):
            current[section] = _deep_merge(current[section], values)
    new_settings = AppSettings.model_validate(current)
    save_settings(new_settings)
    # Invalidate the pattern registry singleton when pattern list or cloud scoring
    # parameters change — forces CloudPattern to re-read its scoring tables from
    # the new settings on next instantiation.
    if patterns_changed or cloud_pattern_changed or ai_pattern_changed:
        try:
            from chatbot.modules.pattern_registry import reset_pattern_registry
            reset_pattern_registry()
        except Exception:
            pass
    return new_settings
