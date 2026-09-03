"""
Typed Pydantic models for ThreatAssessor outputs.

All models are standalone — no chatbot.* imports — so this module is safe to
ship in the mcp_connector PyPI package without pulling in the full TA codebase.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ── gate ──────────────────────────────────────────────────────────────────────

class GateResult(BaseModel):
    result: Literal["PASS", "BLOCK"]
    risk_level: str
    blocking_signals: List[str] = Field(default_factory=list)


# ── assessment ────────────────────────────────────────────────────────────────

class AttackPath(BaseModel):
    id: Optional[str] = None
    entry: str
    target: str
    criticality: Optional[str] = None
    techniques: List[str] = Field(default_factory=list)
    hop_count: Optional[int] = None


class ControlRecommendation(BaseModel):
    control: Optional[str] = None
    priority: Optional[str] = None
    score: Optional[float] = None


class AssessmentSection(BaseModel):
    risk_score_before: Optional[Dict[str, Any]] = None
    risk_score_after: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    val_pct: Optional[float] = None
    attack_paths: List[AttackPath] = Field(default_factory=list)
    mitre_techniques: List[str] = Field(default_factory=list)
    controls_recommended: List[ControlRecommendation] = Field(default_factory=list)


# ── TATB ─────────────────────────────────────────────────────────────────────

class TATBSection(BaseModel):
    threat: Optional[float] = None
    ttp: Optional[float] = None
    risk: Optional[float] = None
    plan: Optional[float] = None
    overall: Optional[float] = None


# ── governance ────────────────────────────────────────────────────────────────

class GovernanceSignals(BaseModel):
    exploitation_severity: Optional[str] = None
    manipulation_severity: Optional[str] = None
    leakage_flagged: Optional[bool] = None
    sovereignty_flagged: Optional[bool] = None
    cross_boundary_nodes: List[str] = Field(default_factory=list)


class GovernanceSection(BaseModel):
    aivss_composite: Optional[float] = None
    outbound_composite: Optional[float] = None
    risk_level: Optional[str] = None
    signals: GovernanceSignals = Field(default_factory=GovernanceSignals)


# ── OTM ───────────────────────────────────────────────────────────────────────

class OTMAsset(BaseModel):
    id: str
    name: str
    type: str


class OTMThreat(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    risk: Optional[str] = None
    mitre_techniques: List[str] = Field(default_factory=list)
    affected_assets: List[str] = Field(default_factory=list)


class OTMMitigation(BaseModel):
    id: str
    name: str
    priority: Optional[str] = None
    mitre_mitigations: List[str] = Field(default_factory=list)


class OTMSection(BaseModel):
    otm_version: str = "0.2.0"
    project: Dict[str, str] = Field(default_factory=dict)
    assets: List[OTMAsset] = Field(default_factory=list)
    threats: List[OTMThreat] = Field(default_factory=list)
    mitigations: List[OTMMitigation] = Field(default_factory=list)


# ── MoE consensus ─────────────────────────────────────────────────────────────

class CriticSummary(BaseModel):
    status: Optional[str] = None
    confidence: Optional[float] = None
    top_gap: Optional[str] = None


class MoEConsensus(BaseModel):
    confidence: Optional[float] = None
    redesign_required: bool = False
    critics: Dict[str, CriticSummary] = Field(default_factory=dict)


# ── full export bundle ────────────────────────────────────────────────────────

class TAExportBundle(BaseModel):
    schema_version: str = Field(alias="schema", default="ta-export/1.0")
    exported_at: str = ""
    architecture: Dict[str, Any] = Field(default_factory=dict)
    gate: GateResult
    assessment: AssessmentSection = Field(default_factory=AssessmentSection)
    tatb: TATBSection = Field(default_factory=TATBSection)
    governance: GovernanceSection = Field(default_factory=GovernanceSection)
    moe_consensus: MoEConsensus = Field(default_factory=MoEConsensus)
    detect_findings: List[Dict[str, Any]] = Field(default_factory=list)
    security_findings: List[Dict[str, Any]] = Field(default_factory=list)
    otm: OTMSection = Field(default_factory=OTMSection)

    model_config = {"populate_by_name": True}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TAExportBundle":
        return cls.model_validate(d)


# ── enrichment ────────────────────────────────────────────────────────────────

class ComponentContext(BaseModel):
    """TA threat context for one architecture component — embed in SAST/VAPT reports."""
    component_label: str
    attack_paths: List[AttackPath] = Field(default_factory=list)
    techniques: List[str] = Field(default_factory=list)
    risk_level: str = "UNKNOWN"
    controls_recommended: List[str] = Field(default_factory=list)
    match_confidence: float = 1.0

    def as_markdown(self) -> str:
        lines = [f"## TA Context: {self.component_label}",
                 f"**Risk level:** {self.risk_level}  "
                 f"**Match confidence:** {self.match_confidence:.0%}"]
        if self.attack_paths:
            lines.append("\n**Attack paths involving this component:**")
            for ap in self.attack_paths[:5]:
                lines.append(f"- `{ap.entry}` → `{ap.target}` "
                              f"({ap.criticality or 'N/A'}) — {', '.join(ap.techniques[:3])}")
        if self.techniques:
            lines.append(f"\n**Mapped MITRE techniques:** {', '.join(self.techniques[:10])}")
        if self.controls_recommended:
            lines.append("\n**Recommended controls:**")
            for c in self.controls_recommended[:5]:
                lines.append(f"- {c}")
        return "\n".join(lines)


__all__ = [
    "GateResult", "AttackPath", "ControlRecommendation",
    "AssessmentSection", "TATBSection",
    "GovernanceSignals", "GovernanceSection",
    "OTMAsset", "OTMThreat", "OTMMitigation", "OTMSection",
    "CriticSummary", "MoEConsensus",
    "TAExportBundle", "ComponentContext",
]
