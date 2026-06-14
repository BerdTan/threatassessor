"""
ScrumMaster Meta-Critic

Reads ALL MoE ValidationResults, identifies impediments (conflicts, coverage
gaps, unresolved recommendations, blindspots), and works towards harmony —
not score maximisation.

Algorithm:
1. Analyse impediments — deterministic, no LLM
2. Confidence gate: ≥90% → prioritise only, no re-triggering
3. Harmony check: majority unresolvable → redesign_signal, no re-triggering
4. Targeted re-trigger (up to max_iterations=2, max 2 critics/iteration)
5. Stop early if delta < MIN_DELTA (further rounds won't help)
6. Build sharp prioritised action plan (top-5 if confident, top-3 if redesign)
7. Populate baseline_feedback for det-engine improvement when needed

Does NOT duplicate MoE sequencing — calls MoEOrchestrator.run_targeted().
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.modules.agents.orchestrators.moe_orchestrator import MoEResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ImpedimentItem:
    """A conflict, gap, or contradiction identified across critics."""
    impediment_type: str          # "contradiction" | "coverage_gap" | "unresolved_rec" | "blindspot"
    source_critics: List[str]     # critics involved, e.g. ["architect", "red_team"]
    description: str
    severity: str                 # "critical" | "high" | "medium" | "low"
    affected_attack_paths: List[str]
    resolvable: bool              # False = architecture may need redesign
    proposed_resolution: str = "" # concrete proposal (empty if not resolvable)
    target_critic: str = ""       # critic best placed to address this


@dataclass
class BaselineFeedback:
    """Structured feedback to the deterministic engine.

    Not a live code edit — input for the next analysis pass or a human reviewer.
    Populated when redesign_signal=True or persistent unresolvable gaps remain.
    """
    weak_controls: List[str] = field(default_factory=list)
    pattern_gaps: List[str] = field(default_factory=list)
    rapids_weight_hints: Dict[str, float] = field(default_factory=dict)
    ground_truth_gaps: List[str] = field(default_factory=list)


@dataclass
class ScrumMasterResult:
    """Full output of a ScrumMaster synthesis run."""
    architecture_name: str
    initial_confidence: float         # MoE final_confidence before ScrumMaster
    final_confidence: float           # confidence after SM (same as initial if no re-triggers)
    confidence_delta: float           # final - initial
    iterations_run: int               # 0 if confidence gate passed on first check
    redesign_signal: bool             # architecture needs structural changes, not more critic rounds
    impediments_found: List[ImpedimentItem]
    impediments_resolved: List[ImpedimentItem]
    action_plan: List[Dict]           # top-N sharp prioritised items
    blindspots_surfaced: List[str]
    critics_retriggered: List[str]    # empty if gate passed or redesign_signal
    confidence_trajectory: List[float]
    baseline_feedback: Optional[BaselineFeedback]
    synthesis_note: str               # one-paragraph plain-English summary

    def to_dict(self) -> Dict:
        """JSON-serialisable dict. Used for 08_scrum_master.json persistence."""
        import dataclasses
        def _ser(obj):
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return {k: _ser(v) for k, v in dataclasses.asdict(obj).items()}
            if isinstance(obj, list):
                return [_ser(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _ser(v) for k, v in obj.items()}
            return obj
        return _ser(self)


# ---------------------------------------------------------------------------
# Critic name → confidence-adjustment attribute map
# ---------------------------------------------------------------------------

_CRITIC_ADJUSTMENT_ATTRS = {
    "architect":   "architect_adjustment",
    "tester":      "tester_adjustment",
    "red_team":    "red_team_adjustment",
    "purple_team": "purple_team_adjustment",
    "blackhat":    "blackhat_adjustment",
}

_CRITIC_RESULT_ATTRS = {
    "architect":   "architect_result",
    "tester":      "tester_result",
    "red_team":    "red_team_result",
    "purple_team": "purple_team_result",
    "blackhat":    "blackhat_result",
}

_CRITIC_FILES = {
    "architect":   "04_architect_critique.json",
    "tester":      "05_tester_critique.json",
    "red_team":    "06_red_team_critique.json",
    "purple_team": "06b_purple_team_critique.json",
    "blackhat":    "06c_blackhat_critique.json",
}


# ---------------------------------------------------------------------------
# ScrumMasterCritic
# ---------------------------------------------------------------------------

class ScrumMasterCritic:
    """Meta-critic — reads all ValidationResults and works towards harmony."""

    MAX_ITERATIONS = 2
    CONFIDENCE_TARGET = 90.0
    MIN_DELTA = 1.0   # stop early if iteration gained < 1% confidence

    def __init__(self, model: Optional[str] = None):
        try:
            from chatbot.config import get_settings
            self.model = model or get_settings().llm_model
        except Exception:
            self.model = model or "anthropic/claude-sonnet-4-6"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        moe_result: "MoEResult",
        report_dir: str,
        ground_truth: Dict,
        max_iterations: int = MAX_ITERATIONS,
        confidence_target: float = CONFIDENCE_TARGET,
        progress_callback=None,
    ) -> ScrumMasterResult:
        """Main entry point: analyse → gate → harmony → (optional) re-trigger → plan."""

        arch_name = moe_result.architecture_name
        initial_confidence = moe_result.final_confidence
        trajectory = [initial_confidence]
        critics_retriggered: List[str] = []
        all_impediments: List[ImpedimentItem] = []
        resolved_impediments: List[ImpedimentItem] = []
        current_result = moe_result

        if progress_callback:
            progress_callback("scrum_master", 90, "ScrumMaster: analysing impediments...")

        # Step 1: Deterministic impediment analysis
        impediments = self._analyse_impediments(current_result)
        all_impediments = impediments

        # Step 2: Confidence gate — if already confident, skip re-triggering entirely
        if initial_confidence >= confidence_target:
            logger.info(
                f"ScrumMaster: confidence {initial_confidence:.1f}% >= {confidence_target}% "
                "— skipping re-triggers, focusing on prioritisation"
            )
            action_plan = self._build_action_plan(current_result, resolved_impediments, redesign_signal=False)
            baseline_fb = self._build_baseline_feedback(current_result, ground_truth, impediments) \
                if self._has_persistent_gaps(impediments) else None
            return ScrumMasterResult(
                architecture_name=arch_name,
                initial_confidence=initial_confidence,
                final_confidence=initial_confidence,
                confidence_delta=0.0,
                iterations_run=0,
                redesign_signal=False,
                impediments_found=all_impediments,
                impediments_resolved=resolved_impediments,
                action_plan=action_plan,
                blindspots_surfaced=self._extract_blindspots(current_result),
                critics_retriggered=[],
                confidence_trajectory=trajectory,
                baseline_feedback=baseline_fb,
                synthesis_note=self._build_synthesis_note(
                    initial_confidence, initial_confidence, 0, False, [], impediments
                ),
            )

        # Step 3: Harmony check — majority unresolvable → redesign signal
        harmony_ok = self._harmony_check(impediments)
        if not harmony_ok:
            logger.info("ScrumMaster: harmony check failed — redesign_signal=True")
            baseline_fb = self._build_baseline_feedback(current_result, ground_truth, impediments)
            action_plan = self._build_action_plan(current_result, [], redesign_signal=True)
            return ScrumMasterResult(
                architecture_name=arch_name,
                initial_confidence=initial_confidence,
                final_confidence=initial_confidence,
                confidence_delta=0.0,
                iterations_run=0,
                redesign_signal=True,
                impediments_found=all_impediments,
                impediments_resolved=[],
                action_plan=action_plan,
                blindspots_surfaced=self._extract_blindspots(current_result),
                critics_retriggered=[],
                confidence_trajectory=trajectory,
                baseline_feedback=baseline_fb,
                synthesis_note=self._build_synthesis_note(
                    initial_confidence, initial_confidence, 0, True, [], impediments
                ),
            )

        # Step 4: Formulate proposals for resolvable impediments (LLM pass)
        if progress_callback:
            progress_callback("scrum_master", 92, "ScrumMaster: formulating proposals...")

        impediments = self._formulate_proposals(impediments, ground_truth)

        # Step 5: Targeted re-trigger loop
        for iteration in range(max_iterations):
            critics_to_run = self._select_critics_to_retrigger(current_result, impediments)

            if not critics_to_run:
                logger.info(f"ScrumMaster: no addressable critics found — stopping at iteration {iteration}")
                break

            if progress_callback:
                progress_callback(
                    "scrum_master", 93 + iteration,
                    f"ScrumMaster: re-triggering {critics_to_run} (iteration {iteration + 1})..."
                )

            proposals = [
                {"description": i.description, "proposed_resolution": i.proposed_resolution,
                 "target_critic": i.target_critic, "severity": i.severity}
                for i in impediments if i.resolvable and i.proposed_resolution
            ]

            try:
                new_result = self._retrigger_critics(
                    critics_to_run, report_dir, proposals, current_result
                )
            except Exception as exc:
                logger.warning(f"ScrumMaster: re-trigger iteration {iteration + 1} failed: {exc}")
                break

            new_confidence = new_result.final_confidence
            delta = new_confidence - current_result.final_confidence
            trajectory.append(new_confidence)
            critics_retriggered.extend(critics_to_run)

            logger.info(
                f"ScrumMaster: iteration {iteration + 1} — "
                f"confidence {current_result.final_confidence:.1f}% → {new_confidence:.1f}% "
                f"(delta: {delta:+.1f}%)"
            )

            # Track which impediments improved
            new_impediments = self._analyse_impediments(new_result)
            for old_imp in impediments:
                if old_imp.resolvable:
                    # If the severity dropped or the gap disappeared, count as resolved
                    matching_new = [
                        n for n in new_impediments
                        if n.description == old_imp.description
                    ]
                    if not matching_new or (matching_new and matching_new[0].severity == "low"):
                        resolved_impediments.append(old_imp)

            current_result = new_result
            impediments = new_impediments

            # Early stop if diminishing returns
            if delta < self.MIN_DELTA:
                logger.info(
                    f"ScrumMaster: delta {delta:.2f}% < MIN_DELTA {self.MIN_DELTA}% — stopping early"
                )
                break

            # Early stop if target reached mid-loop
            if new_confidence >= confidence_target:
                logger.info(f"ScrumMaster: confidence {new_confidence:.1f}% >= target — stopping")
                break

        final_confidence = current_result.final_confidence
        confidence_delta = final_confidence - initial_confidence

        # Step 6: Baseline feedback if persistent gaps remain
        has_persistent = self._has_persistent_gaps(impediments)
        baseline_fb = self._build_baseline_feedback(current_result, ground_truth, impediments) \
            if has_persistent else None

        # Step 7: Build sharp prioritised action plan
        if progress_callback:
            progress_callback("scrum_master", 95, "ScrumMaster: building action plan...")

        action_plan = self._build_action_plan(current_result, resolved_impediments, redesign_signal=False)

        return ScrumMasterResult(
            architecture_name=arch_name,
            initial_confidence=initial_confidence,
            final_confidence=final_confidence,
            confidence_delta=confidence_delta,
            iterations_run=len(trajectory) - 1,
            redesign_signal=False,
            impediments_found=all_impediments,
            impediments_resolved=resolved_impediments,
            action_plan=action_plan,
            blindspots_surfaced=self._extract_blindspots(current_result),
            critics_retriggered=list(dict.fromkeys(critics_retriggered)),  # dedupe, preserve order
            confidence_trajectory=trajectory,
            baseline_feedback=baseline_fb,
            synthesis_note=self._build_synthesis_note(
                initial_confidence, final_confidence,
                len(trajectory) - 1, False, critics_retriggered, impediments
            ),
        )

    # ------------------------------------------------------------------
    # Step 1: Deterministic impediment analysis (no LLM)
    # ------------------------------------------------------------------

    def _analyse_impediments(self, moe_result: "MoEResult") -> List[ImpedimentItem]:
        """Extract impediments from all ValidationResult fields — no LLM."""
        impediments: List[ImpedimentItem] = []

        # 1a. Cross-critic contradictions (from MoE synthesis)
        for c in getattr(moe_result, "contradictions", []):
            impediments.append(ImpedimentItem(
                impediment_type="contradiction",
                source_critics=c.get("critics", []),
                description=c.get("description", str(c)),
                severity=c.get("severity", "medium"),
                affected_attack_paths=c.get("affected_paths", []),
                resolvable=self._is_resolvable_contradiction(c),
                target_critic=c.get("critics", ["architect"])[0] if c.get("critics") else "architect",
            ))

        # 1b. Structural blindspots (no critic can see these)
        for b in getattr(moe_result, "blindspots", []):
            desc = b.get("description", str(b)) if isinstance(b, dict) else str(b)
            impediments.append(ImpedimentItem(
                impediment_type="blindspot",
                source_critics=[],
                description=desc,
                severity=b.get("severity", "high") if isinstance(b, dict) else "high",
                affected_attack_paths=[],
                resolvable=False,
                target_critic="",
            ))

        # 1c. Per-critic gaps with no matching control
        controls_present = set()
        # Controls are referenced by category keywords — use a simple heuristic
        # (ScrumMaster does not need perfect precision here)

        for critic_name, attr in _CRITIC_RESULT_ATTRS.items():
            vr = getattr(moe_result, attr, None)
            if vr is None:
                continue
            for gap in getattr(vr, "gaps", []):
                desc = gap.get("description", str(gap)) if isinstance(gap, dict) else str(gap)
                severity = gap.get("severity", "medium") if isinstance(gap, dict) else "medium"
                affected = gap.get("affected_items", []) if isinstance(gap, dict) else []
                impediments.append(ImpedimentItem(
                    impediment_type="coverage_gap",
                    source_critics=[critic_name],
                    description=desc,
                    severity=severity,
                    affected_attack_paths=affected if isinstance(affected, list) else [],
                    resolvable=severity in ("medium", "low"),  # critical/high gaps may be structural
                    target_critic=critic_name,
                ))

        # 1d. Recommendations with no matching control in ground_truth
        # (high-value: these are actionable gaps the det-engine missed)
        for critic_name, attr in _CRITIC_RESULT_ATTRS.items():
            vr = getattr(moe_result, attr, None)
            if vr is None:
                continue
            for rec in getattr(vr, "recommendations", []):
                if isinstance(rec, dict) and rec.get("priority") in ("critical", "high"):
                    impediments.append(ImpedimentItem(
                        impediment_type="unresolved_rec",
                        source_critics=[critic_name],
                        description=rec.get("action", str(rec)),
                        severity=rec.get("priority", "high"),
                        affected_attack_paths=[],
                        resolvable=True,
                        target_critic=critic_name,
                    ))

        return impediments

    def _is_resolvable_contradiction(self, contradiction: dict) -> bool:
        """A contradiction is unresolvable if critics disagree on the same AP with no overlap."""
        # Simple heuristic: if both critics' affected paths are non-empty and disjoint → unresolvable
        critics = contradiction.get("critics", [])
        paths = contradiction.get("affected_paths", [])
        if len(critics) >= 2 and not paths:
            return False
        return True

    # ------------------------------------------------------------------
    # Step 3: Harmony check
    # ------------------------------------------------------------------

    def _harmony_check(self, impediments: List[ImpedimentItem]) -> bool:
        """Returns True (harmony reachable) or False (redesign needed)."""
        critical_or_high = [i for i in impediments if i.severity in ("critical", "high")]
        if not critical_or_high:
            return True  # nothing blocking harmony
        resolvable = [i for i in critical_or_high if i.resolvable]
        unresolvable = [i for i in critical_or_high if not i.resolvable]
        if not resolvable and unresolvable:
            return False  # all high-severity impediments are structural
        return len(resolvable) >= len(unresolvable)

    # ------------------------------------------------------------------
    # Step 4: Formulate proposals (LLM pass — one call for all impediments)
    # ------------------------------------------------------------------

    def _formulate_proposals(
        self,
        impediments: List[ImpedimentItem],
        ground_truth: Dict,
    ) -> List[ImpedimentItem]:
        """LLM pass: fill proposed_resolution for each resolvable impediment."""
        resolvable = [i for i in impediments if i.resolvable and not i.proposed_resolution]
        if not resolvable:
            return impediments

        # Build a compact prompt — one structured request for all proposals
        items_text = "\n".join(
            f"{idx + 1}. [{i.impediment_type}/{i.severity}] {i.description}"
            f" (critic: {i.target_critic})"
            for idx, i in enumerate(resolvable)
        )

        existing_controls = ground_truth.get("controls_present", [])
        missing_controls = ground_truth.get("controls_missing", [])

        prompt = (
            "You are a security architecture advisor helping a ScrumMaster resolve "
            "impediments identified across expert critic reviews.\n\n"
            f"Existing controls: {existing_controls[:10]}\n"
            f"Missing controls (top 5): {missing_controls[:5]}\n\n"
            "For each numbered impediment below, provide ONE concrete, actionable "
            "resolution proposal in one sentence. Focus on what should change in the "
            "architecture or threat model — not process improvements.\n\n"
            f"{items_text}\n\n"
            "Return a JSON array with objects: "
            '[{"index": 1, "proposed_resolution": "..."}, ...]'
        )

        proposals_by_index: Dict[int, str] = {}
        try:
            from agentic.llm_client import LLMClient
            client = LLMClient()
            response = client.complete(prompt, model=self.model)
            # Parse JSON from response
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                proposals = json.loads(json_match.group())
                for p in proposals:
                    proposals_by_index[p.get("index", 0)] = p.get("proposed_resolution", "")
        except Exception as exc:
            logger.warning(f"ScrumMaster: proposal formulation failed: {exc}")
            # Fallback: mark all resolvable as needing manual review
            for i in resolvable:
                i.proposed_resolution = "Manual review required — ScrumMaster LLM call failed"
            return impediments

        # Apply proposals back to the matching impediments
        for idx, imp in enumerate(resolvable):
            proposal = proposals_by_index.get(idx + 1, "")
            if proposal:
                imp.proposed_resolution = proposal

        return impediments

    # ------------------------------------------------------------------
    # Step 5: Select critics to re-trigger
    # ------------------------------------------------------------------

    def _select_critics_to_retrigger(
        self,
        moe_result: "MoEResult",
        impediments: List[ImpedimentItem],
    ) -> List[str]:
        """Select max 2 critics: largest confidence drag AND addressable impediments."""
        # Build critic → drag score (larger absolute = more drag)
        drag: Dict[str, float] = {}
        for name, attr in _CRITIC_ADJUSTMENT_ATTRS.items():
            adj = getattr(moe_result, attr, 0.0)
            drag[name] = abs(adj)  # negative adjustment → positive drag score

        # Build critic → has_addressable_impediment
        addressable: Dict[str, bool] = {}
        for imp in impediments:
            if imp.resolvable and imp.proposed_resolution and imp.target_critic:
                addressable[imp.target_critic] = True

        # Score = drag × addressable (0 if no proposals)
        scored = {
            name: drag.get(name, 0.0)
            for name in _CRITIC_ADJUSTMENT_ATTRS
            if addressable.get(name) and drag.get(name, 0.0) > 0
        }

        if not scored:
            return []

        # Pick top 2 by drag score
        top = sorted(scored, key=lambda n: scored[n], reverse=True)[:2]
        return top

    # ------------------------------------------------------------------
    # Step 5: Re-trigger via MoEOrchestrator.run_targeted
    # ------------------------------------------------------------------

    def _retrigger_critics(
        self,
        critics: List[str],
        report_dir: str,
        proposals: List[Dict],
        moe_result: "MoEResult",
    ) -> "MoEResult":
        """Calls MoEOrchestrator.run_targeted — loads saved results for others."""
        from chatbot.modules.agents.orchestrators.moe_orchestrator import MoEOrchestrator
        orchestrator = MoEOrchestrator(model=self.model)
        return orchestrator.run_targeted(
            report_dir=report_dir,
            critics_to_run=critics,
            new_proposals_context={"scrum_master_proposals": proposals},
            base_confidence=moe_result.base_confidence,
        )

    # ------------------------------------------------------------------
    # Step 7: Build sharp prioritised action plan (LLM pass)
    # ------------------------------------------------------------------

    def _build_action_plan(
        self,
        moe_result: "MoEResult",
        resolved_impediments: List[ImpedimentItem],
        redesign_signal: bool,
    ) -> List[Dict]:
        """Build top-N sharp prioritised plan. NOT a long list."""
        if redesign_signal:
            return self._build_redesign_recommendations(moe_result)

        # Collect all recommendations from all critics
        all_recs: List[Dict] = list(getattr(moe_result, "critical_recommendations", []))
        all_recs += list(getattr(moe_result, "high_recommendations", []))

        # Add resolved impediments as confirmed items
        for imp in resolved_impediments:
            if imp.proposed_resolution:
                all_recs.append({
                    "priority": imp.severity,
                    "action": imp.proposed_resolution,
                    "rationale": f"ScrumMaster resolved: {imp.description}",
                    "source": "scrum_master",
                })

        if not all_recs:
            return []

        # LLM de-duplicate, rank, and trim to top-5
        recs_text = "\n".join(
            f"{idx + 1}. [{r.get('priority', 'medium')}] {r.get('action', str(r))}"
            for idx, r in enumerate(all_recs[:20])  # cap input to avoid huge prompts
        )

        prompt = (
            "You are a security advisor producing an action plan from expert critic findings.\n\n"
            "De-duplicate and rank these recommendations by: risk reduction × implementation effort. "
            "Return the top 5 as a JSON array.\n"
            "Each item: {\"priority\": \"critical|high|medium\", \"action\": \"...\", "
            "\"rationale\": \"why this matters\", \"risk_reduction_estimate\": \"high|medium|low\", "
            "\"effort\": \"days|weeks|months\"}\n\n"
            f"{recs_text}"
        )

        try:
            from agentic.llm_client import LLMClient
            import re
            client = LLMClient()
            response = client.complete(prompt, model=self.model)
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())[:5]
        except Exception as exc:
            logger.warning(f"ScrumMaster: action plan LLM call failed: {exc}")

        # Fallback: return top-5 raw recommendations
        return all_recs[:5]

    def _build_redesign_recommendations(self, moe_result: "MoEResult") -> List[Dict]:
        """Top-3 architectural redesign recommendations when redesign_signal=True."""
        blindspots = getattr(moe_result, "blindspots", [])[:3]
        contradictions = getattr(moe_result, "contradictions", [])[:3]

        recs = []
        for b in blindspots:
            desc = b.get("description", str(b)) if isinstance(b, dict) else str(b)
            recs.append({
                "priority": "critical",
                "action": f"Redesign: {desc}",
                "rationale": "Structural blindspot — incremental controls cannot address this",
                "risk_reduction_estimate": "high",
                "effort": "weeks",
            })
        for c in contradictions:
            desc = c.get("description", str(c)) if isinstance(c, dict) else str(c)
            if len(recs) >= 3:
                break
            recs.append({
                "priority": "high",
                "action": f"Resolve structural conflict: {desc}",
                "rationale": "Unresolvable cross-critic contradiction — requires architectural decision",
                "risk_reduction_estimate": "medium",
                "effort": "weeks",
            })
        return recs[:3]

    # ------------------------------------------------------------------
    # Step 6: Baseline feedback for det-engine
    # ------------------------------------------------------------------

    def _build_baseline_feedback(
        self,
        moe_result: "MoEResult",
        ground_truth: Dict,
        impediments: List[ImpedimentItem],
    ) -> BaselineFeedback:
        """Deterministic pass — identify det-engine improvement areas."""
        weak_controls: List[str] = []
        pattern_gaps: List[str] = []
        rapids_hints: Dict[str, float] = {}
        gt_gaps: List[str] = []

        # Weak controls: generic names that provide no actionable guidance
        generic_keywords = ["review", "monitor", "consider", "ensure", "implement security"]
        for ctrl in ground_truth.get("controls_missing", []):
            if any(kw in ctrl.lower() for kw in generic_keywords):
                weak_controls.append(ctrl)

        # Pattern gaps: unresolved_rec impediments that have no matching RAPIDS category
        rapids = ground_truth.get("rapids_assessment", {})
        for imp in impediments:
            if imp.impediment_type == "unresolved_rec" and not any(
                imp.description.lower() in cat.lower()
                for cat in rapids.keys()
            ):
                pattern_gaps.append(imp.description[:100])

        # RAPIDS weight hints: if a category has 0 threats but critic found gaps there
        threat_categories = ["ransomware", "lateral_movement", "exfiltration", "initial_access",
                             "privilege_escalation", "defense_evasion"]
        for cat in threat_categories:
            cat_score = rapids.get(cat, {})
            if isinstance(cat_score, dict) and cat_score.get("score", 0) == 0:
                # Check if any critic found gaps in this area
                matching_gaps = [
                    i for i in impediments
                    if cat.replace("_", " ") in i.description.lower()
                ]
                if matching_gaps:
                    rapids_hints[cat] = 0.1  # suggest slight weight increase

        # Ground truth gaps: areas with thin output
        if not ground_truth.get("expected_attack_paths"):
            gt_gaps.append("No attack paths generated — graph may be too sparse")
        if len(ground_truth.get("controls_present", [])) < 2:
            gt_gaps.append("Very few controls detected — consider enriching node labels")

        return BaselineFeedback(
            weak_controls=weak_controls[:10],
            pattern_gaps=list(dict.fromkeys(pattern_gaps))[:10],
            rapids_weight_hints=rapids_hints,
            ground_truth_gaps=gt_gaps,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_blindspots(self, moe_result: "MoEResult") -> List[str]:
        blindspots = getattr(moe_result, "blindspots", [])
        result = []
        for b in blindspots:
            desc = b.get("description", str(b)) if isinstance(b, dict) else str(b)
            result.append(desc)
        return result

    def _has_persistent_gaps(self, impediments: List[ImpedimentItem]) -> bool:
        """True if any high/critical impediment remains unresolved."""
        return any(
            i.severity in ("critical", "high") and not i.proposed_resolution
            for i in impediments
        )

    def _build_synthesis_note(
        self,
        initial: float,
        final: float,
        iterations: int,
        redesign: bool,
        retriggered: List[str],
        impediments: List[ImpedimentItem],
    ) -> str:
        n_found = len(impediments)
        n_critical = sum(1 for i in impediments if i.severity in ("critical", "high"))
        n_unresolvable = sum(1 for i in impediments if not i.resolvable)

        if redesign:
            return (
                f"ScrumMaster found {n_found} impediments ({n_critical} critical/high, "
                f"{n_unresolvable} structurally unresolvable). The architecture requires "
                "redesign before further critic rounds will improve confidence. "
                "Action plan focuses on architectural changes. "
                "Baseline feedback provided to guide deterministic engine improvements."
            )

        if initial >= 90.0:
            return (
                f"Confidence {initial:.1f}% met the 90% target. ScrumMaster produced a "
                f"sharp prioritised action plan from {n_found} impediments without "
                "re-triggering any critics."
            )

        delta = final - initial
        if iterations == 0:
            return (
                f"No re-triggering was needed. Confidence {initial:.1f}% with "
                f"{n_found} impediments found. Action plan produced from existing findings."
            )

        retrig_str = ", ".join(retriggered) if retriggered else "none"
        return (
            f"ScrumMaster ran {iterations} iteration(s). Confidence: "
            f"{initial:.1f}% → {final:.1f}% ({delta:+.1f}%). "
            f"Critics re-triggered: {retrig_str}. "
            f"Impediments found: {n_found} ({n_critical} critical/high). "
            + ("Baseline feedback provided for persistent gaps." if self._has_persistent_gaps(impediments) else "")
        )
