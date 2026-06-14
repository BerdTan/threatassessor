"""
Concrete pipeline stage implementations for ThreatAssessorHarness.

All imports from project modules are deferred (inside _logic methods) to
avoid circular imports at module load time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from chatbot.modules.harness import PipelineContext, PipelineStage


class AnalysisStage(PipelineStage):
    """Deterministic threat analysis: parse → RAPIDS → pattern detection → confidence.

    Required stage — failure halts the pipeline.
    Wraps ThreatAnalysisService.safe_execute().
    """

    name = "analysis"
    required = True

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        from chatbot.services import ThreatAnalysisService

        service = ThreatAnalysisService()
        safe_kw = {}
        if ctx.get("architecture_name"):
            safe_kw["architecture_name"] = ctx["architecture_name"]
        result = service.safe_execute(
            architecture_path=ctx["architecture_path"],
            include_validation=ctx.get("include_validation", True),
            ssp_profile=ctx.get("ssp_profile", "low_risk_cloud"),
            enable_ssp=ctx.get("enable_ssp", True),
            **safe_kw,
        )

        ctx["service_result"] = result
        ctx["ground_truth"] = result.data.get("analysis", {})
        ctx["confidence"] = result.data.get("confidence", 0)
        ctx["patterns_applied"] = result.data.get("patterns_applied", [])

        if cb := kw.get("progress_callback"):
            cb("analysis", 55, "Threat analysis complete")

        return ctx


class ReportStage(PipelineStage):
    """APT/CVE enrichment + all markdown report generation.

    Optional — failure is logged, pipeline continues.
    Wraps generate_report_package() which handles: ADRs, narrative enrichment,
    threat scene deepening (APT attribution, KEV CVEs), threat model, diagrams.
    """

    name = "report"
    required = False

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        from chatbot.modules.threat_report import generate_report_package

        # generate_report_package appends the architecture name to output_dir
        # report_dir is already the fully-qualified arch directory; its parent
        # is the base output dir that generate_report_package expects.
        output_dir = str(Path(ctx["report_dir"]).parent)

        paths = generate_report_package(
            original_mmd_path=ctx["architecture_path"],
            ground_truth=ctx["ground_truth"],
            output_dir=output_dir,
        )
        ctx["report_paths"] = paths

        if cb := kw.get("progress_callback"):
            cb("report", 75, "Reports generated")

        return ctx


class CriticStage(PipelineStage):
    """MoE expert validation: Architect, Tester, Red Team (+ optional Purple/Blackhat).

    Optional — only runs when ctx["enable_moe"] is True.
    Wraps run_moe_pipeline(); saves critic JSON files to report_dir.
    """

    name = "critics"
    required = False

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        if not ctx.get("enable_moe", False):
            return ctx

        from chatbot.modules.agents.orchestrators.moe_orchestrator import run_moe_pipeline

        ctx["moe_result"] = run_moe_pipeline(
            str(ctx["report_dir"]),
            base_confidence=ctx.get("confidence"),
            critic_mode=ctx.get("critic_mode", "sequential"),
            run_blackhat=ctx.get("run_blackhat"),
            progress_callback=kw.get("progress_callback"),
        )

        if cb := kw.get("progress_callback"):
            cb("critics", 88, "Expert review complete")

        return ctx


class ScrumMasterStage(PipelineStage):
    """ScrumMaster meta-critic synthesis.

    Optional — requires ctx["moe_result"] to be populated (runs after CriticStage).
    Reads all ValidationResults, identifies impediments, drives confidence higher
    through targeted re-triggering (up to max_iterations), and produces a sharp
    prioritised action plan. Signals redesign when the architecture is structurally
    limited rather than brute-forcing further critic rounds.
    """

    name = "scrum_master"
    required = False

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        if not ctx.get("moe_result"):
            return ctx   # nothing to synthesise without MoE results

        from chatbot.modules.agents.critics.scrum_master_critic import ScrumMasterCritic
        import json

        model = ctx.get("_scrum_master_model")

        sm = ScrumMasterCritic(model=model)
        sm_result = sm.run(
            moe_result=ctx["moe_result"],
            report_dir=ctx["report_dir"],
            ground_truth=ctx["ground_truth"],
            progress_callback=kw.get("progress_callback"),
        )
        ctx["scrum_master_result"] = sm_result

        # ── Persist to disk (08_scrum_master.json) ──────────────────────────
        try:
            sm_path = Path(ctx["report_dir"]) / "08_scrum_master.json"
            sm_path.parent.mkdir(parents=True, exist_ok=True)
            with open(sm_path, "w") as f:
                json.dump(sm_result.to_dict(), f, indent=2)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"ScrumMasterStage: could not save result: {exc}")

        # ── Tag SM-enhanced items in ground_truth for reports ────────────────
        gt = ctx.get("ground_truth", {})
        if sm_result.action_plan:
            gt["scrum_master_action_plan"] = sm_result.action_plan
        if sm_result.redesign_signal and sm_result.baseline_feedback:
            import dataclasses
            gt["scrum_master_baseline_feedback"] = dataclasses.asdict(sm_result.baseline_feedback)
        gt["scrum_master_critics_retriggered"] = sm_result.critics_retriggered
        gt["scrum_master_synthesis_note"] = sm_result.synthesis_note
        gt["scrum_master_redesign_signal"] = sm_result.redesign_signal
        gt["scrum_master_final_confidence"] = sm_result.final_confidence
        gt["scrum_master_confidence_trajectory"] = sm_result.confidence_trajectory

        # ── Merge SM actions into improvement tiers (07_moe_orchestrator.json) ─
        # SM action items are classified by priority into the existing tier buckets:
        #   critical/high  → quick_wins  (highest ROI, act first)
        #   medium         → recommended (balanced tier)
        #   low/unset      → maximum     (full-coverage tier)
        # Items are tagged with source="scrum_master" so dashboard can badge them.
        # After merge, 08_improvement_summary.md is regenerated to stay in sync.
        self._merge_sm_into_tiers(sm_result, ctx["report_dir"])

        if cb := kw.get("progress_callback"):
            cb("scrum_master", 96, "ScrumMaster synthesis complete")

        return ctx

    def _merge_sm_into_tiers(self, sm_result, report_dir: str) -> None:
        """Inject SM action items into 07_moe_orchestrator.json improvement tiers,
        then regenerate 08_improvement_summary.md so all improvement reports stay in sync.
        """
        import json
        import logging
        _log = logging.getLogger(__name__)

        report_path = Path(report_dir)
        moe_path = report_path / "07_moe_orchestrator.json"
        if not moe_path.exists() or not sm_result.action_plan:
            return

        try:
            with open(moe_path) as f:
                moe_data = json.load(f)
        except Exception as exc:
            _log.warning(f"ScrumMasterStage: could not read 07_moe_orchestrator.json: {exc}")
            return

        tiers = moe_data.setdefault("improvement_options", {})

        # Priority → tier mapping
        _TIER_MAP = {
            "critical": "quick_wins",
            "high":     "quick_wins",
            "medium":   "recommended",
            "low":      "maximum",
        }

        # Track which item texts are already present (dedup across all tiers)
        existing_texts: set = set()
        for tier_obj in tiers.values():
            if isinstance(tier_obj, dict):
                for item in tier_obj.get("items", []):
                    existing_texts.add(str(item).lower()[:80])

        injected: dict = {"quick_wins": [], "recommended": [], "maximum": []}

        for item in sm_result.action_plan:
            action_text = item.get("action", "")
            if not action_text:
                continue
            # Dedup: skip if a closely matching item already exists
            key = action_text.lower()[:80]
            if key in existing_texts:
                continue
            existing_texts.add(key)

            priority = item.get("priority", "medium").lower()
            tier_key = _TIER_MAP.get(priority, "recommended")

            # Build a tagged string entry: "[SM] <action> — <rationale>"
            rationale = item.get("rationale", "")
            effort = item.get("effort", "")
            rr = item.get("risk_reduction_estimate", "")
            suffix_parts = []
            if rationale:
                suffix_parts.append(rationale)
            if effort:
                suffix_parts.append(f"effort: {effort}")
            if rr:
                suffix_parts.append(f"risk reduction: {rr}")
            suffix = " | ".join(suffix_parts)
            tagged = f"[SM] {action_text}" + (f" — {suffix}" if suffix else "")

            injected[tier_key].append(tagged)

        # Inject into tier objects; create tier stub if tier was empty/missing
        tier_defaults = {
            "quick_wins":  {"name": "Quick Wins",         "effort": "not estimated", "cost": "cost not estimated",
                            "risk_reduction": "—", "residual": "", "practical_verdict": "not assessed",
                            "rationale": "Highest ROI items identified by ScrumMaster analysis."},
            "recommended": {"name": "Recommended Target", "effort": "not estimated", "cost": "cost not estimated",
                            "risk_reduction": "—", "residual": "", "practical_verdict": "not assessed",
                            "rationale": "Balanced items identified by ScrumMaster analysis."},
            "maximum":     {"name": "Maximum Security",   "effort": "not estimated", "cost": "cost not estimated",
                            "risk_reduction": "—", "residual": "", "practical_verdict": "not assessed",
                            "rationale": "Full-coverage items identified by ScrumMaster analysis."},
        }

        changed = False
        for tier_key, new_items in injected.items():
            if not new_items:
                continue
            if tier_key not in tiers:
                tiers[tier_key] = dict(tier_defaults[tier_key])
                tiers[tier_key]["items"] = []
            elif not isinstance(tiers[tier_key], dict):
                continue
            tiers[tier_key].setdefault("items", [])
            tiers[tier_key]["items"].extend(new_items)
            # Mark tier as SM-enhanced so dashboard can show a badge
            tiers[tier_key]["sm_enhanced"] = True
            changed = True

        if not changed:
            return  # nothing new to write

        # Tag the top-level SM confidence data
        moe_data["scrum_master"] = {
            "final_confidence":      sm_result.final_confidence,
            "confidence_delta":      sm_result.confidence_delta,
            "redesign_signal":       sm_result.redesign_signal,
            "iterations_run":        sm_result.iterations_run,
            "critics_retriggered":   sm_result.critics_retriggered,
            "synthesis_note":        sm_result.synthesis_note,
        }

        try:
            with open(moe_path, "w") as f:
                json.dump(moe_data, f, indent=2)
            _log.info(f"ScrumMasterStage: merged SM items into {moe_path.name}")
        except Exception as exc:
            _log.warning(f"ScrumMasterStage: could not write {moe_path.name}: {exc}")
            return

        # Regenerate 08_improvement_summary.md now that tiers are updated
        try:
            from chatbot.modules.improvement_summary_generator import generate_summary
            generate_summary(str(report_path), orchestrator_result=moe_data)
            _log.info("ScrumMasterStage: regenerated 08_improvement_summary.md")
        except Exception as exc:
            _log.warning(f"ScrumMasterStage: could not regenerate improvement summary: {exc}")
