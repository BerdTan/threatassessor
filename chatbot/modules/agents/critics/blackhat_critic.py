"""
Blackhat Critic — Layer 2D: Cross-path chain analysis.

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
    Layer 2D critic — cross-path chain analysis.

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
        Find AP-i → AP-j chains where AP-i's target appears in AP-j's path body.
        Returns list of {chain: [ap_id_i, ap_id_j], pivot: node}.
        """
        chains = []
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
                        "chain_criticality": max(
                            ap_i.get("criticality_tier", "LOW"),
                            ap_j.get("criticality_tier", "LOW"),
                            key=lambda t: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(t, 0)
                        ),
                    })
        return chains

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
            combined_techs: List[str] = []
            for ap_id in chain["chain"]:
                ap = ap_by_id.get(ap_id, {})
                combined_techs.extend(ap.get("techniques", []))
            uncovered = [t for t in set(combined_techs) if not tech_to_controls.get(t)]
            if uncovered:
                gaps.append(
                    f"Chain {' → '.join(chain['chain'])} via `{chain['pivot']}`: "
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
            "Do NOT repeat findings already covered by Architect, Tester, or Red Team critics. "
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
    ) -> CritiqueScore:
        """
        Run cross-path chain analysis.

        Short-circuits to PASS if fewer than 2 attack paths (cross-path analysis N/A).
        """
        attack_paths = ground_truth.get("expected_attack_paths", [])
        control_recs = ground_truth.get("control_recommendations", [])

        if len(attack_paths) < 2:
            logger.info("BlackhatCritic: < 2 attack paths — cross-path analysis not applicable, returning PASS")
            return self._short_circuit_pass()

        # --- Deterministic pre-processing ---
        shared_nodes = self._find_shared_nodes(attack_paths)
        chains = self._identify_chained_paths(attack_paths)
        all_techniques: List[str] = []
        for ap in attack_paths:
            all_techniques.extend(ap.get("techniques", []))
        stealth_score, stealthy_techs = self._score_stealth(all_techniques)
        chain_gaps = self._find_control_gaps_for_chains(chains, attack_paths, control_recs)

        logger.info(
            f"BlackhatCritic: {len(shared_nodes)} shared nodes, "
            f"{len(chains)} chains, stealth_score={stealth_score}"
        )

        # --- LLM challenge ---
        prompt = self._build_prompt(
            attack_paths, control_recs, shared_nodes, chains,
            stealth_score, stealthy_techs, chain_gaps, red_team_critique
        )

        logger.info("BlackhatCritic: Calling LLM for cross-path chain assessment")
        response = self.llm_client.generate(
            prompt=prompt,
            system_message=self.system_prompt,
            model=self.model,
            temperature=0.3,
            max_tokens=3000,
        )

        raw_score = self._parse_response_wrapper(response)

        # Inject deterministic fields into breakdown
        raw_score.breakdown["shared_nodes"] = {k: v for k, v in list(shared_nodes.items())[:10]}
        raw_score.breakdown["chained_exploit_findings"] = [
            f"{c['chain'][0]} → {c['chain'][1]} via `{c['pivot']}` [{c['chain_criticality']}]"
            for c in chains[:10]
        ]
        raw_score.breakdown["stealth_score"] = stealth_score
        raw_score.breakdown["stealthy_techniques"] = stealthy_techs
        raw_score.breakdown["least_resistance_paths"] = [
            c for c in chains if c.get("chain_criticality") in ("CRITICAL", "HIGH")
        ]
        raw_score.breakdown["mitigation_gaps_for_chains"] = chain_gaps

        # Uniqueness vs other critics
        rt_gaps = []
        if red_team_critique:
            rt_gaps = [str(g) for g in red_team_critique.gaps[:5]]
        raw_score.breakdown["uniqueness_vs_critics"] = {
            "new_findings_not_in_redteam": [
                g for g in chain_gaps
                if not any(g[:20] in rt for rt in rt_gaps)
            ][:5],
            "chains_missed_by_architect": [
                f"{c['chain'][0]} → {c['chain'][1]}" for c in chains[:5]
            ],
            "mitre_gaps_not_in_tester": [
                f"Uncovered in chain: {g[:60]}" for g in chain_gaps[:3]
            ],
        }

        logger.info(f"BlackhatCritic: complete — score={raw_score.score}, chains={len(chains)}")
        return raw_score

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
        chains: List[Dict],
        stealth_score: int,
        stealthy_techs: List[str],
        chain_gaps: List[str],
        red_team_critique: Optional[CritiqueScore],
    ) -> str:
        weights = self._rubric_weights

        paths_summary = ""
        for ap in attack_paths:
            paths_summary += (
                f"  {ap.get('id','?')} [{ap.get('criticality_tier','?')}]: "
                f"{' → '.join(ap.get('path', [])[:5])} | "
                f"Techniques: {', '.join(ap.get('techniques', [])[:4])}\n"
            )

        controls_summary = ", ".join(cr.get("control", "?") for cr in control_recs[:10])

        shared_summary = ""
        for node, aps in list(shared_nodes.items())[:8]:
            shared_summary += f"  `{node}` shared by: {', '.join(aps)}\n"

        chains_summary = ""
        for c in chains[:8]:
            chains_summary += f"  {c['chain'][0]} → {c['chain'][1]} via `{c['pivot']}` [{c['chain_criticality']}]\n"

        rt_context = ""
        if red_team_critique:
            rt_context = (
                f"\n## Red Team Findings (do NOT repeat these — find NEW cross-path issues)\n"
                f"Red Team score: {red_team_critique.score}/100\n"
                f"Red Team gaps (first 3): {'; '.join(str(g) for g in red_team_critique.gaps[:3])}\n"
            )

        return f"""# Blackhat Cross-Path Chain Assessment

INVERTED SCORING: high score = easy cross-path chain = BAD defence.
Your job: assess whether the attack paths can be COMBINED via shared nodes into more dangerous chains.
Do NOT re-assess individual path controls (Red Team already did that).

## Attack Paths
{paths_summary}
## Controls Present
{controls_summary}

## Pre-computed Deterministic Facts

### Shared Pivot Nodes (appear in 2+ paths):
{shared_summary or '  None identified.'}

### Identified Chains (AP-i target appears in AP-j path):
{chains_summary or '  No chains identified.'}

### Stealth Score: {stealth_score} (count of Defense Evasion techniques: {', '.join(stealthy_techs) or 'none'})

### Cross-Path Mitigation Gaps:
{''.join('  - ' + g + chr(10) for g in chain_gaps) or '  None — all chain techniques have a mitigation.'}
{rt_context}
## Rubric (100 points, INVERTED)

| Category | Points |
|----------|--------|
| Cross-Path Chain Feasibility | {weights['cross_path_chain_feasibility']} |
| Least-Resistance Path | {weights['least_resistance_path']} |
| Stealth Potential | {weights['stealth_potential']} |
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
  "reasoning": "<2-3 sentences explaining the chain threat level>",
  "gaps": [
    {{"severity": "<LOW/MEDIUM/HIGH/CRITICAL>", "description": "<cross-path chain gap>"}}
  ],
  "strengths": ["<what mitigations hold even across chains>"],
  "exploit_mitigation_roadmap": [
    {{
      "target_score": <int>,
      "requirements": ["<control to break the chain>"],
      "attacker_impact": "<how this breaks chain feasibility>",
      "practical": "<YES/MAYBE/NO>"
    }}
  ]
}}
```"""
