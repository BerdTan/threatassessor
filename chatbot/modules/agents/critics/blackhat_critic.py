"""
Blackhat Critic — Layer 2E: Cross-path chain analysis (supreme critic — runs last).

Uniqueness vs other critics:
- Architect, Tester, Red Team all validate WITHIN individual attack paths.
- Blackhat examines CROSS-PATH chains: can an attacker combine AP-i → AP-j via a shared pivot
  to form a more exploitable, often stealthy, route that per-path mitigations cannot block?

Deterministic pre-processing feeds structured facts to the LLM, minimising hallucination.
Config-gated (default off). Short-circuits with PASS if fewer than 2 attack paths.

Inverted scoring (0-100): higher = easier to chain-exploit = weaker cross-path defence.

Rubric (default weights, adjustable via settings.blackhat.rubric_weights):
  Cross-Path Chain Feasibility : 30
  Least-Resistance Path        : 25
  Stealth Potential            : 25
  Mitigation Chain Coverage    : 20

Output: CritiqueScore with extra breakdown fields:
  chained_exploit_findings, shared_nodes, stealth_score, stealthy_techniques,
  least_resistance_paths, mitigation_gaps_for_chains, exploit_mitigation_roadmap,
  uniqueness_vs_critics
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from chatbot.modules.agent_framework import CriticAgent, CritiqueScore
from chatbot.modules.artifact_extractor import ArtifactSet

logger = logging.getLogger(__name__)

# Default stealth technique IDs (overridden by settings)
_DEFAULT_STEALTH_TECHNIQUES = ["T1562", "T1070", "T1078", "T1036", "T1027"]


class BlackhatCritic(CriticAgent):
    """
    Layer 2E critic — cross-path chain analysis (supreme critic).

    Contract:
    - Input: ground_truth.json (expected_attack_paths, control_recommendations)
    - Output: CritiqueScore with cross-path chain findings
    - Short-circuit: if < 2 attack paths → PASS, 0 adjustment, no LLM call
    """

    def __init__(self, model: Optional[str] = None):
        super().__init__(
            role="Blackhat",
            rubric=self._build_rubric(),
            system_prompt=self._build_system_prompt(),
            tools=[],
            model=model,
        )
        self._stealth_techniques: List[str] = _DEFAULT_STEALTH_TECHNIQUES
        self._rubric_weights: Dict[str, int] = {
            "cross_path_chain_feasibility": 30,
            "least_resistance_path": 25,
            "stealth_potential": 25,
            "mitigation_chain_coverage": 20,
        }
        # Try to load live settings
        try:
            from chatbot.config.settings import get_settings
            cfg = get_settings().blackhat
            self._stealth_techniques = cfg.stealth_techniques
            w = cfg.rubric_weights
            self._rubric_weights = {
                "cross_path_chain_feasibility": w.cross_path_chain_feasibility,
                "least_resistance_path": w.least_resistance_path,
                "stealth_potential": w.stealth_potential,
                "mitigation_chain_coverage": w.mitigation_chain_coverage,
            }
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Deterministic pre-processing
    # ------------------------------------------------------------------

    def _find_shared_nodes(self, paths: List[Dict]) -> Dict[str, List[str]]:
        """Return {node_id: [ap_ids]} for nodes appearing in 2+ paths."""
        node_to_aps: Dict[str, List[str]] = defaultdict(list)
        for ap in paths:
            for node in ap.get("path", []):
                node_to_aps[node].append(ap.get("id", "?"))
        return {node: aps for node, aps in node_to_aps.items() if len(aps) >= 2}

    def _identify_chained_paths(self, paths: List[Dict]) -> List[Dict]:
        """
        Find AP-i → AP-j chains where AP-i's target appears as a mid-node in AP-j.
        Returns list of {chain: [ap_id_i, ap_id_j], pivot: node, chain_type: 'sequential'}.
        """
        chains = []
        _tier = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        for i, ap_i in enumerate(paths):
            target_i = ap_i.get("target", "")
            if not target_i:
                continue
            for j, ap_j in enumerate(paths):
                if i == j:
                    continue
                path_j = ap_j.get("path", [])
                if target_i in path_j and target_i != ap_j.get("target", ""):
                    chains.append({
                        "chain": [ap_i.get("id", f"AP-{i+1}"), ap_j.get("id", f"AP-{j+1}")],
                        "pivot": target_i,
                        "chain_type": "sequential",
                        "chain_criticality": max(
                            ap_i.get("criticality_tier", "LOW"),
                            ap_j.get("criticality_tier", "LOW"),
                            key=lambda t: _tier.get(t, 0)
                        ),
                    })
        return chains

    def _find_pivot_diverge_chains(
        self,
        paths: List[Dict],
        shared_nodes: Dict[str, List[str]],
        control_recs: List[Dict],
        detection_controls: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Pivot-diverge analysis: shared mid-nodes where a single compromise gives
        forked reach to multiple distinct downstream targets.

        Example: AuthService shared by AP-12 (→UserDB) and AP-15 (→Cache).
        Attacker reaching AuthService gains lateral reach to both targets — per-path
        mitigations on each AP cannot prevent this branching.

        Returns list of {pivot, ap_ids, diverge_targets, techniques_at_pivot,
                          detection_downstream, chain_type, chain_criticality}.
        """
        _tier = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        detection_keywords = set(detection_controls or [
            "siem", "edr", "ids", "ips", "logging", "monitoring", "audit",
            "detection", "alerting", "behavioral analysis", "ndr", "xdr",
        ])

        # Build control name set for detection check
        control_names_lower = {cr.get("control", "").lower() for cr in control_recs}
        has_detection = any(
            any(kw in name for kw in detection_keywords)
            for name in control_names_lower
        )

        pivot_chains = []
        for node, ap_ids in shared_nodes.items():
            if len(ap_ids) < 2:
                continue
            # Collect distinct targets reachable from this node across all APs
            diverge_targets: Dict[str, Dict] = {}  # target → {ap_id, onward_path}
            for ap in paths:
                if ap.get("id") not in ap_ids:
                    continue
                path = ap.get("path", [])
                if node not in path:
                    continue
                idx = path.index(node)
                onward = path[idx:]
                target = ap.get("target", "")
                if target and target != node:
                    diverge_targets[target] = {
                        "ap_id": ap.get("id"),
                        "onward": onward,
                        "criticality": ap.get("criticality_tier", "LOW"),
                    }

            if len(diverge_targets) < 2:
                continue  # only one target reachable — not a diverge

            # Techniques at pivot node across all involved APs
            techs_at_pivot: List[str] = []
            for ap in paths:
                if ap.get("id") in ap_ids:
                    node_techs = ap.get("per_node_techniques", {}).get(node, [])
                    techs_at_pivot.extend(node_techs)
            techs_at_pivot = list(dict.fromkeys(techs_at_pivot))  # dedupe, preserve order

            # Downstream detection: any detection control on the onward paths?
            onward_nodes: List[str] = []
            for info in diverge_targets.values():
                onward_nodes.extend(info["onward"][1:])  # skip pivot itself
            detection_downstream = has_detection  # conservative: global check

            max_crit = max(
                (info["criticality"] for info in diverge_targets.values()),
                key=lambda t: _tier.get(t, 0),
                default="LOW"
            )

            pivot_chains.append({
                "pivot": node,
                "ap_ids": ap_ids,
                "diverge_targets": {t: v["ap_id"] for t, v in diverge_targets.items()},
                "onward_paths": {t: v["onward"] for t, v in diverge_targets.items()},
                "techniques_at_pivot": techs_at_pivot[:6],
                "detection_downstream": detection_downstream,
                "chain_type": "pivot_diverge",
                "chain_criticality": max_crit,
            })

        return pivot_chains

    def _score_stealth(self, techniques_list: List[str]) -> Tuple[int, List[str]]:
        """Count Defense Evasion techniques in a combined technique list."""
        stealthy = [t for t in techniques_list if t in self._stealth_techniques]
        return len(stealthy), stealthy

    def _find_control_gaps_for_chains(
        self,
        chains: List[Dict],
        paths: List[Dict],
        control_recs: List[Dict],
    ) -> List[str]:
        """
        For each chain, find techniques from both paths that have no mitigation
        across the combined chain's technique set.
        """
        gaps = []
        # Build: technique → set of control names that address it
        tech_to_controls: Dict[str, List[str]] = defaultdict(list)
        for cr in control_recs:
            for tech in cr.get("techniques", []):
                tech_to_controls[tech].append(cr.get("control", "unknown"))

        ap_by_id = {ap.get("id", f"AP-{i}"): ap for i, ap in enumerate(paths)}
        for chain in chains:
            # Sequential chains use "chain": [ap_id_i, ap_id_j]
            # Pivot-diverge chains use "ap_ids": [ap_id, ...]
            ap_ids = chain.get("chain") or chain.get("ap_ids", [])
            pivot = chain.get("pivot", "?")
            combined_techs: List[str] = []
            for ap_id in ap_ids:
                ap = ap_by_id.get(ap_id, {})
                combined_techs.extend(ap.get("techniques", []))
            uncovered = [t for t in set(combined_techs) if not tech_to_controls.get(t)]
            if uncovered:
                chain_label = " → ".join(ap_ids) if ap_ids else pivot
                gaps.append(
                    f"Chain {chain_label} via `{pivot}`: "
                    f"uncovered techniques: {', '.join(uncovered[:5])}"
                )
        return gaps

    # ------------------------------------------------------------------
    # Rubric / system prompt
    # ------------------------------------------------------------------

    def _build_rubric(self) -> Dict:
        return {
            "total_points": 100,
            "categories": {
                "cross_path_chain_feasibility": {
                    "points": 30,
                    "description": "Can attacker chain AP-i → AP-j via shared pivot node?",
                },
                "least_resistance_path": {
                    "points": 25,
                    "description": "Does a partial-path combination bypass all per-path controls?",
                },
                "stealth_potential": {
                    "points": 25,
                    "description": "Defense Evasion technique count → undetectable attacker advantage",
                },
                "mitigation_chain_coverage": {
                    "points": 20,
                    "description": "Do per-path mitigations hold against the combined chain?",
                },
            },
            "rating_scale": {
                "0-29": "MINIMAL — cross-path chains are infeasible or fully mitigated",
                "30-49": "LOW — chains exist but high barrier",
                "50-69": "MEDIUM — exploitable chains with moderate effort",
                "70-89": "HIGH — clear cross-path chains, weak combined mitigations",
                "90-100": "CRITICAL — trivially chainable, no stealth barriers",
            },
        }

    def _build_system_prompt(self) -> str:
        return (
            "You are a blackhat security assessor specialising in cross-path chain exploitation. "
            "Your sole focus is: can an attacker combine individual attack paths via shared pivot nodes "
            "to form a more dangerous, often stealthy, composite attack? "
            "Do NOT repeat findings already covered by Architect, Tester, Red Team, or Purple Team critics. "
            "Purple Team (Layer 2D) has already assessed detection depth, coverage gaps, and ADR operability — "
            "do not re-raise those findings; instead, use PT's detection blindspot data as input to identify "
            "pivot nodes where a cross-path chain would be invisible to defenders. "
            "INVERTED scoring: high score = easy cross-path chain = BAD defence. "
            "Ground yourself in the deterministic pre-processing data provided — "
            "do not hallucinate paths or controls not listed in the input."
        )

    # ------------------------------------------------------------------
    # Main critique entry point
    # ------------------------------------------------------------------

    def critique(
        self,
        artifacts: ArtifactSet,
        ground_truth: Dict,
        red_team_critique: Optional[CritiqueScore] = None,
        purple_team_critique: Optional[CritiqueScore] = None,
    ) -> CritiqueScore:
        """
        Run cross-path chain analysis.

        Receives red_team_critique and purple_team_critique (when available) so BH
        can elevate stealth pivots that overlap with PT's detection blindspots.

        Short-circuits to PASS if fewer than 2 attack paths.
        """
        attack_paths = ground_truth.get("expected_attack_paths", [])
        control_recs = ground_truth.get("control_recommendations", [])

        if len(attack_paths) < 2:
            logger.info("BlackhatCritic: < 2 attack paths — cross-path analysis not applicable, returning PASS")
            return self._short_circuit_pass()

        # --- Deterministic pre-processing ---
        shared_nodes = self._find_shared_nodes(attack_paths)

        # Sequential chains: AP-i.target is a mid-node of AP-j
        sequential_chains = self._identify_chained_paths(attack_paths)

        # Pivot-diverge chains: shared mid-node fans out to multiple distinct targets
        pivot_chains = self._find_pivot_diverge_chains(attack_paths, shared_nodes, control_recs)

        # PT detection blindspots: nodes that PT flagged as having no detection downstream
        pt_blind_nodes: List[str] = []
        if purple_team_critique and purple_team_critique.breakdown:
            pt_blind_nodes = [
                b.get("node", "") for b in
                purple_team_critique.breakdown.get("detection_blindspots", [])
                if b.get("node")
            ]
            # Elevate pivot chains where the pivot node has no detection (PT finding)
            for pc in pivot_chains:
                if pc["pivot"] in pt_blind_nodes:
                    pc["stealth_elevated"] = True
                    pc["chain_criticality"] = "CRITICAL"  # worst-case: blind pivot

        all_chains = sequential_chains + pivot_chains
        all_techniques: List[str] = []
        for ap in attack_paths:
            all_techniques.extend(ap.get("techniques", []))
        stealth_score, stealthy_techs = self._score_stealth(all_techniques)
        chain_gaps = self._find_control_gaps_for_chains(all_chains, attack_paths, control_recs)

        logger.info(
            f"BlackhatCritic: {len(shared_nodes)} shared nodes, "
            f"{len(sequential_chains)} sequential chains, "
            f"{len(pivot_chains)} pivot-diverge chains, "
            f"stealth_score={stealth_score}"
        )

        # --- LLM challenge ---
        prompt = self._build_prompt(
            attack_paths, control_recs, shared_nodes,
            sequential_chains, pivot_chains,
            stealth_score, stealthy_techs, chain_gaps,
            red_team_critique, pt_blind_nodes,
            ground_truth=ground_truth,
        )

        import time as _t
        logger.info("BlackhatCritic: Calling LLM for cross-path chain assessment")
        _wall_start = _t.time()
        response = self.llm_client.generate(
            prompt=prompt,
            system_message=self.system_prompt,
            model=self.model,
            temperature=0.3,
            max_tokens=3000,
        )
        _wall_elapsed = _t.time() - _wall_start

        raw_score = self._parse_response_wrapper(response)

        # Stamp perf telemetry onto the score
        raw_score.llm_calls     = 1
        raw_score.llm_tokens    = getattr(response, 'tokens_used',    0) or 0
        raw_score.llm_cost_usd  = round(getattr(response, 'cost_usd',       0.0) or 0.0, 6)
        raw_score.llm_latency_s = round(getattr(response, 'latency_seconds',0.0) or 0.0, 3)
        raw_score.llm_model     = getattr(response, 'model', self.model or '') or ''
        raw_score.wall_clock_s  = round(_wall_elapsed, 3)

        # Inject deterministic fields into breakdown
        raw_score.breakdown["shared_nodes"] = {k: v for k, v in list(shared_nodes.items())[:10]}
        raw_score.breakdown["chained_exploit_findings"] = [
            f"{c['chain'][0]} → {c['chain'][1]} via `{c['pivot']}` [{c['chain_criticality']}]"
            for c in sequential_chains[:10]
        ]
        raw_score.breakdown["pivot_diverge_chains"] = [
            {
                "pivot": pc["pivot"],
                "ap_ids": pc["ap_ids"],
                "targets": list(pc["diverge_targets"].keys()),
                "techniques": pc["techniques_at_pivot"],
                "chain_criticality": pc["chain_criticality"],
                "stealth_elevated": pc.get("stealth_elevated", False),
            }
            for pc in pivot_chains[:8]
        ]
        raw_score.breakdown["stealth_score"] = stealth_score
        raw_score.breakdown["stealthy_techniques"] = stealthy_techs
        raw_score.breakdown["least_resistance_paths"] = [
            {
                "chain": c.get("chain") or c.get("ap_ids", []),
                "pivot": c.get("pivot", "?"),
                "chain_type": c.get("chain_type", "unknown"),
                "chain_criticality": c.get("chain_criticality", "UNKNOWN"),
            }
            for c in all_chains if c.get("chain_criticality") in ("CRITICAL", "HIGH")
        ]
        raw_score.breakdown["mitigation_gaps_for_chains"] = chain_gaps
        raw_score.breakdown["pt_blind_pivot_nodes"] = pt_blind_nodes

        # Uniqueness vs other critics
        rt_gaps = [str(g) for g in red_team_critique.gaps[:5]] if red_team_critique else []
        pt_gaps = [str(g) for g in purple_team_critique.gaps[:5]] if purple_team_critique else []
        raw_score.breakdown["uniqueness_vs_critics"] = {
            "new_findings_not_in_redteam": [
                g for g in chain_gaps
                if not any(g[:20] in rt for rt in rt_gaps)
            ][:5],
            "chains_missed_by_architect": [
                f"{c['chain'][0]} → {c['chain'][1]}" for c in sequential_chains[:5]
            ],
            "pivot_diverge_missed_by_purpleteam": [
                f"Pivot `{pc['pivot']}` fans to: {', '.join(pc['diverge_targets'].keys())}"
                for pc in pivot_chains[:3]
                if not any(pc["pivot"][:8] in pt for pt in pt_gaps)
            ],
        }

        logger.info(
            f"BlackhatCritic: complete — score={raw_score.score}, "
            f"sequential={len(sequential_chains)}, pivot_diverge={len(pivot_chains)}"
        )
        return raw_score

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response_wrapper(self, response) -> CritiqueScore:
        """Parse LLM response into CritiqueScore using parent JSON extractor."""
        data = self._parse_llm_response(response)

        if not data:
            logger.warning("BlackhatCritic: parse failure — using default score")
            return CritiqueScore(
                role=self.role,
                score=50,
                max_score=100,
                rating="UNKNOWN",
                breakdown={},
                gaps=[],
                strengths=[],
                improvement_roadmap=[],
            )

        return CritiqueScore(
            role=self.role,
            score=data.get("score", 50),
            max_score=100,
            rating=data.get("rating", "UNKNOWN"),
            breakdown=data.get("breakdown", {}),
            gaps=data.get("gaps", []),
            strengths=data.get("strengths", []),
            improvement_roadmap=[],
            reasoning=data.get("reasoning", ""),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_bh_story_context(self, attack_paths: list, ground_truth: Optional[Dict]) -> str:
        """
        Stealth augmentation: for each pivot node in chains, flag whether it sits on
        a corroborated path (attacker blends with real traffic → stealth is elevated)
        or a post-compromise path (no user baseline → already a blind spot).
        """
        if not ground_truth:
            return ""
        journeys = ground_truth.get("user_stories", {}).get("journeys", [])
        if not journeys:
            return ""

        by_ap = {j.get("attack_path_id"): j for j in journeys if j.get("attack_path_id")}
        if not by_ap:
            return ""

        lines = []
        for ap in attack_paths:
            ap_id = ap.get("id", "?")
            j = by_ap.get(ap_id)
            if not j:
                continue
            if j.get("no_user_story"):
                lines.append(
                    f"  {ap_id} [POST-COMPROMISE]: No legitimate user traverses this path — "
                    f"any activity is anomalous, but only if network-layer detection is present."
                )
            else:
                role = j.get("user_role", "user")
                lines.append(
                    f"  {ap_id} [CORROBORATED — {role}]: Attacker traffic on this path mimics "
                    f"real {role} behaviour. If this AP shares a pivot node with another AP, "
                    f"lateral movement at the pivot is INVISIBLE to behavioural anomaly detection. "
                    f"Treat stealth_potential as elevated for any chain through this AP."
                )

        if not lines:
            return ""
        return "\n## User Journey Stealth Context (elevate chains through corroborated paths):\n" + "\n".join(lines) + "\n"

    def _short_circuit_pass(self) -> CritiqueScore:
        return CritiqueScore(
            role="Blackhat",
            score=0,
            max_score=100,
            rating="PASS — cross-path analysis not applicable (< 2 attack paths)",
            breakdown={
                "cross_path_chain_feasibility": 0,
                "least_resistance_path": 0,
                "stealth_potential": 0,
                "mitigation_chain_coverage": 0,
                "shared_nodes": {},
                "chained_exploit_findings": [],
                "stealth_score": 0,
                "stealthy_techniques": [],
                "least_resistance_paths": [],
                "mitigation_gaps_for_chains": [],
                "uniqueness_vs_critics": {},
            },
            gaps=[],
            strengths=["Insufficient attack paths for cross-path analysis"],
            improvement_roadmap=[],
        )

    def _build_prompt(
        self,
        attack_paths: List[Dict],
        control_recs: List[Dict],
        shared_nodes: Dict[str, List[str]],
        sequential_chains: List[Dict],
        pivot_chains: List[Dict],
        stealth_score: int,
        stealthy_techs: List[str],
        chain_gaps: List[str],
        red_team_critique: Optional[CritiqueScore],
        pt_blind_nodes: Optional[List[str]] = None,
        ground_truth: Optional[Dict] = None,
    ) -> str:
        weights = self._rubric_weights

        paths_summary = ""
        for ap in attack_paths:
            paths_summary += (
                f"  {ap.get('id','?')} [{ap.get('criticality_tier','?')}]: "
                f"{' → '.join(ap.get('path', [])[:6])} | "
                f"Techniques: {', '.join(ap.get('techniques', [])[:4])}\n"
            )

        controls_summary = ", ".join(cr.get("control", "?") for cr in control_recs[:10])

        shared_summary = ""
        for node, aps in list(shared_nodes.items())[:8]:
            shared_summary += f"  `{node}` shared by: {', '.join(aps)}\n"

        seq_summary = ""
        for c in sequential_chains[:6]:
            seq_summary += (
                f"  {c['chain'][0]} → {c['chain'][1]} via `{c['pivot']}` "
                f"[{c['chain_criticality']}]\n"
            )

        pivot_summary = ""
        for pc in pivot_chains[:8]:
            targets_str = ", ".join(
                f"{t} (via {aid})" for t, aid in pc["diverge_targets"].items()
            )
            stealth_note = " ⚠ NO DETECTION DOWNSTREAM" if pc.get("stealth_elevated") else ""
            pivot_summary += (
                f"  PIVOT `{pc['pivot']}` [{pc['chain_criticality']}]{stealth_note}\n"
                f"    Shared by: {', '.join(pc['ap_ids'])}\n"
                f"    Diverge targets: {targets_str}\n"
                f"    Techniques at pivot: {', '.join(pc['techniques_at_pivot']) or 'none mapped'}\n"
            )

        rt_context = ""
        if red_team_critique:
            rt_context = (
                f"\n## Red Team Findings (do NOT repeat — find NEW cross-path issues)\n"
                f"Red Team score: {red_team_critique.score}/100\n"
                f"Red Team gaps (first 3): {'; '.join(str(g) for g in red_team_critique.gaps[:3])}\n"
            )

        pt_context = ""
        if pt_blind_nodes:
            pt_context = (
                f"\n## Purple Team Detection Blindspots\n"
                f"These nodes have no detection controls downstream (Purple Team finding).\n"
                f"If any of these are pivot nodes, the attacker can branch silently:\n"
                f"  {', '.join(pt_blind_nodes[:8])}\n"
                f"Elevate any pivot chain that passes through these nodes to CRITICAL.\n"
            )

        return f"""# Blackhat Cross-Path Chain Assessment

INVERTED SCORING: high score = easy cross-path chain = BAD defence.
Your job: identify whether attack paths can be COMBINED via shared nodes into more dangerous composite attacks.
Do NOT re-assess individual path controls (Red Team + Purple Team already covered that).

## Attack Paths
{paths_summary}
## Controls Present
{controls_summary}

## Pre-computed Deterministic Facts

### Shared Nodes (appear in 2+ paths):
{shared_summary or '  None identified.'}

### Sequential Chains (AP-i target is mid-node of AP-j — direct pivot):
{seq_summary or '  None — targets are leaf nodes not reused as mid-nodes.'}

### Pivot-Diverge Chains (shared mid-node fans out to multiple distinct targets):
{pivot_summary or '  None — no shared mid-nodes lead to distinct targets.'}
(A pivot-diverge means: one compromise gives the attacker forked reach across multiple AP targets
without needing separate entry points. Per-path mitigations cannot stop this.)

### Stealth Score: {stealth_score} Defence Evasion techniques ({', '.join(stealthy_techs) or 'none'})

### Cross-Path Mitigation Gaps:
{''.join('  - ' + g + chr(10) for g in chain_gaps) or '  None — all chain techniques have a mitigation.'}
{rt_context}{pt_context}{self._format_bh_story_context(attack_paths, ground_truth)}
## Rubric (100 points, INVERTED)

| Category | Points |
|----------|--------|
| Cross-Path Chain Feasibility (sequential + pivot-diverge) | {weights['cross_path_chain_feasibility']} |
| Least-Resistance Path | {weights['least_resistance_path']} |
| Stealth Potential (pivot nodes with no detection) | {weights['stealth_potential']} |
| Mitigation Chain Coverage | {weights['mitigation_chain_coverage']} |

## Required Output (JSON only)

```json
{{
  "score": <int 0-100>,
  "rating": "<MINIMAL/LOW/MEDIUM/HIGH/CRITICAL>",
  "breakdown": {{
    "cross_path_chain_feasibility": <int 0-{weights['cross_path_chain_feasibility']}>,
    "least_resistance_path": <int 0-{weights['least_resistance_path']}>,
    "stealth_potential": <int 0-{weights['stealth_potential']}>,
    "mitigation_chain_coverage": <int 0-{weights['mitigation_chain_coverage']}>
  }},
  "reasoning": "<1-2 sentences: name the most dangerous chain, which node it pivots on, and the concrete consequence. State facts only — no evaluative adjectives>",
  "gaps": [
    {{
      "severity": "<LOW/MEDIUM/HIGH/CRITICAL>",
      "description": "<ONE sentence: name the pivot node, the APs that converge, and the technique. Stop there.>",
      "recommendation": "<ONE sentence: the single control that breaks this chain at the pivot node.>"
    }}
  ],
  "strengths": ["<what mitigations hold even across chains>"],
  "exploit_mitigation_roadmap": [
    {{
      "target_score": <int>,
      "requirements": ["<ONE control that breaks this specific chain — name the control and the node>"],
      "attacker_impact": "<ONE sentence: what this eliminates for the attacker.>",
      "practical": "<YES/MAYBE/NO>"
    }}
  ]
}}
```

**OUTPUT TONE RULES:**
- gaps[].description: ONE sentence. Name the pivot node, converging APs, and technique. No consequence chain after that.
  GOOD: "WebServer pivot (AP-2/AP-3) allows T1059 command injection to reach Database and FileStorage in a single session."
  BAD:  "WebServer pivot (AP-2/AP-3): T1059 command injection enables parallel Database exfiltration and FileStorage tampering; network segmentation present but no micro-segmentation between WebServer→Database and WebServer→FileStorage prevents lateral fan-out."
- gaps[].recommendation: ONE control at ONE node. Not empty, not a list.
  GOOD: "Add micro-segmentation between WebServer and Database with default-deny egress."
- exploit_mitigation_roadmap[].requirements: name ONE control per entry, not a sentence.
- Write for a practitioner who implements one thing at a time."""


# CriticRegistry self-registration (elevated tier — requires policy allow)
try:
    from chatbot.harness.registry import _DEFAULT_REGISTRY, CriticDescriptor
    _DEFAULT_REGISTRY.register(CriticDescriptor(
        name="blackhat", cls=BlackhatCritic,
        governance_tier="elevated", model_key="blackhat", enabled=False,
    ))
except Exception:
    pass
