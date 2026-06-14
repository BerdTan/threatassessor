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
import time as _time
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
    perf: Dict = field(default_factory=dict)  # {llm_calls, llm_tokens, llm_cost_usd, llm_latency_s, llm_model, wall_clock_s}

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
        self._perf_acc: Dict = {}  # accumulated LLM telemetry for this run

    def _reset_perf(self) -> None:
        self._perf_acc = {"llm_calls": 0, "llm_tokens": 0, "llm_cost_usd": 0.0,
                          "llm_latency_s": 0.0, "llm_model": "", "wall_clock_s": 0.0}

    def _accum_perf(self, response) -> None:
        self._perf_acc["llm_calls"]    += 1
        self._perf_acc["llm_tokens"]   += getattr(response, "tokens_used",    0) or 0
        self._perf_acc["llm_cost_usd"] += getattr(response, "cost_usd",       0.0) or 0.0
        self._perf_acc["llm_latency_s"]+= getattr(response, "latency_seconds",0.0) or 0.0
        self._perf_acc["llm_model"]     = getattr(response, "model", self._perf_acc["llm_model"]) or self._perf_acc["llm_model"]

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

        _run_start = _time.time()
        self._reset_perf()

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
            baseline_fb = self._build_baseline_feedback(current_result, ground_truth, impediments, report_dir) \
                if self._has_persistent_gaps(impediments) else None
            self._perf_acc["wall_clock_s"] = round(_time.time() - _run_start, 3)
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
                perf=dict(self._perf_acc),
            )

        # Step 3: Harmony check — majority unresolvable → redesign signal
        harmony_ok = self._harmony_check(impediments)
        if not harmony_ok:
            logger.info("ScrumMaster: harmony check failed — redesign_signal=True")
            baseline_fb = self._build_baseline_feedback(current_result, ground_truth, impediments, report_dir)
            action_plan = self._build_action_plan(current_result, [], redesign_signal=True)
            self._perf_acc["wall_clock_s"] = round(_time.time() - _run_start, 3)
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
                perf=dict(self._perf_acc),
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
        baseline_fb = self._build_baseline_feedback(current_result, ground_truth, impediments, report_dir) \
            if has_persistent else None

        # Step 7: Build sharp prioritised action plan
        if progress_callback:
            progress_callback("scrum_master", 95, "ScrumMaster: building action plan...")

        action_plan = self._build_action_plan(current_result, resolved_impediments, redesign_signal=False)

        self._perf_acc["wall_clock_s"] = round(_time.time() - _run_start, 3)
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
            perf=dict(self._perf_acc),
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
            import re
            client = LLMClient()
            response = client.generate(prompt=prompt, system_message="You are a security architecture advisor. Return only valid JSON.", model=self.model)
            self._accum_perf(response)
            content = response.content if hasattr(response, "content") else str(response)
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
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
    # Step 7: Strategist action plan (LLM pass)
    # ------------------------------------------------------------------

    def _build_action_plan(
        self,
        moe_result: "MoEResult",
        resolved_impediments: List[ImpedimentItem],
        redesign_signal: bool,
    ) -> List[Dict]:
        """Strategist action plan — Less controls, more defensible.

        Principles:
        - Fewer controls that block the actual attack paths > many controls that add noise
        - Each item carries a confidence estimate (how much it recovers)
        - Anti-patterns are flagged: convenience without effectiveness
        - Ranked by: confidence_gain × path_coverage × simplicity (not just priority label)
        """
        if redesign_signal:
            return self._build_redesign_recommendations(moe_result)

        # ── Source material ───────────────────────────────────────────────────
        critical_recs: List[Dict] = list(getattr(moe_result, "critical_recommendations", []))
        high_recs: List[Dict] = list(getattr(moe_result, "high_recommendations", []))

        for imp in resolved_impediments:
            if imp.proposed_resolution:
                high_recs.append({
                    "priority": imp.severity,
                    "action": imp.proposed_resolution,
                    "rationale": f"Confirmed by ScrumMaster: {imp.description}",
                    "source": "scrum_master",
                })

        all_recs = critical_recs + high_recs
        if not all_recs:
            return []

        # ── Derive confidence gain estimates from critic adjustments ──────────
        # Each critic's confidence_adjustment tells us how much that domain dragged.
        # If a control directly addresses that critic's top gap, it can recover part
        # of the adjustment.
        critic_adjustments = {}
        for name, attr in _CRITIC_ADJUSTMENT_ATTRS.items():
            adj = getattr(moe_result, attr, 0.0)
            if adj < 0:
                critic_adjustments[name] = abs(adj)  # positive drag value

        total_drag = sum(critic_adjustments.values()) or 0.01

        # Anti-pattern keywords — controls that look impressive but have low
        # effectiveness in aggressive risk reduction
        _ANTIPATTERNS = [
            "policy", "process", "procedure", "training", "awareness",
            "document", "review periodically", "governance framework",
            "consider", "monitor and review", "risk accept",
        ]

        def _is_antipattern(action: str) -> bool:
            a = action.lower()
            return any(kw in a for kw in _ANTIPATTERNS)

        def _source_critic(rec: Dict) -> str:
            src = (rec.get("source") or "").lower()
            if "architect" in src: return "architect"
            if "tester" in src or "coverage" in src: return "tester"
            if "red" in src or "exploit" in src: return "red_team"
            if "purple" in src: return "purple_team"
            if "black" in src: return "blackhat"
            return ""

        def _confidence_gain_pct(rec: Dict) -> float:
            """Estimate confidence recovery if this item is addressed.

            Logic: items that address the highest-drag critic recover more confidence.
            KNOWN (multi-critic) items recover more than UNSURE (single-critic) items.
            Anti-patterns recover near-zero regardless of priority label.
            """
            if _is_antipattern(rec.get("action", "")):
                return 0.5  # negligible — process controls rarely move the needle

            is_known = (rec.get("confidence_label") == "KNOWN"
                        or "+" in (rec.get("source") or ""))
            critic = _source_critic(rec)
            drag = critic_adjustments.get(critic, 0.0)

            # Base: proportion of total drag this critic holds
            base_pct = (drag / total_drag) * 100 if total_drag else 0
            # KNOWN findings recover more (consensus = higher confidence that fix helps)
            multiplier = 1.5 if is_known else 0.8
            # Critical recommendations recover more than high
            prio_mult = 1.2 if rec.get("priority") == "critical" else 1.0
            return round(base_pct * multiplier * prio_mult, 1)

        # ── Score and annotate every rec ──────────────────────────────────────
        scored = []
        for rec in all_recs[:20]:
            action = rec.get("action") or rec.get("description") or rec.get("recommendation") or ""
            if not action:
                continue
            conf_gain = _confidence_gain_pct(rec)
            antipattern = _is_antipattern(action)
            scored.append({
                "_action":     action,
                "_conf_gain":  conf_gain,
                "_antipattern": antipattern,
                "_rec":        rec,
            })

        # Sort: highest confidence gain first; anti-patterns last
        scored.sort(key=lambda x: (not x["_antipattern"], x["_conf_gain"]), reverse=True)

        # ── LLM: strategist rewrite — concrete, simple, ranked ───────────────
        top_raw = scored[:8]
        recs_text = "\n".join(
            f"{i+1}. [conf_gain={r['_conf_gain']:.1f}%] [antipattern={r['_antipattern']}] "
            f"{r['_action'][:120]}"
            for i, r in enumerate(top_raw)
        )

        base_conf = getattr(moe_result, "base_confidence", 99.5)
        final_conf = getattr(moe_result, "final_confidence", base_conf)

        prompt = (
            "You are a security architect applying a strategist mindset to an action plan.\n\n"
            f"Current validated confidence: {final_conf:.1f}%. Target: 90%.\n"
            f"Gap to close: {max(0, 90 - final_conf):.1f}%.\n\n"
            "Principles:\n"
            "1. Simplicity is king — fewer controls with genuine path-blocking effect beat a long list.\n"
            "2. Design with less control yet more defensible — each item must directly block or "
            "significantly impede a real attack path. Remove anything that adds process overhead "
            "without measurably reducing attacker capability.\n"
            "3. Avoid anti-patterns — policy reviews, awareness training, governance frameworks, "
            "and 'monitor and review' items rarely move the needle. Flag them if they must appear, "
            "but rank them last.\n"
            "4. Confidence gain matters — items with higher conf_gain recover more confidence "
            "per unit of effort. Prioritise ruthlessly.\n\n"
            "Input (ranked by estimated confidence gain, with anti-pattern flag):\n"
            f"{recs_text}\n\n"
            "Return the top 5 as a JSON array. For each item:\n"
            "- Rewrite 'action' as a concrete, one-sentence engineering instruction "
            "(what to build/configure/add — not what to review or consider)\n"
            "- 'rationale': ONE sentence — why this specific control blocks the attack path\n"
            "- 'confidence_gain': estimated % confidence recovery if implemented (from conf_gain input)\n"
            "- 'priority': critical | high | medium (based on conf_gain and path coverage)\n"
            "- 'effort': days | weeks | months\n"
            "- 'risk_reduction_estimate': high | medium | low\n"
            "- 'is_antipattern': true | false\n"
            "- 'first_step': the single most concrete first action (tool, config, code change)\n\n"
            "JSON only, no explanation outside the array."
        )

        try:
            from agentic.llm_client import LLMClient
            import re
            client = LLMClient()
            response = client.generate(prompt=prompt, system_message="You are a security prioritisation expert. Return only valid JSON.", model=self.model)
            self._accum_perf(response)
            response = response.content if hasattr(response, "content") else str(response)
            json_match = re.search(r'\[.*?\]', response, re.DOTALL)
            if json_match:
                items = json.loads(json_match.group())
                # Ensure confidence_gain and is_antipattern are present; merge from scored
                result = []
                for item in items[:5]:
                    if isinstance(item, dict) and item.get("action"):
                        if "confidence_gain" not in item:
                            # Find matching scored item by action text similarity
                            for s in top_raw:
                                if s["_action"][:40].lower() in item["action"].lower():
                                    item["confidence_gain"] = s["_conf_gain"]
                                    item["is_antipattern"] = s["_antipattern"]
                                    break
                        result.append(item)
                if result:
                    return result
        except Exception as exc:
            logger.warning(f"ScrumMaster: strategist action plan LLM call failed: {exc}")

        # ── Fallback: annotate top-5 deterministically ────────────────────────
        result = []
        for s in scored[:5]:
            r = dict(s["_rec"])
            r["action"] = s["_action"]
            r["confidence_gain"] = s["_conf_gain"]
            r["is_antipattern"] = s["_antipattern"]
            if not r.get("first_step"):
                r["first_step"] = "Implement this control and verify in the next Expert Review run."
            result.append(r)
        return result

    def _build_redesign_recommendations(self, moe_result: "MoEResult") -> List[Dict]:
        """Tiered action plan when redesign_signal=True.

        Tier A — Immediate: resolvable medium/low impediments (apply controls now,
                            don't wait for redesign — reduces risk while architecture work happens).
        Tier B — Structural: unresolvable critical/high impediments translated into
                             concrete architectural decisions with sequenced next steps.

        Each item includes: what to do, why it matters, first concrete step, effort.
        """
        recs = []

        # ── Tier A: Immediate actions on resolvable impediments ──────────────
        # Pull from MoE consensus critical/high recommendations — these are actionable NOW
        critical_recs = list(getattr(moe_result, "critical_recommendations", []))
        high_recs = list(getattr(moe_result, "high_recommendations", []))
        for r in (critical_recs + high_recs)[:3]:
            action = r.get("action") or r.get("description") or r.get("recommendation") or str(r)
            evidence = r.get("evidence", "")
            recs.append({
                "priority": "high",
                "action": f"[Immediate] {action}",
                "rationale": f"Actionable now — does not require architectural redesign. {evidence}".strip(". ") + ".",
                "risk_reduction_estimate": "medium",
                "effort": "days",
                "tier": "immediate",
                "first_step": f"Add this control to the relevant ADR and assign an owner. Verify in the next Expert Review run.",
            })

        # ── Tier B: Structural changes — translated into decisions, not descriptions ─
        # Map each blindspot/unresolvable contradiction to a concrete architectural decision
        blindspots = getattr(moe_result, "blindspots", [])
        contradictions = getattr(moe_result, "contradictions", [])

        # Concrete translation map for common blindspot themes
        _DECISION_MAP = {
            "vendor":           ("Add a Vendor Risk Assessment node to the architecture. Define contract SLAs for security incident notification and minimum control requirements. Map to relevant attack paths.",  "Schedule vendor security review; add vendor_risk_assessment node to .mmd"),
            "supply chain":     ("Introduce a Software Composition Analysis (SCA) gate in the CI/CD pipeline. Add dependency inventory node. Map supply chain attack paths explicitly.",                            "Add SCA tool to pipeline; identify top 5 third-party dependencies with no security SLA"),
            "continuity":       ("Define RTO/RPO targets per attack path criticality tier. Add BCP/DR controls to ADRs for HIGH/CRITICAL paths. Model availability impact in the threat model.",                 "Map current attack paths to availability impact; add recovery_time_objective field to top 3 ADRs"),
            "mobile":           ("Add mobile app security layer to architecture (certificate pinning, device attestation, jailbreak detection). Model client-side attack surface as a separate trust zone.",       "Add mobile_security_controls subgraph to .mmd; re-run analysis"),
            "api gateway":      ("Reposition API Gateway as the single ingress point with authentication/authorization enforcement. Remove direct backend service exposure. Add east-west traffic inspection.",    "Redraw architecture so all external traffic routes through API Gateway; add WAF and auth enforcement controls"),
            "detection":        ("Add dedicated detection layer: SIEM correlation rules, UEBA baselines, and anomaly thresholds per attack path type. Separate detection controls from preventive controls in ADRs.", "Define alert thresholds for top 3 attack paths; add detection_layer subgraph to .mmd"),
            "insider":          ("Add privileged access management (PAM) and user behavior analytics (UEBA) as explicit architecture nodes. Model insider threat attack paths separately.",                         "Add PAM node; create dedicated insider_threat attack path in analysis"),
            "compliance":       ("Map all L0 cardinal controls to architecture nodes. Create a compliance coverage matrix. Flag any nodes with zero L0 control coverage.",                                         "Run SSP gap analysis; add missing L0 controls to the action plan immediately"),
            "segmentation":     ("Implement microsegmentation between services — add network zone boundaries to .mmd. Each service should only accept connections from known callers.",                            "Add microsegmentation subgraph; add firewall_rules and service_mesh nodes"),
        }

        for source_list, source_type in [(blindspots, "blindspot"), (contradictions, "contradiction")]:
            for item in source_list:
                if len(recs) >= 6:
                    break
                desc = item.get("description", str(item)) if isinstance(item, dict) else str(item)
                desc_lower = desc.lower()

                # Find best matching decision template
                decision_action, first_step = None, None
                for keyword, (action, step) in _DECISION_MAP.items():
                    if keyword in desc_lower:
                        decision_action, first_step = action, step
                        break

                if not decision_action:
                    # Generic structural decision template — still more useful than "redesign this"
                    short = desc[:80].rstrip(".")
                    decision_action = (
                        f"Address structural gap: {short}. "
                        "Add the missing component as an explicit architecture node in the .mmd diagram, "
                        "assign a trust zone, and re-run analysis to generate attack paths and controls for it."
                    )
                    first_step = f"Identify the missing component. Add it to the .mmd file. Re-run analysis."

                priority = "critical" if source_type == "blindspot" else "high"
                recs.append({
                    "priority": priority,
                    "action": f"[Structural] {decision_action}",
                    "rationale": f"{'Structural blindspot' if source_type == 'blindspot' else 'Unresolvable cross-critic contradiction'} — cannot be addressed by adding controls to the current architecture. Original gap: {desc[:120]}",
                    "risk_reduction_estimate": "high",
                    "effort": "weeks",
                    "tier": "structural",
                    "first_step": first_step,
                })

        # Ensure we have at least something when both tiers are empty
        if not recs:
            recs.append({
                "priority": "high",
                "action": "[Structural] Review architecture scope — critics found no addressable gaps but confidence remains below target.",
                "rationale": "No concrete impediments surfaced — the architecture diagram may be under-specified. Add missing services, trust boundaries, and data stores.",
                "risk_reduction_estimate": "medium",
                "effort": "days",
                "tier": "structural",
                "first_step": "Review .mmd for missing nodes. Add any external dependencies, databases, and inter-service connections not currently modelled.",
            })

        return recs

    # ------------------------------------------------------------------
    # Step 6: Baseline feedback for det-engine
    # ------------------------------------------------------------------

    def _build_baseline_feedback(
        self,
        moe_result: "MoEResult",
        ground_truth: Dict,
        impediments: List[ImpedimentItem],
        report_dir: Optional[str] = None,
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

        # RAPIDS weight hints: fire when a critic found significant gaps in a threat
        # category but the RAPIDS score for that category is low (may be under-weighted).
        #
        # Mapping: keyword phrases critics use → actual RAPIDS category key
        # (RAPIDS keys are: ransomware, application_vulns, phishing,
        #                   insider_threat, dos, supply_chain)
        _KEYWORD_TO_RAPIDS = {
            # lateral movement maps to insider_threat (post-compromise pivot)
            "lateral movement":   "insider_threat",
            "lateral move":       "insider_threat",
            "pivot":              "insider_threat",
            "east-west":          "insider_threat",
            # exfiltration maps to application_vulns
            "exfiltration":       "application_vulns",
            "data exfil":         "application_vulns",
            "data loss":          "application_vulns",
            # privilege escalation maps to insider_threat
            "privilege escalat":  "insider_threat",
            "escalat":            "insider_threat",
            # initial access maps to ransomware (entry-point category)
            "initial access":     "ransomware",
            "initial compromise": "ransomware",
            # supply chain / third party maps to supply_chain
            "supply chain":       "supply_chain",
            "third.party":        "supply_chain",
            "vendor":             "supply_chain",
            # detection gaps map to phishing (behavioural / social engineering)
            "detection gap":      "phishing",
            "behavioral detect":  "phishing",
            "ueba":               "phishing",
            # availability / dos
            "availability":       "dos",
            "denial of service":  "dos",
        }

        # Collect RAPIDS keys that critics flagged, with a count of matching impediments
        critic_flags: Dict[str, int] = {}
        for imp in impediments:
            desc_lower = imp.description.lower()
            for keyword, rapids_key in _KEYWORD_TO_RAPIDS.items():
                if keyword in desc_lower:
                    critic_flags[rapids_key] = critic_flags.get(rapids_key, 0) + 1
                    break

        # For each flagged RAPIDS category, check if its current risk score
        # is below 60 (medium). If critics found ≥2 impediments pointing there,
        # suggest a +10% weight; if ≥4 impediments, suggest +20%.
        for rapids_key, flag_count in critic_flags.items():
            cat_data = rapids.get(rapids_key, {})
            current_risk = cat_data.get("risk", 0) if isinstance(cat_data, dict) else 0
            if current_risk < 60 and flag_count >= 2:
                hint = 0.20 if flag_count >= 4 else 0.10
                rapids_hints[rapids_key] = hint

        # Ground truth gaps: areas with thin output
        if not ground_truth.get("expected_attack_paths"):
            gt_gaps.append(
                "No attack paths generated — graph may be too sparse. "
                "Add intermediate service nodes between entry points and data stores "
                "so the BFS engine can find multi-hop paths."
            )
        n_controls = len(ground_truth.get("controls_present", []))
        if n_controls < 2:
            # Choose the most appropriate MMD file to reference — not always after.mmd:
            # - 08b_recommended_target.mmd: balanced set, best starting point for most cases
            # - 08a_quick_wins.mmd: if only quick wins are feasible (simple architecture)
            # - after.mmd: full set, only if no tier diagrams exist
            # Pick based on what actually exists in the report directory
            ref_mmd = "after.mmd"  # safe fallback
            ref_reason = "all recommended controls"
            if report_dir:
                _rp = Path(report_dir)
                if (_rp / "08b_recommended_target.mmd").exists():
                    ref_mmd = "08b_recommended_target.mmd"
                    ref_reason = "the balanced Recommended tier controls (⭐ — best ROI/effort tradeoff)"
                elif (_rp / "08a_quick_wins.mmd").exists():
                    ref_mmd = "08a_quick_wins.mmd"
                    ref_reason = "the Quick Wins tier controls (⚡ — highest impact, lowest effort)"
                # If only after.mmd exists (no tier diagrams yet), fall back to it
                elif not (_rp / "after.mmd").exists():
                    ref_mmd = None

            if ref_mmd:
                gt_gaps.append(
                    f"Only {n_controls} control(s) detected in node labels. "
                    f"Open {ref_mmd} — it already shows {ref_reason} as NEW_* nodes. "
                    "Copy the relevant NEW_* node definitions into your source .mmd file "
                    "and rename them (e.g. NEW_MFA → MFA[Multi-Factor Authentication]). "
                    "The engine reads control keywords from node labels, so promoting "
                    "NEW_* nodes makes them visible to RAPIDS scoring and attack path ranking. "
                    "Re-run analysis after updating the diagram."
                )
            else:
                gt_gaps.append(
                    f"Only {n_controls} control(s) detected in node labels. "
                    "Run a full analysis first to generate tier diagrams (08a/08b/08c.mmd), "
                    "then copy the NEW_* control nodes from the recommended tier into your source diagram."
                )

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
        n_resolvable = n_found - n_unresolvable

        if redesign:
            # Clarify: n_unresolvable is a subset of n_found, not additive
            unres_note = f"all {n_unresolvable}" if n_unresolvable == n_found else f"{n_unresolvable} of {n_found}"
            return (
                f"ScrumMaster found {n_found} impediments — {unres_note} are structurally unresolvable "
                f"({n_critical} critical/high severity). "
                f"{'No impediments can be addressed with incremental controls alone. ' if n_resolvable == 0 else f'{n_resolvable} can be addressed with immediate controls while structural changes are made. '}"
                "The action plan is tiered: immediate control additions first, then architectural decisions with concrete first steps. "
                "Baseline feedback provided to guide the next analysis pass."
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
