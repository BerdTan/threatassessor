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
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

CONFIG_DIR = Path(__file__).parent
USER_CONFIG_PATH = CONFIG_DIR / "user_config.json"


# ---------------------------------------------------------------------------
# Section models
# ---------------------------------------------------------------------------

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
    # Architect critic score thresholds
    architect_pass_threshold: int = Field(default=90, ge=50, le=100,
        description="Architect score ≥ this = PASS (no confidence penalty)")
    architect_minor_gap_threshold: int = Field(default=80, ge=50, le=100,
        description="Architect score ≥ this (but < pass) = MINOR_GAPS (−2% to −5%)")
    architect_major_gap_threshold: int = Field(default=70, ge=0, le=100,
        description="Architect score < this = MAJOR_GAPS (−10% confidence)")
    # Tester critic score thresholds
    tester_pass_threshold: int = Field(default=85, ge=50, le=100,
        description="Tester score ≥ this = PASS (no confidence penalty)")
    tester_minor_gap_threshold: int = Field(default=75, ge=50, le=100,
        description="Tester score ≥ this (but < pass) = MINOR_GAPS (−1% to −3%)")
    tester_major_gap_threshold: int = Field(default=65, ge=0, le=100,
        description="Tester score < this = MAJOR_GAPS (−5% confidence)")
    # Red team critic thresholds (inverted: high score = easy to exploit = bad)
    red_team_hard_threshold: int = Field(default=40, ge=0, le=100,
        description="Red team score ≤ this = hard to exploit (no penalty)")
    red_team_medium_threshold: int = Field(default=55, ge=0, le=100,
        description="Red team score ≤ this (but > hard) = medium exploitability (−3% to −6%)")
    red_team_easy_threshold: int = Field(default=70, ge=0, le=100,
        description="Red team score > this = easy to exploit (−10% confidence)")

    @model_validator(mode="after")
    def check_critic_threshold_order(self) -> "MoESettings":
        if not (self.architect_major_gap_threshold < self.architect_minor_gap_threshold < self.architect_pass_threshold):
            raise ValueError("Architect thresholds must satisfy: major_gap < minor_gap < pass")
        if not (self.tester_major_gap_threshold < self.tester_minor_gap_threshold < self.tester_pass_threshold):
            raise ValueError("Tester thresholds must satisfy: major_gap < minor_gap < pass")
        if not (self.red_team_hard_threshold < self.red_team_medium_threshold < self.red_team_easy_threshold):
            raise ValueError("Red team thresholds must satisfy: hard < medium < easy")
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
        default=["ai_ml_arc"],
        description="Pattern IDs to register and run during analysis. Only 'ai_ml_arc' is currently active."
    )

    @model_validator(mode="after")
    def check_known_patterns(self) -> "PatternsSettings":
        from chatbot.config.patterns_catalog import AVAILABLE_PATTERNS
        unknown = [p for p in self.enabled_patterns if p not in AVAILABLE_PATTERNS]
        if unknown:
            raise ValueError(f"Unknown pattern ID(s): {unknown}. Valid: {list(AVAILABLE_PATTERNS)}")
        return self


class AppSettings(BaseModel):
    engine: AnalysisEngineSettings = Field(default_factory=AnalysisEngineSettings)
    confidence: ConfidenceSettings = Field(default_factory=ConfidenceSettings)
    completeness: CompletenessSettings = Field(default_factory=CompletenessSettings)
    residual_risk: ResidualRiskSettings = Field(default_factory=ResidualRiskSettings)
    moe: MoESettings = Field(default_factory=MoESettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    system: SystemSettings = Field(default_factory=SystemSettings)
    patterns: PatternsSettings = Field(default_factory=PatternsSettings)


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
        defaults = AppSettings()
        diff: dict = {}
        for section_name, section_model in new_settings:
            default_section = getattr(defaults, section_name)
            section_diff: dict = {}
            for field_name, value in section_model:
                if value != getattr(default_section, field_name):
                    section_diff[field_name] = value
            if section_diff:
                diff[section_name] = section_diff
        USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_CONFIG_PATH.write_text(json.dumps(diff, indent=2))
        _settings = new_settings


def update_settings(partial: dict) -> AppSettings:
    """Merge a partial dict into current settings, validate, persist, and reload singleton."""
    current = get_settings().model_dump()
    patterns_changed = "patterns" in partial
    for section, values in partial.items():
        if section in current and isinstance(values, dict):
            current[section].update(values)
    new_settings = AppSettings.model_validate(current)
    save_settings(new_settings)
    # Invalidate the pattern registry singleton when pattern settings change
    # so create_default_registry() picks up the new enabled_patterns list.
    if patterns_changed:
        try:
            from chatbot.modules.pattern_registry import reset_pattern_registry
            reset_pattern_registry()
        except Exception:
            pass
    return new_settings
