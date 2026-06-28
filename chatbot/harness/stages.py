"""
Concrete pipeline stage implementations for ThreatAssessorHarness.

All imports from project modules are deferred (inside _logic methods) to
avoid circular imports at module load time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from chatbot.harness.controller import PipelineContext, PipelineStage


class AnalysisStage(PipelineStage):
    """Deterministic threat analysis: parse → RAPIDS → pattern detection → confidence.

    Required stage — failure halts the pipeline.
    Wraps ThreatAnalysisService.safe_execute().
    """

    name = "analysis"
    required = True

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        from chatbot.services import ThreatAnalysisService

        # Capture raw MMD content before service call (used by QualityStage)
        try:
            ctx["_raw_mmd_content"] = Path(ctx["architecture_path"]).read_text(errors="replace")
        except Exception:
            ctx["_raw_mmd_content"] = ""

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

        # Apply AIVSS gate tightening before critics run (inbound score already computed)
        gate = ctx.get("_aivss_gate")
        aivss = ctx.get("_aivss_score")
        if gate is not None and aivss is not None:
            try:
                gate.tighten(ctx.get("_moe_orchestrator"), aivss.inbound)
            except Exception:
                pass

        from chatbot.modules.agents.orchestrators.moe_orchestrator import run_moe_pipeline

        guardian = ctx.get("_model_guardian")
        agent_models = guardian.models_dict(
            ["architect", "tester", "red_team", "purple_team", "blackhat", "moe_orchestrator"]
        ) if guardian else {}

        ctx["moe_result"] = run_moe_pipeline(
            str(ctx["report_dir"]),
            base_confidence=ctx.get("confidence"),
            critic_mode=ctx.get("critic_mode", "sequential"),
            run_blackhat=ctx.get("run_blackhat"),
            blocked_agents=ctx.get("blocked_agents", []),
            progress_callback=kw.get("progress_callback"),
            agent_models=agent_models or None,
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

        guardian = ctx.get("_model_guardian")
        model = guardian.get_model("scrum_master") if guardian else None

        sm = ScrumMasterCritic(model=model)
        # Expose per-critic models so ScrumMaster can thread them into re-triggered runs
        if guardian:
            sm._agent_models = guardian.models_dict(
                ["architect", "tester", "red_team", "purple_team", "blackhat"]
            )
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


class QualityStage(PipelineStage):
    """Governance checks on input MMD and ground_truth artifact.

    Optional — never fatal. Writes governance_signals.json to report_dir and
    stores the signals dict in ctx["governance_signals"] for SSE emission.
    Blocks the pipeline only if exploitation.severity == CRITICAL and blocked == True
    (by appending to ctx.errors, which halts a required-stage check upstream).
    """

    name = "quality"
    required = False

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        try:
            from chatbot.harness.governance import (
                get_governance_adapter,
                save_governance_signals,
            )
        except ImportError:
            return ctx  # governance module absent — skip silently

        try:
            adapter = ctx.get("_governance_adapter") or get_governance_adapter()

            input_sig = adapter.check_input(
                ctx.get("_raw_mmd_content", ""),
                ctx.get("architecture_path", ""),
            )
            artifact_sig = adapter.check_artifact(ctx.get("ground_truth", {}))
            merged = input_sig.merge(artifact_sig)
            merged.architecture_name = ctx.get("architecture_name", "")

            # Resolve blocked_agents from governance policy
            blocked: list = []
            try:
                import yaml
                from pathlib import Path as _Path
                _policy = yaml.safe_load(_Path("policies/agent_governance.yaml").read_text())
                _agent_policy = _policy.get("agent_policy", {})
                if merged.exploitation.get("severity") == "CRITICAL":
                    blocked.extend(_agent_policy.get("blocked_agents_on_critical", []))
                if merged.overall_risk_level == "HIGH":
                    blocked.extend(_agent_policy.get("blocked_agents_on_high", []))
            except Exception:
                pass
            merged.blocked_agents = list(set(blocked))
            ctx["blocked_agents"] = merged.blocked_agents

            ctx["governance_signals"] = merged.to_dict()

            # Save governance signals now (without AIVSS — full score happens in AIVSSStage
            # after critics + SM have run, so moe_result and scrum_master_result are available)
            from chatbot.config.settings import get_settings
            if get_settings().governance.save_signals_per_run and ctx.get("report_dir"):
                save_governance_signals(merged, ctx["report_dir"])

            # Only surface as pipeline error on CRITICAL blocked input
            if merged.exploitation.get("severity") == "CRITICAL" and merged.exploitation.get("blocked"):
                patterns = merged.exploitation.get("injection_patterns", []) or \
                           merged.exploitation.get("path_traversal", [])
                ctx.errors.append(f"quality: input blocked — {patterns[:3]}")

            if cb := kw.get("progress_callback"):
                cb("quality", 60, f"Governance check — risk: {merged.overall_risk_level}")

            # Pre-build the gate object so CriticStage can tighten thresholds before critics run.
            # Full AIVSS scoring (inbound/internal/outbound) happens in AIVSSStage after SM.
            try:
                from chatbot.modules.harness_aivss import AIVSSAgentGate
                from chatbot.config.settings import get_settings as _gs
                gate = AIVSSAgentGate(critic_settings=_gs().critics)
                ctx["_aivss_gate"] = gate
            except Exception as gate_exc:
                import logging as _log
                _log.getLogger(__name__).warning(f"AIVSS gate setup failed (non-fatal): {gate_exc}")

        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"QualityStage failed (non-fatal): {exc}")

        return ctx


# ---------------------------------------------------------------------------
# Helper: enrich ground_truth attack paths with AIVSS scores in-place
# ---------------------------------------------------------------------------

def _enrich_paths_with_aivss(ground_truth: dict, per_threat) -> None:
    paths = ground_truth.get("expected_attack_paths", [])
    threat_map = {t.technique_id: t for t in (per_threat or [])}
    for path in paths:
        pid = path.get("id", "")
        ts = threat_map.get(pid)
        if ts:
            path["aivss_score"] = round(ts.composite, 2)
            path["aivss_severity"] = ts.severity


# ---------------------------------------------------------------------------
# AIVSSStage — full three-flow scoring after critics + SM have run
# ---------------------------------------------------------------------------

class AIVSSStage(PipelineStage):
    """Full AIVSS v4 three-flow scoring (inbound / internal / outbound).

    Runs after ScrumMasterStage so moe_result and scrum_master_result are
    available for the internal flow's manipulation and drift signals.
    Enriches ctx["governance_signals"]["aivss"] in-place and re-saves
    governance_signals.json with the complete picture.
    """

    name = "aivss"
    required = False

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        try:
            import json as _json
            from pathlib import Path as _Path
            from chatbot.modules.harness_aivss import AIVSSFlowScorer, AIVSSAgentGate
            from chatbot.config.settings import get_settings
            _settings = get_settings()

            # Resolve governance_signals: prefer ctx (from QualityStage in full pipeline),
            # fall back to reading governance_signals.json from disk (expert-review SSE path
            # where QualityStage didn't run and ctx has no governance_signals).
            gov_signals = ctx.get("governance_signals") or {}
            if not gov_signals and ctx.get("report_dir"):
                sig_path = _Path(ctx["report_dir"]) / "governance_signals.json"
                if sig_path.exists():
                    try:
                        gov_signals = _json.loads(sig_path.read_text(encoding="utf-8"))
                        # Strip stale aivss block — we are about to recompute it
                        gov_signals.pop("aivss", None)
                    except Exception:
                        gov_signals = {}

            scorer = AIVSSFlowScorer(industry=_settings.governance.industry)
            aivss = scorer.compute(
                gov_signals,
                ctx.get("ground_truth", {}),
                ctx.get("moe_result"),
                ctx.get("scrum_master_result"),
            )

            # Merge AIVSS result into governance_signals (never replace the whole dict)
            gov_signals["aivss"] = aivss.to_dict()
            ctx["governance_signals"] = gov_signals

            # Enrich each attack path with its per-threat AIVSS score
            _enrich_paths_with_aivss(ctx.get("ground_truth", {}), aivss.per_threat)

            # Save the merged governance_signals.json (governance dims + aivss together)
            if _settings.governance.save_signals_per_run and ctx.get("report_dir"):
                sig_path = _Path(ctx["report_dir"]) / "governance_signals.json"
                sig_path.write_text(
                    _json.dumps(gov_signals, indent=2),
                    encoding="utf-8",
                )

            # Update gate and store score for OutboundAIVSSGate
            gate = AIVSSAgentGate(critic_settings=_settings.critics)
            ctx["_aivss_gate"] = gate
            ctx["_aivss_score"] = aivss

            if cb := kw.get("progress_callback"):
                cb("aivss", 100, f"AIVSS overall: {aivss.overall} {aivss.overall_severity}")

        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning(f"AIVSSStage failed (non-fatal): {exc}")

        return ctx


# ---------------------------------------------------------------------------
# OutboundAIVSSGate — optional stage after ScrumMasterStage
# ---------------------------------------------------------------------------

class OutboundAIVSSGate(PipelineStage):
    """
    Gate outbound report data on AIVSS outbound score.
    Emits a SIEM event after every run (regardless of severity).
    """

    name = "outbound_aivss"
    required = False

    def _logic(self, ctx: PipelineContext, **kw) -> PipelineContext:
        import logging as _log
        _logger = _log.getLogger(__name__)

        aivss: "AIVSSScore | None" = ctx.get("_aivss_score")  # type: ignore[name-defined]
        if aivss is None:
            return ctx

        outbound_score = aivss.outbound.composite
        if outbound_score >= 9.0:
            _logger.warning(
                f"AIVSS outbound {outbound_score:.1f} CRITICAL — "
                "report may contain high-risk disclosure signals; flagging run."
            )
            ctx["_outbound_blocked"] = True
        elif outbound_score >= 7.0:
            _logger.warning(
                f"AIVSS outbound {outbound_score:.1f} HIGH — "
                "elevated outbound risk signals detected."
            )

        # Always emit SIEM event
        try:
            from chatbot.modules.harness_siem import SiemEmitter, SiemEvent
            from chatbot.config.settings import get_settings
            gov = ctx.get("governance_signals", {})
            per_threat = aivss.per_threat
            top = max(per_threat, key=lambda t: t.composite) if per_threat else None
            event = SiemEvent(
                event_type="threat_assessment_complete",
                architecture=ctx.get("architecture_name", ctx.get("architecture_path", "")),
                aivss_inbound=aivss.inbound.composite,
                aivss_internal=aivss.internal.composite,
                aivss_outbound=aivss.outbound.composite,
                overall_severity=aivss.overall_severity,
                top_threat={
                    "technique_id": top.technique_id if top else "",
                    "technique_name": top.technique_name if top else "",
                    "aivss_score": round(top.composite, 2) if top else 0.0,
                    "severity": top.severity if top else "LOW",
                } if top else {},
                governance_dims={
                    "D1": gov.get("exploitation", {}).get("severity", "LOW"),
                    "D2": gov.get("manipulation_resistance", {}).get("severity", "LOW"),
                    "D3": gov.get("data_leakage", {}).get("severity", "LOW"),
                    "D4": gov.get("identity_integrity", {}).get("severity", "LOW"),
                    "D5": gov.get("data_sovereignty", {}).get("severity", "LOW"),
                },
                run_id=ctx.get("_run_id", ""),
                ts=ctx.get("_run_ts", ""),
            )
            settings = get_settings()
            emitter = SiemEmitter(webhook_url=settings.governance.siem_webhook_url)
            emitter.emit(event)
        except Exception as exc:
            _logger.warning(f"OutboundAIVSSGate SIEM emit failed (non-fatal): {exc}")

        return ctx
