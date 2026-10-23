"""
DirectorCaster — simulation orchestrator for TA Perspective.

Sits between GroupCampaignMatcher output (already embedded in ground_truth) and
PerspectiveRunner. No LLM calls. Fully deterministic.

Three outputs:
    ScenarioManifest  — all attack paths ranked by composite_risk_score
    SimulationBounds  — technique + node guardrails for one selected scenario
    PacingSignals     — per-step timing hints for the kill chain canvas

composite_risk_score = (1 - block_rate) * 0.5 + actor_confidence * 0.3 + aivss_path_weight * 0.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ── Constants ──────────────────────────────────────────────────────────────────

_STEP_DELAY_NOMINAL_MS = 1200
_STEP_DELAY_CRITICAL_MS = 2400

_RISK_BADGE = {
    (0.75, 1.01): "CRITICAL",
    (0.50, 0.75): "HIGH",
    (0.25, 0.50): "MED",
    (0.00, 0.25): "LOW",
}


def _risk_badge(score: float) -> str:
    for (lo, hi), label in _RISK_BADGE.items():
        if lo <= score < hi:
            return label
    return "LOW"


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class ScenarioEntry:
    scenario_id: str            # e.g. "AP-1"
    path_label: str             # human-readable "internet → api_gw → db"
    composite_risk_score: float # 0.0–1.0
    risk_badge: str             # CRITICAL / HIGH / MED / LOW
    block_rate_estimate: float  # fraction of path techniques with present mitigations
    actor_overlap_pct: float    # top matched actor's overlap (0 if none)
    actor_name: str             # top matched actor name (empty if none)
    risk_rationale: str         # short explanatory string for hover tooltip

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "path_label": self.path_label,
            "composite_risk_score": round(self.composite_risk_score, 4),
            "risk_badge": self.risk_badge,
            "block_rate_estimate": round(self.block_rate_estimate, 4),
            "actor_overlap_pct": round(self.actor_overlap_pct, 4),
            "actor_name": self.actor_name,
            "risk_rationale": self.risk_rationale,
        }


@dataclass
class ScenarioManifest:
    scenarios: list[ScenarioEntry]
    arch_actors: list[dict]     # arch-level top actors from ground_truth["threat_actors"]

    def to_dict(self) -> dict:
        return {
            "scenarios": [s.to_dict() for s in self.scenarios],
            "arch_actors": self.arch_actors,
        }

    def get(self, scenario_id: str) -> Optional[ScenarioEntry]:
        for s in self.scenarios:
            if s.scenario_id == scenario_id:
                return s
        return None


@dataclass
class SimulationBounds:
    scenario_id: str
    technique_set: set[str]     # union of per_node_techniques for this path
    node_set: list[str]         # ordered node IDs along the path
    actor: dict                 # top matched actor dict (may be empty {})

    def allows_technique(self, technique: str) -> bool:
        return technique in self.technique_set

    def allows_node(self, node_id: str) -> bool:
        return node_id in self.node_set


@dataclass
class StepPacing:
    node_id: str
    technique: str
    pause_at_critical: bool
    step_delay_ms: int


@dataclass
class PacingSignals:
    scenario_id: str
    steps: list[StepPacing]

    def for_node(self, node_id: str) -> Optional[StepPacing]:
        for s in self.steps:
            if s.node_id == node_id:
                return s
        return None


# ── Block-rate estimator ───────────────────────────────────────────────────────

def _estimate_block_rate(ap: dict, controls_present: set[str], control_recommendations: list[dict]) -> float:
    """
    Fraction of this path's techniques that have at least one present mitigation.

    A technique is "blocked" when any recommendation covers it AND that
    recommendation's control is in controls_present.
    """
    path_techs = set(ap.get("techniques", []))
    if not path_techs:
        return 0.0

    # Build: technique → set of controls that address it
    tech_to_controls: dict[str, set[str]] = {}
    for rec in control_recommendations:
        ctrl = rec.get("control", "").lower().strip()
        if not ctrl:
            continue
        for t in rec.get("techniques", []):
            tech_to_controls.setdefault(t, set()).add(ctrl)

    # Normalise controls_present for case-insensitive match
    cp_lower = {c.lower().strip() for c in controls_present}

    blocked = sum(
        1 for t in path_techs
        if tech_to_controls.get(t, set()) & cp_lower
    )
    return blocked / len(path_techs)


# ── Normalise criticalities ────────────────────────────────────────────────────

def _normalise_criticalities(attack_paths: list[dict]) -> dict[str, float]:
    """Map AP id → criticality normalised to [0, 1] across all paths."""
    crits = {ap.get("id", str(i)): float(ap.get("criticality", 0.5))
             for i, ap in enumerate(attack_paths)}
    max_c = max(crits.values(), default=1.0) or 1.0
    return {k: v / max_c for k, v in crits.items()}


# ── Risk rationale builder ─────────────────────────────────────────────────────

def _build_rationale(ap: dict, block_rate: float, actor_name: str, actor_overlap: float, score: float) -> str:
    techs = ap.get("techniques", [])
    gaps = max(0, round(len(techs) * (1 - block_rate)))
    parts = []
    if gaps:
        parts.append(f"{gaps} unmitigated technique{'s' if gaps != 1 else ''}")
    if actor_name:
        parts.append(f"{actor_name} {actor_overlap:.0%} TTP overlap")
    parts.append(f"risk score {score:.2f}")
    return "; ".join(parts) if parts else f"risk score {score:.2f}"


# ── Main DirectorCaster ────────────────────────────────────────────────────────

class DirectorCaster:
    """
    Build ScenarioManifest, SimulationBounds, and PacingSignals from ground_truth.

    Usage:
        dc = DirectorCaster(ground_truth)
        manifest = dc.build_manifest()
        bounds   = dc.build_bounds("AP-1")
        pacing   = dc.build_pacing(bounds)
    """

    def __init__(self, ground_truth: dict) -> None:
        self._gt = ground_truth
        self._attack_paths: list[dict] = ground_truth.get("expected_attack_paths", [])
        self._controls_present: set[str] = set(ground_truth.get("controls_present", []))
        self._control_recs: list[dict] = ground_truth.get("control_recommendations", [])
        self._arch_actors: list[dict] = ground_truth.get("threat_actors") or []
        self._norm_crits = _normalise_criticalities(self._attack_paths)

    # ── ScenarioManifest ──────────────────────────────────────────────────────

    def build_manifest(self) -> ScenarioManifest:
        entries: list[ScenarioEntry] = []

        for ap in self._attack_paths:
            ap_id = ap.get("id", f"AP-{len(entries)+1}")
            path_nodes: list = ap.get("path", [])
            entry_label = ap.get("entry", path_nodes[0] if path_nodes else "entry")
            target_label = ap.get("target", path_nodes[-1] if path_nodes else "target")
            path_label = f"{entry_label} → {target_label}"

            block_rate = _estimate_block_rate(ap, self._controls_present, self._control_recs)

            # Actor confidence: top path-level actor, fall back to arch-level
            matched = ap.get("matched_actors") or self._arch_actors
            top_actor = matched[0] if matched else {}
            actor_confidence = float(top_actor.get("overlap_pct", 0.0))
            actor_name = top_actor.get("name", "")

            aivss_weight = self._norm_crits.get(ap_id, float(ap.get("criticality", 0.5)))

            score = round(
                (1 - block_rate) * 0.5 + actor_confidence * 0.3 + aivss_weight * 0.2,
                4,
            )

            rationale = _build_rationale(ap, block_rate, actor_name, actor_confidence, score)

            entries.append(ScenarioEntry(
                scenario_id=ap_id,
                path_label=path_label,
                composite_risk_score=score,
                risk_badge=_risk_badge(score),
                block_rate_estimate=round(block_rate, 4),
                actor_overlap_pct=round(actor_confidence, 4),
                actor_name=actor_name,
                risk_rationale=rationale,
            ))

        entries.sort(key=lambda e: e.composite_risk_score, reverse=True)
        return ScenarioManifest(scenarios=entries, arch_actors=self._arch_actors)

    # ── SimulationBounds ──────────────────────────────────────────────────────

    def build_bounds(self, scenario_id: str) -> SimulationBounds:
        """
        Build guardrails for a specific scenario.
        PerspectiveRunner must not emit signals outside these bounds.
        """
        ap = self._find_ap(scenario_id)
        if ap is None:
            return SimulationBounds(
                scenario_id=scenario_id,
                technique_set=set(),
                node_set=[],
                actor={},
            )

        per_node: dict = ap.get("per_node_techniques", {})
        technique_set: set[str] = set()
        for techs in per_node.values():
            technique_set.update(techs)
        # Also include base techniques (some paths may not have per_node populated)
        technique_set.update(ap.get("techniques", []))

        matched = ap.get("matched_actors") or self._arch_actors
        top_actor = matched[0] if matched else {}

        return SimulationBounds(
            scenario_id=scenario_id,
            technique_set=technique_set,
            node_set=list(ap.get("path", [])),
            actor=top_actor,
        )

    # ── PacingSignals ─────────────────────────────────────────────────────────

    def build_pacing(self, bounds: SimulationBounds) -> PacingSignals:
        """
        Pre-compute per-step pacing for a simulation run.

        A step is "critical" when the node's technique is in the actor's
        known matched_techniques (i.e. the actor is known to use this exact TTP).
        """
        ap = self._find_ap(bounds.scenario_id)
        if ap is None:
            return PacingSignals(scenario_id=bounds.scenario_id, steps=[])

        actor_techs: set[str] = set(bounds.actor.get("matched_techniques", []))
        per_node: dict = ap.get("per_node_techniques", {})

        steps: list[StepPacing] = []
        for node_id in bounds.node_set:
            node_techs = set(per_node.get(node_id, []))
            # Primary technique for this node: first in set, or empty
            primary_tech = next(iter(node_techs & bounds.technique_set), "")
            is_critical = bool(node_techs & actor_techs)
            steps.append(StepPacing(
                node_id=node_id,
                technique=primary_tech,
                pause_at_critical=is_critical,
                step_delay_ms=_STEP_DELAY_CRITICAL_MS if is_critical else _STEP_DELAY_NOMINAL_MS,
            ))

        return PacingSignals(scenario_id=bounds.scenario_id, steps=steps)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _find_ap(self, scenario_id: str) -> Optional[dict]:
        for ap in self._attack_paths:
            if ap.get("id") == scenario_id:
                return ap
        return None
