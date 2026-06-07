"""
Purple Teamer Critic — Layer 2D: Detection Depth, Coverage Gaps & TM/ADR Operability.

Runs after Red Team (2C), before Blackhat (2E — supreme critic).
Receives all prior critic outputs for cross-referencing (availability depends on mode).

Three validation lenses:

  A — Coverage (Red lens):
      Every MITRE technique across all attack paths must have ≥1 mitigation in
      control_recommendations. Uncovered techniques = undefended attack surface that
      neither Architect, Tester, nor Red Team may have flagged at path level.

  B — Assume Breach / Next Layer (Blue lens):
      For each AP node, assumes the attacker has already reached it. Checks whether
      any detection control (SIEM, EDR, IDS, logging) exists on the onward path so
      the breach can be observed and contained. Prevention-only downstream = silent breach.

  C — ThreatHunter / TM-ADR Operability (SOC lens):
      For each CRITICAL/HIGH AP, every hop must have ≥1 detection control so a SOC
      analyst can trace an IoA/IoC through the path. Also validates ADR coherence:
      if an ADR recommends a control for a node but that node's techniques remain
      uncovered in control_recommendations, the ADR recommendation is hollow.

Scoring: FORWARD (0-100). Higher = better coverage.
Confidence adjustment: 0% to -4% depending on gap severity.

Output: CritiqueScore with breakdown fields:
  coverage_gaps, detection_blindspots, adr_coherence_failures
Saved as: 06b_purple_team_critique.json
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Set

from chatbot.modules.agent_framework import CriticAgent, CritiqueScore
from chatbot.modules.artifact_extractor import ArtifactSet

logger = logging.getLogger(__name__)

_DETECTION_KEYWORDS: Set[str] = {
    "siem", "edr", "ids", "ips", "logging", "monitoring", "audit log",
    "audit", "detection", "alerting", "behavioral analysis", "ndr", "xdr",
    "threat hunting", "log", "telemetry", "visibility",
}

_ADR_CONTROL_PATTERNS = [
    "mfa", "least privilege", "network segmentation", "encryption",
    "input validation", "rate limiting", "waf", "secrets management",
    "patch", "patching", "edr", "siem",
]


class PurpleTeamerCritic(CriticAgent):
    """
    Layer 2D — Detection depth, coverage completeness, and TM/ADR operability.

    Contract:
    - Input: ArtifactSet + ground_truth + arch/tester/redteam CritiqueScores
    - Output: CritiqueScore with coverage_gaps, detection_blindspots, adr_coherence_failures
    - Missing prior critic inputs: accepted gracefully, noted in mode_context
    """

    def __init__(self, model: Optional[str] = None):
        super().__init__(
            role="PurpleTeamer",
            rubric=self._build_rubric(),
            system_prompt=self._build_system_prompt(),
            tools=[],
            model=model,
        )

    # ------------------------------------------------------------------
    # Deterministic pre-processing
    # ------------------------------------------------------------------

    def _find_coverage_gaps(
        self,
        attack_paths: List[Dict],
        control_recs: List[Dict],
    ) -> List[Dict]:
        """
        Lens A: Every technique across all APs must have ≥1 mitigation.
        Returns list of {technique, affected_nodes, affected_aps, severity}.
        """
        tech_to_controls: Dict[str, List[str]] = defaultdict(list)
        for cr in control_recs:
            for tech in cr.get("techniques", []):
                tech_to_controls[tech].append(cr.get("control", "?"))

        # Collect technique → {nodes, aps}
        tech_nodes: Dict[str, Set[str]] = defaultdict(set)
        tech_aps: Dict[str, Set[str]] = defaultdict(set)
        for ap in attack_paths:
            ap_id = ap.get("id", "?")
            for node, techs in ap.get("per_node_techniques", {}).items():
                for t in techs:
                    tech_nodes[t].add(node)
                    tech_aps[t].add(ap_id)

        gaps = []
        for tech, nodes in tech_nodes.items():
            if not tech_to_controls.get(tech):
                ap_ids = list(tech_aps[tech])
                # Severity: CRITICAL if ≥2 CRITICAL/HIGH APs, HIGH otherwise
                ap_tiers = [
                    ap.get("criticality_tier", "LOW") for ap in attack_paths
                    if ap.get("id") in ap_ids
                ]
                sev = "CRITICAL" if ap_tiers.count("CRITICAL") >= 1 or ap_tiers.count("HIGH") >= 2 else "HIGH"
                gaps.append({
                    "technique": tech,
                    "affected_nodes": sorted(nodes)[:4],
                    "affected_aps": ap_ids[:4],
                    "severity": sev,
                    "description": (
                        f"Technique {tech} used at node(s) {', '.join(sorted(nodes)[:3])} "
                        f"across {', '.join(ap_ids[:3])} has no mitigation in control recommendations. "
                        f"This leaves the technique completely undefended."
                    ),
                })
        return sorted(gaps, key=lambda g: (g["severity"] != "CRITICAL", g["technique"]))

    def _find_detection_blindspots(
        self,
        attack_paths: List[Dict],
        control_recs: List[Dict],
    ) -> List[Dict]:
        """
        Lens B: Assume attacker has reached each node. Does any detection control
        exist on the onward path? Prevention-only downstream = silent breach.
        Returns list of {node, ap_id, onward_nodes, severity}.
        """
        # Which controls are detection-oriented?
        detection_control_names: Set[str] = set()
        for cr in control_recs:
            name = cr.get("control", "").lower()
            if any(kw in name for kw in _DETECTION_KEYWORDS):
                detection_control_names.add(cr.get("control", ""))

        # Which nodes do detection controls address? (via attack_paths association)
        # Conservative: if any detection control covers this AP, treat that AP as monitored.
        # Per-node detection would require more granular data than control_recs provides.
        detection_ap_indices: Set[int] = set()
        for i, cr in enumerate(control_recs):
            if cr.get("control", "") in detection_control_names:
                for ap_idx in cr.get("attack_paths", []):
                    detection_ap_indices.add(ap_idx)

        blindspots = []
        for ap_idx, ap in enumerate(attack_paths):
            tier = ap.get("criticality_tier", "LOW")
            if tier not in ("CRITICAL", "HIGH"):
                continue  # lens B focuses on high-value paths
            path_nodes = ap.get("path", [])
            if len(path_nodes) < 2:
                continue

            ap_monitored = ap_idx in detection_ap_indices

            for node_idx, node in enumerate(path_nodes[:-1]):  # skip final target
                onward = path_nodes[node_idx + 1:]
                if not ap_monitored:
                    blindspots.append({
                        "node": node,
                        "ap_id": ap.get("id", "?"),
                        "ap_criticality": tier,
                        "onward_nodes": onward[:4],
                        "severity": "HIGH" if tier == "HIGH" else "CRITICAL",
                        "description": (
                            f"If attacker reaches '{node}' on {ap.get('id','?')} "
                            f"({tier}), there is no detection control covering the "
                            f"onward path to {ap.get('target','?')}. "
                            f"A breach here would be silent — no SOC alert triggered."
                        ),
                    })
        # Dedupe by node+ap
        seen: Set[str] = set()
        deduped = []
        for b in blindspots:
            k = f"{b['node']}:{b['ap_id']}"
            if k not in seen:
                seen.add(k)
                deduped.append(b)
        return deduped[:10]

    def _find_adr_coherence_failures(
        self,
        attack_paths: List[Dict],
        control_recs: List[Dict],
        artifacts: ArtifactSet,
    ) -> List[Dict]:
        """
        Lens C: If an ADR recommends a control for a node but that node's
        per_node_techniques have no matching mitigation, the ADR recommendation
        is hollow — the threat is not actually closed.
        Also checks that CRITICAL/HIGH APs have ≥1 detection control per hop.
        """
        failures = []
        tech_to_controls: Dict[str, List[str]] = defaultdict(list)
        for cr in control_recs:
            for tech in cr.get("techniques", []):
                tech_to_controls[tech].append(cr.get("control", "?"))

        # ADR coherence: for recommended controls, do they actually cover the AP techniques?
        for ap in attack_paths:
            if ap.get("criticality_tier") not in ("CRITICAL", "HIGH"):
                continue
            for node, techs in ap.get("per_node_techniques", {}).items():
                uncovered_techs = [t for t in techs if not tech_to_controls.get(t)]
                if not uncovered_techs:
                    continue
                # Check if any ADR-pattern control was recommended for this AP
                ap_idx = attack_paths.index(ap)
                ap_controls = [
                    cr.get("control", "?") for cr in control_recs
                    if ap_idx in cr.get("attack_paths", [])
                ]
                # If controls were recommended but techniques are still uncovered,
                # the controls don't actually address these techniques → hollow ADR
                if ap_controls:
                    failures.append({
                        "node": node,
                        "ap_id": ap.get("id", "?"),
                        "uncovered_techniques": uncovered_techs[:4],
                        "recommended_controls": ap_controls[:3],
                        "severity": "HIGH",
                        "description": (
                            f"Node '{node}' in {ap.get('id','?')} has recommended controls "
                            f"({', '.join(ap_controls[:2])}) but techniques "
                            f"{', '.join(uncovered_techs[:3])} remain unmapped. "
                            f"The ADR recommendation does not close this attack vector — "
                            f"it needs to explicitly address these techniques."
                        ),
                    })

        # Dedupe by node+ap
        seen: Set[str] = set()
        deduped = []
        for f in failures:
            k = f"{f['node']}:{f['ap_id']}"
            if k not in seen:
                seen.add(k)
                deduped.append(f)
        return deduped[:8]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def critique(
        self,
        artifacts: ArtifactSet,
        ground_truth: Dict,
        architect_critique: Optional[CritiqueScore] = None,
        tester_critique: Optional[CritiqueScore] = None,
        red_team_critique: Optional[CritiqueScore] = None,
    ) -> CritiqueScore:
        """
        Run three-lens coverage analysis.

        Missing prior critic inputs are accepted — noted in the breakdown as
        mode_context so the orchestrator can surface the tradeoff.
        """
        attack_paths = ground_truth.get("expected_attack_paths", [])
        control_recs = ground_truth.get("control_recommendations", [])

        if not attack_paths:
            return self._short_circuit_pass("No attack paths in ground truth")

        # --- Deterministic pre-processing (all three lenses) ---
        coverage_gaps = self._find_coverage_gaps(attack_paths, control_recs)
        detection_blindspots = self._find_detection_blindspots(attack_paths, control_recs)
        adr_failures = self._find_adr_coherence_failures(attack_paths, control_recs, artifacts)

        # What prior critic context is available?
        available_critics = []
        if architect_critique:
            available_critics.append("Architect")
        if tester_critique:
            available_critics.append("Tester")
        if red_team_critique:
            available_critics.append("RedTeam")
        mode_context = (
            f"Prior critic inputs available: {', '.join(available_critics) or 'none'}. "
            + ("Full cross-referencing enabled." if len(available_critics) == 3
               else "Partial cross-referencing — some gaps may overlap with unavailable critics.")
        )

        logger.info(
            f"PurpleTeamerCritic: {len(coverage_gaps)} coverage gaps, "
            f"{len(detection_blindspots)} detection blindspots, "
            f"{len(adr_failures)} ADR coherence failures"
        )

        prompt = self._build_prompt(
            attack_paths, control_recs,
            coverage_gaps, detection_blindspots, adr_failures,
            mode_context, architect_critique, tester_critique, red_team_critique,
        )

        logger.info("PurpleTeamerCritic: Calling LLM")
        response = self.llm_client.generate(
            prompt=prompt,
            system_message=self.system_prompt,
            model=self.model,
            temperature=0.3,
            max_tokens=3500,
        )

        raw_score = self._parse_response_wrapper(response)

        # Inject deterministic breakdown fields
        raw_score.breakdown["coverage_gaps"] = [
            {"technique": g["technique"], "affected_aps": g["affected_aps"],
             "affected_nodes": g["affected_nodes"], "severity": g["severity"]}
            for g in coverage_gaps[:10]
        ]
        raw_score.breakdown["detection_blindspots"] = [
            {"node": b["node"], "ap_id": b["ap_id"],
             "onward_nodes": b["onward_nodes"], "severity": b["severity"]}
            for b in detection_blindspots[:8]
        ]
        raw_score.breakdown["adr_coherence_failures"] = [
            {"node": f["node"], "ap_id": f["ap_id"],
             "uncovered_techniques": f["uncovered_techniques"],
             "severity": f["severity"]}
            for f in adr_failures[:6]
        ]
        raw_score.breakdown["mode_context"] = mode_context
        raw_score.breakdown["summary_counts"] = {
            "coverage_gaps": len(coverage_gaps),
            "detection_blindspots": len(detection_blindspots),
            "adr_coherence_failures": len(adr_failures),
        }

        logger.info(f"PurpleTeamerCritic: complete — score={raw_score.score}")
        return raw_score

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response_wrapper(self, response) -> CritiqueScore:
        data = self._parse_llm_response(response)
        if not data:
            logger.warning("PurpleTeamerCritic: parse failure — using default score")
            return CritiqueScore(
                role=self.role, score=50, max_score=100, rating="UNKNOWN",
                breakdown={}, gaps=[], strengths=[], improvement_roadmap=[],
            )
        return CritiqueScore(
            role=self.role,
            score=data.get("score", 50),
            max_score=100,
            rating=data.get("rating", "UNKNOWN"),
            breakdown=data.get("breakdown", {}),
            gaps=data.get("gaps", []),
            strengths=data.get("strengths", []),
            improvement_roadmap=data.get("improvement_roadmap", []),
            reasoning=data.get("reasoning", ""),
        )

    # ------------------------------------------------------------------
    # Rubric / prompts / helpers
    # ------------------------------------------------------------------

    def _build_rubric(self) -> Dict:
        return {
            "total_points": 100,
            "categories": {
                "technique_coverage": {
                    "points": 35,
                    "description": "All attack techniques have ≥1 mitigation (Lens A)",
                },
                "detection_chain": {
                    "points": 35,
                    "description": "CRITICAL/HIGH paths have detection controls (Lens B)",
                },
                "adr_tm_coherence": {
                    "points": 30,
                    "description": "ADR recommendations actually close the technique gaps (Lens C)",
                },
            },
            "rating_scale": {
                "0-39":  "CRITICAL — major coverage and detection gaps",
                "40-59": "HIGH — significant gaps, TM not operationally useful",
                "60-74": "MEDIUM — partial coverage, some detection blind spots",
                "75-89": "LOW — minor gaps, TM mostly operable",
                "90-100": "PASS — full coverage, detection chain intact, ADR coherent",
            },
        }

    def _build_system_prompt(self) -> str:
        return (
            "You are a Purple Team assessor bridging offensive and defensive security. "
            "You validate three things: (A) every MITRE technique is mitigated, "
            "(B) every high-value path has detection so a SOC analyst can observe a breach, "
            "(C) ADR/ThreatModel recommendations actually close the attack vectors they claim to. "
            "FORWARD scoring: high score = good coverage = strong defence. "
            "Be specific — name the technique ID, node, and AP when citing a gap. "
            "Do NOT repeat findings already covered by Architect, Tester, or Red Team. "
            "Ground yourself in the deterministic pre-processing data — "
            "do not invent techniques or controls not listed in the input."
        )

    def _build_prompt(
        self,
        attack_paths: List[Dict],
        control_recs: List[Dict],
        coverage_gaps: List[Dict],
        detection_blindspots: List[Dict],
        adr_failures: List[Dict],
        mode_context: str,
        architect_critique: Optional[CritiqueScore],
        tester_critique: Optional[CritiqueScore],
        red_team_critique: Optional[CritiqueScore],
    ) -> str:
        paths_summary = ""
        for ap in attack_paths:
            paths_summary += (
                f"  {ap.get('id','?')} [{ap.get('criticality_tier','?')}]: "
                f"{' → '.join(ap.get('path', [])[:6])}\n"
                f"    Techniques: {', '.join(ap.get('techniques', [])[:5])}\n"
            )

        cov_summary = ""
        for g in coverage_gaps[:8]:
            cov_summary += (
                f"  {g['technique']} [{g['severity']}] — nodes: "
                f"{', '.join(g['affected_nodes'][:3])} — APs: {', '.join(g['affected_aps'][:3])}\n"
            )

        det_summary = ""
        for b in detection_blindspots[:6]:
            det_summary += (
                f"  Node `{b['node']}` in {b['ap_id']} [{b['ap_criticality']}] — "
                f"onward to: {', '.join(b['onward_nodes'][:3])}\n"
            )

        adr_summary = ""
        for f in adr_failures[:5]:
            adr_summary += (
                f"  Node `{f['node']}` in {f['ap_id']} — "
                f"uncovered: {', '.join(f['uncovered_techniques'][:3])} — "
                f"recommended controls that don't address these: "
                f"{', '.join(f['recommended_controls'][:2])}\n"
            )

        prior_gaps = ""
        for name, crit in [("Architect", architect_critique),
                            ("Tester", tester_critique),
                            ("RedTeam", red_team_critique)]:
            if crit:
                prior_gaps += (
                    f"  {name} ({crit.score}/100): "
                    f"{'; '.join(str(g.get('description',''))[:80] for g in crit.gaps[:2]) or 'no gaps'}\n"
                )

        return f"""# Purple Team Assessment — Coverage, Detection & TM Operability

Context: {mode_context}

## Attack Paths
{paths_summary}
## Controls Recommended ({len(control_recs)} total)
{', '.join(cr.get('control','?') for cr in control_recs[:12])}

## Pre-computed Deterministic Facts

### Lens A — Uncovered Techniques (no mitigation exists):
{cov_summary or '  All techniques covered.'}

### Lens B — Detection Blindspots (CRITICAL/HIGH paths, prevention-only downstream):
{det_summary or '  All high-value paths have detection coverage.'}

### Lens C — ADR Coherence Failures (control recommended but techniques still unmapped):
{adr_summary or '  All ADR recommendations address their target techniques.'}

## Prior Critic Gaps (do NOT repeat these — find NEW issues in your lenses):
{prior_gaps or '  No prior critic context available.'}

## Rubric (100 points, FORWARD — higher = better)

| Lens | Category | Points |
|------|----------|--------|
| A | Technique Coverage (every technique has ≥1 mitigation) | 35 |
| B | Detection Chain (high-value paths observable by SOC) | 35 |
| C | ADR/TM Coherence (recommendations actually close gaps) | 30 |

## Required Output (JSON only)

```json
{{
  "score": <int 0-100>,
  "rating": "<CRITICAL/HIGH/MEDIUM/LOW/PASS>",
  "breakdown": {{
    "technique_coverage": <int 0-35>,
    "detection_chain": <int 0-35>,
    "adr_tm_coherence": <int 0-30>
  }},
  "reasoning": "<1-2 sentences: name the most critical detection gap, which node or technique it affects, and the direct operational consequence. State facts only — no evaluative adjectives>",
  "gaps": [
    {{
      "lens": "<A/B/C>",
      "severity": "<LOW/MEDIUM/HIGH/CRITICAL>",
      "description": "<specific gap — name technique ID, node, AP>",
      "recommendation": "<what control or change closes this gap>"
    }}
  ],
  "strengths": ["<what coverage or detection is already in place>"],
  "improvement_roadmap": [
    {{
      "priority": "<1/2/3>",
      "action": "<specific action>",
      "closes_lens": "<A/B/C>",
      "effort": "<low/medium/high>"
    }}
  ]
}}
```"""

    def _short_circuit_pass(self, reason: str) -> CritiqueScore:
        return CritiqueScore(
            role="PurpleTeamer",
            score=85,
            max_score=100,
            rating=f"PASS — {reason}",
            breakdown={
                "technique_coverage": 35,
                "detection_chain": 35,
                "adr_tm_coherence": 30,
                "coverage_gaps": [],
                "detection_blindspots": [],
                "adr_coherence_failures": [],
                "summary_counts": {"coverage_gaps": 0, "detection_blindspots": 0, "adr_coherence_failures": 0},
            },
            gaps=[],
            strengths=[reason],
            improvement_roadmap=[],
        )
