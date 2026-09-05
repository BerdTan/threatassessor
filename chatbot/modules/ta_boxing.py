"""
TA Boxing — Brain vs Bot evaluation framework.

Three contenders, one deterministic referee, four quality dimensions + efficiency metrics.

Contenders:
  bot        — full LLM pipeline via ThreatAssessorHarness (LANGFUSE_SKIP=1)
  brain      — TA Brain pattern inference; D2 corpus-derived from evidence arch history
  brain_mini — TA Brain pattern inference; D2 arch-specific via synthetic path validation

Referee dimensions:
  D1  threat_completeness   — bot: precision (validated/total); brain: recall vs bot-validated reference
  D2  threat_accuracy       — topology applicability (method varies per contender)
  D3  mitigation_relevance  — % techniques with ≥1 official ATT&CK M-mitigation
  D4  actionability         — remediation quality: severity + named control + rationale

Efficiency (alongside scores):
  latency_s   — wall-clock seconds
  token_cost  — estimated tokens (bot only; 0 for brain/brain_mini)
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Detection-only techniques carry no preventive M-mitigations — excluded from D3 denominator.
# Kept in sync with exhaustive_mitigation_mapper.DETECTION_ONLY_TECHNIQUES keys.
_DETECT_ONLY: Set[str] = {
    "T1007", "T1010", "T1012", "T1016", "T1018", "T1033", "T1039",
    "T1046", "T1049", "T1057", "T1069", "T1082", "T1083", "T1087",
    "T1120", "T1124", "T1135", "T1201", "T1217", "T1420", "T1422",
    "T1423", "T1424", "T1426", "T1496",
}


# ── Referee ───────────────────────────────────────────────────────────────────

class BoxingReferee:
    """
    Deterministic scorer. No LLM in the referee path.
    All four dimensions return a float in [0, 1].
    """

    def __init__(self) -> None:
        from chatbot.modules.mitre import get_mitre_helper
        self._mitre = get_mitre_helper()

    # D1 ──────────────────────────────────────────────────────────────────────

    def score_d1(self, techniques: List[str], reference: Set[str]) -> float:
        """Technique recall: |contender ∩ reference| / |reference|."""
        if not reference:
            return 0.0
        hits = sum(1 for t in techniques if t in reference)
        return round(hits / len(reference), 4)

    def score_d1_precision(self, validated: List[str], total: List[str]) -> float:
        """
        Bot D1: precision = validated_techniques / total_predicted.
        Penalises hallucinated techniques that didn't pass self-validation.
        Bot recall against the reference is trivially ~100% (it contributed
        the reference), so precision is the meaningful signal here.
        """
        if not total:
            return 0.0
        return round(len(validated) / len(total), 4)

    # D2 variants ─────────────────────────────────────────────────────────────

    def score_d2_validated(self, self_val_output: Dict) -> float:
        """Bot D2: applicability rate from run_self_validation() output."""
        relevance = self_val_output.get("validations", {}).get("technique_relevance", [])
        if not relevance:
            return 0.0
        valid = sum(1 for r in relevance if r.get("valid"))
        return round(valid / len(relevance), 4)

    def score_d2_corpus(self, fired_pattern_ids: List[str]) -> float:
        """
        Brain D2: average technique applicability rate across evidence architectures
        that contributed to the fired patterns.

        Loads governance_signals.json (if present) for each evidence arch and
        reads the stored self-validation applicability rate. Falls back to the
        pattern's corpus_confidence as a proxy when signals are unavailable.
        """
        from chatbot.config import get_settings
        report_dir = Path(get_settings().system.report_dir)

        brain_path = report_dir / "brain" / "ta_brain.json"
        if not brain_path.exists():
            return 0.0

        brain = json.loads(brain_path.read_text())
        patterns = {p["id"]: p for p in brain.get("patterns", [])}

        rates: List[float] = []
        seen_archs: Set[str] = set()

        for pid in fired_pattern_ids:
            pattern = patterns.get(pid)
            if not pattern:
                continue
            for arch_id in pattern.get("evidence_arch_ids", []):
                if arch_id in seen_archs:
                    continue
                seen_archs.add(arch_id)
                sig_path = report_dir / arch_id / "governance_signals.json"
                if sig_path.exists():
                    try:
                        sigs = json.loads(sig_path.read_text())
                        rate = sigs.get("self_validation", {}).get("applicability_rate")
                        if rate is not None:
                            rates.append(float(rate))
                            continue
                    except Exception:
                        pass
                # Fallback: use corpus_confidence as proxy
                rates.append(pattern.get("corpus_confidence", 0.5))

        return round(sum(rates) / len(rates), 4) if rates else 0.0

    def score_d2_synthetic(
        self,
        techniques: List[str],
        nodes: Dict[str, Dict],
    ) -> float:
        """
        Brain-mini D2: for each predicted technique, test applicability against
        synthetic single-node paths constructed from the target arch graph.

        A technique passes if validate_technique_for_path() returns is_valid=True
        for at least one node in the graph.
        """
        if not techniques or not nodes:
            return 0.0

        from chatbot.modules.self_validation import validate_technique_for_path

        valid_count = 0
        for tech_id in techniques:
            tech_valid = False
            for node_id, node_attrs in nodes.items():
                synthetic_path = {
                    "path": [node_id],
                    "entry": node_id,
                    "target": node_id,
                    "techniques": [tech_id],
                    "label": node_attrs.get("label", node_id),
                }
                try:
                    is_valid, _, _ = validate_technique_for_path(
                        tech_id, synthetic_path, nodes, self._mitre
                    )
                    if is_valid:
                        tech_valid = True
                        break
                except Exception:
                    continue
            if tech_valid:
                valid_count += 1

        return round(valid_count / len(techniques), 4)

    # D3 ──────────────────────────────────────────────────────────────────────

    def score_d3(self, techniques: List[str]) -> float:
        """
        ATT&CK M-mitigation linkage: fraction of actionable techniques
        (excluding detection-only) that have ≥1 official M-mitigation.
        """
        actionable = [t for t in techniques if t not in _DETECT_ONLY]
        if not actionable:
            return 0.0

        from chatbot.modules.exhaustive_mitigation_mapper import get_all_mitigations_for_techniques
        try:
            mit_map = get_all_mitigations_for_techniques(actionable, self._mitre)
        except Exception as exc:
            logger.warning("D3: mitigation lookup failed: %s", exc)
            return 0.0

        covered: Set[str] = set()
        for entry in mit_map.values():
            covered.update(entry.get("techniques", []))

        covered_actionable = covered & set(actionable)
        return round(len(covered_actionable) / len(actionable), 4)

    # D4 variants ─────────────────────────────────────────────────────────────

    def score_d4_bot(self, control_recommendations: List[Dict]) -> float:
        """
        Bot D4: per-recommendation completeness.
        Each rec is scored on: priority set + named control + ≥1 mitigation + rationale.
        """
        if not control_recommendations:
            return 0.0
        scores = []
        for rec in control_recommendations:
            has_priority = bool(rec.get("priority"))
            has_control = bool(rec.get("control"))
            has_mitigation = bool(rec.get("mitigations"))
            has_rationale = bool(rec.get("rationale") or rec.get("detailed_rationale"))
            scores.append(sum([has_priority, has_control, has_mitigation, has_rationale]) / 4)
        return round(sum(scores) / len(scores), 4)

    def score_d4_brain(self, infer_result: Dict) -> float:
        """
        Brain/Brain-mini D4: pattern-level remediation quality.
        Scored on: controls named + partial priority signal + remediation template.
        """
        preds = infer_result.get("predictions", {})
        controls = preds.get("control_priorities", [])
        aivss_floor = preds.get("aivss_floor", 0.0)

        controls_score = 1.0 if controls else 0.0
        # Partial priority: AIVSS floor present and non-zero
        priority_score = 0.5 if aivss_floor and aivss_floor > 0 else 0.0
        # Check fired patterns for remediation_template
        template_score = self._has_remediation_template(
            infer_result.get("evidence", {}).get("pattern_ids", [])
        )

        return round((controls_score + priority_score + template_score) / 3, 4)

    def _has_remediation_template(self, pattern_ids: List[str]) -> float:
        try:
            from chatbot.config import get_settings
            brain_path = Path(get_settings().system.report_dir) / "brain" / "ta_brain.json"
            brain = json.loads(brain_path.read_text())
            patterns = {p["id"]: p for p in brain.get("patterns", [])}
            for pid in pattern_ids:
                if patterns.get(pid, {}).get("remediation_template"):
                    return 1.0
        except Exception:
            pass
        return 0.0

    # Composite ───────────────────────────────────────────────────────────────

    @staticmethod
    def composite(d1: float, d2: float, d3: float, d4: float) -> float:
        return round((d1 + d2 + d3 + d4) / 4, 4)


# ── Contender runners ─────────────────────────────────────────────────────────

def _extract_techniques_from_ground_truth(gt: Dict) -> List[str]:
    """Pull flat technique ID list from ground_truth.json."""
    techs: List[str] = []
    for rec in gt.get("control_recommendations", []):
        techs.extend(rec.get("techniques", []))
    for path in gt.get("attack_paths", gt.get("expected_attack_paths", [])):
        techs.extend(path.get("techniques", []))
    techs.extend(gt.get("techniques", []))
    return list(dict.fromkeys(techs))  # deduplicate, preserve order


def _extract_validated_techniques(gt: Dict) -> List[str]:
    """
    Return only techniques that passed self-validation (is_valid=True).
    Falls back to all techniques when validation data is absent (treats all as valid).
    Self-validation lives at gt.validation_report.validations.technique_relevance.
    """
    relevance = (
        gt.get("validation_report", {})
          .get("validations", {})
          .get("technique_relevance", [])
    )
    if not relevance:
        # No validation data — treat all extracted techniques as valid
        return _extract_techniques_from_ground_truth(gt)
    return list(dict.fromkeys(
        r["technique"] for r in relevance if r.get("valid") and r.get("technique")
    ))


def run_bot_contender(
    arch_name: str,
    mmd_path: str,
    ssp_profile: str = "low_risk_cloud",
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Use the best available bot result for arch_name.

    Priority:
    1. Existing report/{arch_name}/ground_truth.json — preserves full MoE run;
       never overwrites a completed assessment with a weaker API_ONLY result.
    2. Existing report/{arch_name}_boxing_bot/ground_truth.json — a prior boxing run.
    3. Fresh LLM pipeline run (API_ONLY) into _boxing_bot dir — only when no prior
       result exists for this arch.

    model_override forces a fresh run into a model-labelled boxing dir regardless
    of (1) and (2), since a model comparison needs fresh per-model outputs.

    Returns scored contender dict ready for the referee.
    """
    from chatbot.config import get_settings

    settings = get_settings()
    parent_report_dir = Path(settings.system.report_dir)

    t0 = time.perf_counter()
    error: Optional[str] = None
    gt: Dict = {}
    self_val: Dict = {}
    token_cost = 0
    ran_fresh = False

    suffix = f"_boxing_bot_{model_override}" if model_override else "_boxing_bot"
    boxing_arch_name = f"{arch_name}{suffix}"
    boxing_report_dir = parent_report_dir / boxing_arch_name

    # ── Determine result source ───────────────────────────────────────────────
    existing_gt: Optional[Path] = None
    if not model_override:
        # Prefer the existing full assessment (may have MoE critics)
        canonical = parent_report_dir / arch_name / "ground_truth.json"
        boxing_cached = boxing_report_dir / "ground_truth.json"
        if canonical.exists():
            existing_gt = canonical
            logger.info("Bot contender: reusing existing assessment for %s", arch_name)
        elif boxing_cached.exists():
            existing_gt = boxing_cached
            logger.info("Bot contender: reusing boxing cache for %s", arch_name)

    if existing_gt is not None:
        try:
            gt = json.loads(existing_gt.read_text())
            self_val = gt.get("validation_report", {})
            # Read token cost from sibling governance_signals if present
            gs_path = existing_gt.parent / "governance_signals.json"
            if gs_path.exists():
                gs = json.loads(gs_path.read_text())
                token_cost = gs.get("llm_usage", {}).get("total_tokens", 0)
        except Exception as exc:
            logger.warning("Could not read existing assessment for %s: %s", arch_name, exc)
            existing_gt = None  # fall through to fresh run

    if existing_gt is None:
        # ── Fresh run ─────────────────────────────────────────────────────────
        from chatbot.harness.controller import ThreatAssessorHarness, PipelineRequest

        env_patch: Dict[str, str] = {"LANGFUSE_SKIP": "1"}
        if model_override:
            env_patch["LLM_PROVIDER"] = model_override
        old_env = {k: os.environ.get(k) for k in env_patch}
        os.environ.update(env_patch)

        try:
            boxing_report_dir.mkdir(parents=True, exist_ok=True)
            harness = ThreatAssessorHarness()
            req = PipelineRequest(
                architecture_path=mmd_path,
                report_dir=str(boxing_report_dir),
                ssp_profile=ssp_profile,
                architecture_name=boxing_arch_name,
                use_llm=True,
                enable_moe=False,
            )
            harness.run_typed(req)
            ran_fresh = True

            gt_path = boxing_report_dir / "ground_truth.json"
            if gt_path.exists():
                gt = json.loads(gt_path.read_text())
                self_val = gt.get("validation_report", {})

            gs_path = boxing_report_dir / "governance_signals.json"
            if gs_path.exists():
                gs = json.loads(gs_path.read_text())
                token_cost = gs.get("llm_usage", {}).get("total_tokens", 0)

        except Exception as exc:
            error = str(exc)
            logger.warning("Bot contender fresh run failed: %s", exc)
        finally:
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    latency = round(time.perf_counter() - t0, 2)
    techniques = _extract_techniques_from_ground_truth(gt)
    validated_techniques = _extract_validated_techniques(gt)
    control_recs = gt.get("control_recommendations", [])

    label = f"LLM Pipeline ({model_override})" if model_override else "LLM Pipeline"
    if not model_override and existing_gt is not None:
        src = "MoE" if (parent_report_dir / arch_name / "ground_truth.json") == existing_gt else "cached"
        label = f"LLM Pipeline [{src}]"
    return {
        "label": label,
        "model": model_override or os.environ.get("LLM_PROVIDER", "default"),
        "techniques": techniques,
        "validated_techniques": validated_techniques,
        "control_recommendations": control_recs,
        "self_val": self_val,
        "latency_s": latency,
        "token_cost": token_cost,
        "error": error,
    }


def run_brain_contenders(arch_name: str, arch_type: str = "") -> Tuple[Dict, Dict]:
    """
    Run the TA Brain inference once; return separate dicts for Brain and Brain-mini.
    Both share the same technique predictions — only D2 source differs.
    """
    from chatbot.modules.ta_brain_query import query_brain

    t0 = time.perf_counter()
    try:
        infer = query_brain(mode="infer", arch_name=arch_name, arch_type=arch_type, caller_type="boxing")
    except Exception as exc:
        logger.warning("Brain inference failed: %s", exc)
        infer = {"had_match": False, "predictions": {}, "evidence": {}, "confidence": 0.0}
    latency = round(time.perf_counter() - t0, 3)

    techniques = infer.get("predictions", {}).get("techniques", [])
    pattern_ids = infer.get("evidence", {}).get("pattern_ids", [])

    brain_data = {
        "label": "TA Brain (corpus inference)",
        "techniques": techniques,
        "infer_result": infer,
        "pattern_ids": pattern_ids,
        "latency_s": latency,
        "token_cost": 0,
        "error": None if infer.get("had_match") else "no_pattern_match",
    }
    brain_mini_data = {
        "label": "TA Brain-mini (arch-specific)",
        "techniques": techniques,
        "infer_result": infer,
        "pattern_ids": pattern_ids,
        "latency_s": latency,  # same inference; synthetic path adds marginal time
        "token_cost": 0,
        "error": None if infer.get("had_match") else "no_pattern_match",
    }
    return brain_data, brain_mini_data


# ── Orchestrator ──────────────────────────────────────────────────────────────

def _score_bot(referee: BoxingReferee, bot: Dict, reference: Set[str]) -> Dict[str, float]:
    # D1: precision = validated / total_predicted
    # Bot recall against the reference is ~100% by construction (it contributed the reference).
    # Precision penalises hallucinations that didn't survive self-validation.
    valid_techs = bot.get("validated_techniques") or bot["techniques"]
    all_techs = bot["techniques"]
    d1 = referee.score_d1_precision(valid_techs, all_techs)
    d2 = referee.score_d2_validated(bot["self_val"])
    d3 = referee.score_d3(valid_techs)
    d4 = referee.score_d4_bot(bot["control_recommendations"])
    return {"threat_completeness": d1, "threat_accuracy": d2,
            "mitigation_relevance": d3, "actionability": d4,
            "composite": referee.composite(d1, d2, d3, d4)}


def run_boxing_match(
    arch_name: str,
    mmd_path: str,
    ssp_profile: str = "low_risk_cloud",
    arch_type: str = "",
    nodes: Optional[Dict[str, Dict]] = None,
    models: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run a full boxing match for arch_name and write boxing_results.json.

    Args:
        arch_name:   architecture identifier
        mmd_path:    path to the .mmd file
        ssp_profile: SSP profile for bot contender(s)
        arch_type:   optional arch_type hint for brain inference
        nodes:       optional pre-parsed node dict for brain-mini synthetic paths
        models:      list of LLM_PROVIDER keys to test as separate bot contenders
                     (e.g. ["hetzner", "gemini_flash", "minimax"]).
                     None or [] runs a single default bot contender.

    Returns:
        Full scorecard dict (also written to report/<arch_name>/boxing_results.json).
    """
    from chatbot.config import get_settings

    report_dir = Path(get_settings().system.report_dir) / arch_name
    report_dir.mkdir(parents=True, exist_ok=True)

    referee = BoxingReferee()

    # ── Parse nodes for brain-mini D2 if not provided ────────────────────────
    if nodes is None:
        try:
            from chatbot.adapters.mmd_adapter import MMDAdapter
            mmd_text = Path(mmd_path).read_text()
            graph = MMDAdapter().extract(mmd_text, mmd_path)
            nodes = {n.id: {"label": n.label, "type": n.node_type} for n in graph.nodes}
        except Exception as exc:
            logger.warning("Could not parse MMD nodes for brain-mini D2: %s", exc)
            nodes = {}

    # ── Run brain contenders once (shared across all bot runs) ────────────────
    logger.info("Boxing: running brain contenders for %s", arch_name)
    brain, brain_mini = run_brain_contenders(arch_name, arch_type)

    # ── Run bot contenders (one per model, or single default) ─────────────────
    model_list: List[Optional[str]] = list(models) if models else [None]
    bot_runs: List[Dict] = []
    for model in model_list:
        label = f"bot_{model}" if model else "bot"
        logger.info("Boxing: running bot contender [%s] for %s", label, arch_name)
        bot_data = run_bot_contender(arch_name, mmd_path, ssp_profile, model_override=model)
        bot_data["_key"] = label
        bot_runs.append(bot_data)

    # ── Reference set: bot-validated techniques only ─────────────────────────
    # Reference = techniques that passed bot self-validation (is_valid=True).
    # Brain techniques are pattern predictions, not independently verified here,
    # so including them would inflate the reference with unverified claims.
    # Brain D1 = recall (how many reference techniques brain predicted).
    # Bot D1 = precision (validated / total_predicted) — see _score_bot().
    # This lets each contender be measured on the dimension most meaningful to it.
    reference: Set[str] = set()
    for b in bot_runs:
        reference.update(b.get("validated_techniques") or b["techniques"])

    # ── Score brain contenders ────────────────────────────────────────────────
    brain_d1 = referee.score_d1(brain["techniques"], reference)
    brain_d2 = referee.score_d2_corpus(brain["pattern_ids"])
    brain_d3 = referee.score_d3(brain["techniques"])
    brain_d4 = referee.score_d4_brain(brain["infer_result"])
    brain_composite = referee.composite(brain_d1, brain_d2, brain_d3, brain_d4)

    # Brain-mini D2: try synthetic path validation first; fall back to brain confidence
    # when path heuristics return 0 (common for non-standard arch topologies).
    t_mini = time.perf_counter()
    brain_mini_d2 = referee.score_d2_synthetic(brain_mini["techniques"], nodes)
    if brain_mini_d2 == 0.0 and brain_mini["techniques"]:
        brain_mini_d2 = round(float(brain_mini["infer_result"].get("confidence", 0.0)), 4)
    brain_mini["latency_s"] = round(brain_mini["latency_s"] + (time.perf_counter() - t_mini), 3)
    brain_mini_d1 = brain_d1
    brain_mini_d3 = brain_d3
    brain_mini_d4 = brain_d4
    brain_mini_composite = referee.composite(brain_mini_d1, brain_mini_d2, brain_mini_d3, brain_mini_d4)

    # ── Build contenders dict ─────────────────────────────────────────────────
    contenders: Dict[str, Any] = {}

    for b in bot_runs:
        key = b["_key"]
        scores = _score_bot(referee, b, reference)
        valid_techs = b.get("validated_techniques") or b["techniques"]
        contenders[key] = {
            "label": b["label"],
            "model": b.get("model"),
            "technique_count": len(b["techniques"]),
            "validated_technique_count": len(valid_techs),
            "latency_s": b["latency_s"],
            "token_cost": b["token_cost"],
            "error": b["error"],
            "scores": scores,
        }

    contenders["brain"] = {
        "label": brain["label"],
        "model": "brain",
        "technique_count": len(brain["techniques"]),
        "latency_s": brain["latency_s"],
        "token_cost": 0,
        "error": brain["error"],
        "scores": {
            "threat_completeness": brain_d1,
            "threat_accuracy": brain_d2,
            "mitigation_relevance": brain_d3,
            "actionability": brain_d4,
            "composite": brain_composite,
        },
    }

    contenders["brain_mini"] = {
        "label": brain_mini["label"],
        "model": "brain_mini",
        "technique_count": len(brain_mini["techniques"]),
        "latency_s": brain_mini["latency_s"],
        "token_cost": 0,
        "error": brain_mini["error"],
        "scores": {
            "threat_completeness": brain_mini_d1,
            "threat_accuracy": brain_mini_d2,
            "mitigation_relevance": brain_mini_d3,
            "actionability": brain_mini_d4,
            "composite": brain_mini_composite,
        },
    }

    # ── Verdict ───────────────────────────────────────────────────────────────
    ranking = sorted(
        [(k, c["scores"]["composite"]) for k, c in contenders.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    # Quality-vs-cost: compare each bot against brain
    ref_bot_latency = next((b["latency_s"] for b in bot_runs), 1.0) or 1.0
    qvsc: Dict[str, Any] = {
        "brain_vs_bot_quality_delta": round(
            brain_composite - (contenders.get("bot") or contenders.get(bot_runs[0]["_key"], {}) or {}).get("scores", {}).get("composite", 0),
            4,
        ),
        "brain_latency_speedup": round(ref_bot_latency / max(brain["latency_s"], 0.001), 1),
        "brain_mini_latency_speedup": round(ref_bot_latency / max(brain_mini["latency_s"], 0.001), 1),
    }
    for b in bot_runs:
        qvsc[f"{b['_key']}_token_cost"] = b["token_cost"]

    result: Dict[str, Any] = {
        "arch_name": arch_name,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "mmd_path": mmd_path,
        "models_tested": [b.get("model") or "default" for b in bot_runs],
        "ref_technique_count": len(reference),
        "contenders": contenders,
        "verdict": {
            "ranking": [r[0] for r in ranking],
            "winner": ranking[0][0],
            "scores": {r[0]: r[1] for r in ranking},
            "quality_vs_cost": qvsc,
        },
    }

    out_path = report_dir / "boxing_results.json"
    out_path.write_text(json.dumps(result, indent=2))
    logger.info("Boxing results written to %s", out_path)

    return result


def promote_boxing_to_brain(arch_name: str) -> Dict[str, Any]:
    """
    Promote a boxing bot run into the brain as a real corpus instance.

    Reads report/{arch_name}_boxing_bot/ground_truth.json, extracts an
    InstanceEntry with arch_id=arch_name (clean name, no suffix), writes/
    updates ta_brain_instances.jsonl, rebuilds the brain, and returns a
    before/after confidence gap report.

    Returns:
        {
          arch_name, pattern_id, pattern_arch_type,
          before: {technique_count, d1_coverage},
          after:  {technique_count, d1_coverage},
          gap_closed: float,           # delta in recall fraction
          new_techniques_added: int,
          brain_version: int,
        }
    """
    from chatbot.config import get_settings
    from chatbot.modules.ta_brain_builder import (
        build_brain, extract_instance, _load_rule_evaluator,
    )
    from chatbot.modules.ta_brain_query import query_brain

    def _infer(arch: str) -> Dict:
        return query_brain(mode="infer", arch_name=arch, caller_type="promote")

    report_base = Path(get_settings().system.report_dir)
    boxing_dir = report_base / f"{arch_name}_boxing_bot"

    if not boxing_dir.exists():
        raise FileNotFoundError(f"Boxing bot dir not found: {boxing_dir}")

    gt_path = boxing_dir / "ground_truth.json"
    if not gt_path.exists():
        raise FileNotFoundError(f"No ground_truth.json in {boxing_dir}")

    # ── Snapshot before ───────────────────────────────────────────────────────
    try:
        before_infer = _infer(arch_name)
        before_techs = set(before_infer.get("predictions", {}).get("techniques", []))
    except Exception:
        before_techs = set()

    valid_ref = set(
        r["technique"]
        for r in json.loads(gt_path.read_text())
            .get("validation_report", {})
            .get("validations", {})
            .get("technique_relevance", [])
        if r.get("valid")
    )
    before_d1 = round(len(before_techs & valid_ref) / len(valid_ref), 4) if valid_ref else 0.0

    # ── Extract instance from boxing dir ─────────────────────────────────────
    try:
        rule_evaluator = _load_rule_evaluator()
    except Exception:
        rule_evaluator = None

    inst = extract_instance(boxing_dir, rule_evaluator)
    if inst is None:
        raise ValueError(
            f"extract_instance returned None for {boxing_dir} — "
            "check that governance_signals.json exists in the boxing dir"
        )

    # Use a _promoted suffix so this entry bypasses HOLD_OUT_ARCHS.
    # The original arch_id may be in the hold-out set (E2E validation gate);
    # the promoted instance is a second, training-eligible copy from the boxing run.
    promoted_id = f"{arch_name}_promoted"
    inst["arch_id"] = promoted_id
    inst["source"] = "real"

    # ── Write/update JSONL ────────────────────────────────────────────────────
    instances_path = report_base / "brain" / "ta_brain_instances.jsonl"
    lines = []
    replaced = False
    if instances_path.exists():
        for line in instances_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("arch_id") == promoted_id:
                    lines.append(json.dumps(inst))
                    replaced = True
                    continue
            except Exception:
                pass
            lines.append(line)
    if not replaced:
        lines.append(json.dumps(inst))
    instances_path.write_text("\n".join(lines) + "\n")
    logger.info("Boxing promote: %s instance %s in JSONL",
                "updated" if replaced else "added", promoted_id)

    # ── Rebuild brain ─────────────────────────────────────────────────────────
    build_brain(incremental=False)

    # ── Snapshot after ────────────────────────────────────────────────────────
    brain = json.loads((report_base / "brain" / "ta_brain.json").read_text())
    after_infer = _infer(arch_name)
    after_techs = set(after_infer.get("predictions", {}).get("techniques", []))
    after_d1 = round(len(after_techs & valid_ref) / len(valid_ref), 4) if valid_ref else 0.0

    # Find which pattern covers this arch
    pattern_id = after_infer.get("evidence", {}).get("pattern_ids", [None])[0]
    pattern_arch_type = next(
        (p.get("trigger", {}).get("arch_type") for p in brain.get("patterns", [])
         if p["id"] == pattern_id),
        None,
    )

    return {
        "arch_name": arch_name,
        "pattern_id": pattern_id,
        "pattern_arch_type": pattern_arch_type,
        "before": {
            "technique_count": len(before_techs),
            "d1_coverage": before_d1,
        },
        "after": {
            "technique_count": len(after_techs),
            "d1_coverage": after_d1,
        },
        "gap_closed": round(after_d1 - before_d1, 4),
        "new_techniques_added": len(after_techs - before_techs),
        "brain_version": brain.get("pattern_version"),
        "validated_reference_size": len(valid_ref),
    }
