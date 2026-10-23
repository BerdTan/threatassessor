"""
PerspectiveRunner — step-through kill chain simulator for TA Perspective.

Walks a selected attack path node by node, emitting PerspectiveStep events
for SSE streaming. Receives SimulationBounds from DirectorCaster — must not
emit techniques or nodes outside those bounds (emits UNKNOWN_NODE instead).

Outcome logic per step:
    BLOCKED   — mitigation present + DETECT rule covers the tactic → fully stopped
    DEGRADED  — mitigation OR detection, not both → slowed/detected but not stopped
    SUCCEEDED — neither → undetected gap
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Optional

from chatbot.modules.director_caster import PacingSignals, SimulationBounds

log = logging.getLogger(__name__)

_DEFAULT_STIX = Path(__file__).parent.parent / "data" / "enterprise-attack.json"
_DEFAULT_RULES = Path(__file__).parent.parent.parent / "policies" / "soc_detection_rules.yaml"
_TECH_TACTIC_PKL = _DEFAULT_STIX.with_suffix(".tech_tactic.pkl")

_STEP_DELAY_NOMINAL_MS = 1200
_STEP_DELAY_CRITICAL_MS = 2400

# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class PerspectiveStep:
    step: int
    node: str
    technique: str              # primary technique for this step; "UNKNOWN_NODE" if out-of-bounds
    outcome: str                # BLOCKED / DEGRADED / SUCCEEDED / UNKNOWN_NODE
    rule_fired: Optional[str]   # DETECT rule id, or None
    mitigation_present: bool
    pause_at_critical: bool
    red_position: str
    blue_position: str
    edge_from: Optional[str]
    edge_to: str
    step_delay_ms: int
    rationale: str

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "node": self.node,
            "technique": self.technique,
            "outcome": self.outcome,
            "rule_fired": self.rule_fired,
            "mitigation_present": self.mitigation_present,
            "pause_at_critical": self.pause_at_critical,
            "red_position": self.red_position,
            "blue_position": self.blue_position,
            "edge_from": self.edge_from,
            "edge_to": self.edge_to,
            "step_delay_ms": self.step_delay_ms,
            "rationale": self.rationale,
        }


@dataclass
class PerspectiveResult:
    scenario_id: str
    steps: list[PerspectiveStep]
    summary: dict = field(default_factory=dict)

    def __post_init__(self):
        outcomes = [s.outcome for s in self.steps]
        self.summary = {
            "total_steps": len(self.steps),
            "blocked": outcomes.count("BLOCKED"),
            "degraded": outcomes.count("DEGRADED"),
            "succeeded": outcomes.count("SUCCEEDED"),
            "unknown": outcomes.count("UNKNOWN_NODE"),
            "block_rate": (
                outcomes.count("BLOCKED") / len(outcomes) if outcomes else 0.0
            ),
        }


# ── Technique → tactic index ──────────────────────────────────────────────────

def _build_tech_tactic_index(stix_path: Path) -> dict[str, list[str]]:
    """
    Map ATT&CK technique T-ID → list of normalised tactic phase names.
    Caches as a pkl alongside the STIX file.
    """
    pkl = stix_path.with_suffix(".tech_tactic.pkl")
    if pkl.exists() and pkl.stat().st_mtime >= stix_path.stat().st_mtime:
        try:
            with open(pkl, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass

    log.info("PerspectiveRunner: building technique→tactic index")
    with open(stix_path) as f:
        data = json.load(f)

    index: dict[str, list[str]] = {}
    for o in data["objects"]:
        if o["type"] != "attack-pattern":
            continue
        tid = ""
        for ext in o.get("external_references", []):
            if ext.get("source_name") == "mitre-attack":
                candidate = ext.get("external_id", "")
                if candidate.startswith("T"):
                    tid = candidate
                    break
        if not tid:
            continue
        phases = [
            p["phase_name"].replace("-", "_")
            for p in o.get("kill_chain_phases", [])
            if p.get("kill_chain_name") == "mitre-attack"
        ]
        if phases:
            index[tid] = phases

    try:
        with open(pkl, "wb") as f:
            pickle.dump(index, f)
    except OSError:
        pass
    return index


# ── DETECT stage → rule index ─────────────────────────────────────────────────

def _build_stage_rule_index(rules_path: Path) -> dict[str, str]:
    """
    Map kill_chain_stage → first matching DETECT rule id.
    Lightweight — loads rules YAML once.
    """
    try:
        import yaml
        with open(rules_path) as f:
            data = yaml.safe_load(f)
        index: dict[str, str] = {}
        for rule in data.get("rules", []):
            stage = rule.get("kill_chain_stage", "")
            rule_id = rule.get("id", "")
            if stage and rule_id and stage not in index:
                index[stage] = rule_id
        return index
    except Exception as exc:
        log.warning("PerspectiveRunner: could not load DETECT rules: %s", exc)
        return {}


# ── Mitigation check ──────────────────────────────────────────────────────────

def _has_mitigation(
    technique: str,
    controls_present: set[str],
    control_recs: list[dict],
) -> bool:
    """True if any present control covers this technique."""
    cp_lower = {c.lower().strip() for c in controls_present}
    for rec in control_recs:
        if technique in rec.get("techniques", []):
            ctrl = rec.get("control", "").lower().strip()
            if ctrl in cp_lower:
                return True
    return False


# ── Rationale builder ─────────────────────────────────────────────────────────

def _step_rationale(
    technique: str,
    outcome: str,
    rule_id: Optional[str],
    mitigation_present: bool,
    actor_name: str,
) -> str:
    parts = [technique]
    if outcome == "BLOCKED":
        parts.append(f"blocked by mitigation + {rule_id}")
    elif outcome == "DEGRADED":
        if mitigation_present:
            parts.append("mitigation present but no detection coverage")
        else:
            parts.append(f"detected by {rule_id} but no mitigation")
    elif outcome == "SUCCEEDED":
        parts.append("no mitigation, no detection — gap")
    elif outcome == "UNKNOWN_NODE":
        parts.append("node outside simulation bounds")
    if actor_name and outcome in ("SUCCEEDED", "DEGRADED"):
        parts.append(f"{actor_name} known to use this TTP")
    return "; ".join(parts)


# ── PerspectiveRunner ─────────────────────────────────────────────────────────

class PerspectiveRunner:
    """
    Step-through kill chain simulator.

    Usage:
        runner = PerspectiveRunner(ground_truth)
        for step in runner.run(bounds, pacing):
            yield step.to_dict()   # stream as SSE
        result = runner.run_all(bounds, pacing)  # collect PerspectiveResult
    """

    def __init__(
        self,
        ground_truth: dict,
        stix_path: Path = _DEFAULT_STIX,
        rules_path: Path = _DEFAULT_RULES,
    ) -> None:
        self._gt = ground_truth
        self._controls_present: set[str] = set(ground_truth.get("controls_present", []))
        self._control_recs: list[dict] = ground_truth.get("control_recommendations", [])
        self._attack_paths: list[dict] = ground_truth.get("expected_attack_paths", [])

        self._tech_tactic = _build_tech_tactic_index(stix_path)
        self._stage_rule = _build_stage_rule_index(rules_path)

    # ── Public interface ──────────────────────────────────────────────────────

    def run(
        self,
        bounds: SimulationBounds,
        pacing: Optional[PacingSignals] = None,
    ) -> Generator[PerspectiveStep, None, None]:
        """Yield PerspectiveStep for each node along the path."""
        ap = self._find_ap(bounds.scenario_id)
        per_node: dict = ap.get("per_node_techniques", {}) if ap else {}
        actor_name = bounds.actor.get("name", "")
        blue_home = bounds.node_set[0] if bounds.node_set else ""
        blue_pos = blue_home
        prev_node: Optional[str] = None

        for i, node_id in enumerate(bounds.node_set):
            step_num = i + 1

            if not bounds.allows_node(node_id):
                yield self._unknown_step(step_num, node_id, prev_node, blue_pos)
                prev_node = node_id
                continue

            # Primary technique: first node technique within bounds, else UNKNOWN_NODE
            node_techs = set(per_node.get(node_id, []))
            in_bounds = node_techs & bounds.technique_set
            if not in_bounds:
                yield self._unknown_step(step_num, node_id, prev_node, blue_pos)
                prev_node = node_id
                continue

            primary_tech = sorted(in_bounds)[0]  # deterministic choice

            mitigation = _has_mitigation(primary_tech, self._controls_present, self._control_recs)
            rule_id = self._find_detect_rule(primary_tech)
            detect_active = rule_id is not None

            if mitigation and detect_active:
                outcome = "BLOCKED"
                blue_pos = prev_node or blue_home
            elif mitigation or detect_active:
                outcome = "DEGRADED"
                blue_pos = prev_node or blue_home
            else:
                outcome = "SUCCEEDED"
                # blue retreats home on undetected step
                blue_pos = blue_home

            step_pacing = pacing.for_node(node_id) if pacing else None
            pause = step_pacing.pause_at_critical if step_pacing else False
            delay = step_pacing.step_delay_ms if step_pacing else (
                _STEP_DELAY_CRITICAL_MS if pause else _STEP_DELAY_NOMINAL_MS
            )

            yield PerspectiveStep(
                step=step_num,
                node=node_id,
                technique=primary_tech,
                outcome=outcome,
                rule_fired=rule_id,
                mitigation_present=mitigation,
                pause_at_critical=pause,
                red_position=node_id,
                blue_position=blue_pos,
                edge_from=prev_node,
                edge_to=node_id,
                step_delay_ms=delay,
                rationale=_step_rationale(primary_tech, outcome, rule_id, mitigation, actor_name),
            )
            prev_node = node_id

    def run_all(
        self,
        bounds: SimulationBounds,
        pacing: Optional[PacingSignals] = None,
    ) -> PerspectiveResult:
        steps = list(self.run(bounds, pacing))
        return PerspectiveResult(scenario_id=bounds.scenario_id, steps=steps)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _find_ap(self, scenario_id: str) -> Optional[dict]:
        for ap in self._attack_paths:
            if ap.get("id") == scenario_id:
                return ap
        return None

    def _find_detect_rule(self, technique: str) -> Optional[str]:
        """Return the first DETECT rule id that covers this technique's tactic, or None."""
        # Check base technique first, then subtechnique parent
        for t in (technique, technique.split(".")[0]):
            for stage in self._tech_tactic.get(t, []):
                rule_id = self._stage_rule.get(stage)
                if rule_id:
                    return rule_id
        return None

    # ── Unknown-node helper ───────────────────────────────────────────────────

    @staticmethod
    def _unknown_step(
        step: int,
        node_id: str,
        prev_node: Optional[str],
        blue_pos: str,
    ) -> PerspectiveStep:
        return PerspectiveStep(
            step=step,
            node=node_id,
            technique="UNKNOWN_NODE",
            outcome="UNKNOWN_NODE",
            rule_fired=None,
            mitigation_present=False,
            pause_at_critical=False,
            red_position=node_id,
            blue_position=blue_pos,
            edge_from=prev_node,
            edge_to=node_id,
            step_delay_ms=_STEP_DELAY_NOMINAL_MS,
            rationale="node outside simulation bounds",
        )
