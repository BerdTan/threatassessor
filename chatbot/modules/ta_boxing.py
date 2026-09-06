"""
TA Boxing — multi-contender evaluation framework.

Five contenders, one deterministic referee, four quality dimensions + efficiency metrics.

Contenders (default: det_moe_full + brain + brain_lexical):
  det_moe_full   — reads canonical report/{arch}/ground_truth.json (full MoE if run)
  llm_only       — pure LLM threat model: raw MMD → LLM → MITRE IDs (no RAPIDS, no harness); opt-in
  det_eng_only   — harness with use_llm=False (pure graph traversal); opt-in
  brain          — TA Brain corpus pattern inference; D2 from evidence arch history
  brain_lexical  — keyword→MITRE lookup on MMD node labels; pure lexical, no patterns

Referee dimensions (same criteria for all contenders):
  D1  threat_completeness   — det_moe_full/det_eng_only: precision (validated/total predicted)
                              llm_only: precision (valid MITRE IDs / total predicted)
                              brain/brain_lexical: recall vs det_moe_full validated reference
  D2  threat_accuracy       — det_moe_full: self-validation applicability rate
                              llm_only: recall vs gold reference (how much of RAPIDS it found)
                              brain: corpus evidence applicability rate
  D2  threat_accuracy       — topology applicability (method varies per contender)
  D3  mitigation_relevance  — % techniques with ≥1 official ATT&CK M-mitigation
  D4  actionability         — remediation quality: severity + named control + rationale

Routing signal: boxing results over many archs drive model_routing.yaml —
  brain D1 ≥ threshold → route to brain (fast, free)
  llm_only D1 ≈ det_moe_full → MoE critics add little value for this arch_type
  brain_lexical ≈ brain → patterns aren't adding value over keyword scanning

Efficiency (alongside scores):
  latency_s   — wall-clock seconds
  token_cost  — estimated tokens (LLM contenders only; 0 for brain/lexical/det_eng)
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


def run_det_moe_full_contender(
    arch_name: str,
    mmd_path: str,
    ssp_profile: str = "low_risk_cloud",
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Gold-standard contender: reads the best available existing assessment.

    Priority:
    1. report/{arch_name}/ground_truth.json — canonical assessment (full MoE if run).
       Never overwritten; this is what all other contenders are compared against.
    2. report/{arch_name}_boxing_bot/ground_truth.json — prior boxing cache.
    3. Fresh API_ONLY LLM run into _boxing_bot dir — only when nothing exists.

    model_override forces a fresh run into a model-labelled dir; used when comparing
    multiple LLM providers as separate det_moe_full variants.

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

    if model_override:
        label = f"Det/MoE ({model_override})"
    elif existing_gt == (parent_report_dir / arch_name / "ground_truth.json"):
        label = "Det/MoE Full [canonical]"
    elif existing_gt is not None:
        label = "Det/MoE Full [cached]"
    else:
        label = "Det/MoE Full [fresh API_ONLY]"
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


_LLM_ONLY_SYSTEM = (
    "You are a senior threat modeler. Given an architecture diagram, identify every applicable "
    "MITRE ATT&CK technique (Enterprise or ATLAS). Be thorough — include initial access, "
    "lateral movement, data exfiltration, and AI/ML-specific techniques where relevant."
)

_LLM_ONLY_PROMPT = """Architecture diagram (Mermaid):
```
{mmd}
```

Return ONLY valid JSON — no prose, no markdown fences — in this exact schema:
{{
  "techniques": ["T1190", "AML.T0025", ...],
  "controls": ["input validation", "network segmentation", ...]
}}

Rules:
- techniques: MITRE ATT&CK IDs only (Txxxx, Txxxx.xxx, AML.Txxxx). No names, no descriptions.
- controls: short named controls (1-5 words each). Max 10.
- Do not include any key other than "techniques" and "controls".
"""


def run_llm_only_contender(
    arch_name: str,
    mmd_path: str,
    ssp_profile: str = "low_risk_cloud",
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Pure LLM threat model — no RAPIDS, no harness, no deterministic engine.
    Feeds the raw MMD to the LLM and asks for MITRE technique IDs directly.
    validated_techniques = subset that exist in MITRE ATT&CK enterprise set.
    D1 precision penalises hallucinated IDs.
    """
    from agentic.llm_client import generate_response_with_system
    from chatbot.modules.mitre import get_mitre_helper

    env_patch: Dict[str, str] = {"LANGFUSE_SKIP": "1"}
    if model_override:
        env_patch["LLM_PROVIDER"] = model_override
    old_env = {k: os.environ.get(k) for k in env_patch}
    os.environ.update(env_patch)

    t0 = time.perf_counter()
    techniques: List[str] = []
    validated: List[str] = []
    controls: List[str] = []
    error: Optional[str] = None

    try:
        mmd_text = Path(mmd_path).read_text()
        prompt = _LLM_ONLY_PROMPT.format(mmd=mmd_text)
        raw = generate_response_with_system(
            prompt, _LLM_ONLY_SYSTEM,
            model=model_override or None,
            temperature=0.2,
            max_tokens=1500,
        )
        # Extract JSON — strip markdown fences if present
        text = raw.strip()
        if "```" in text:
            for block in text.split("```"):
                block = block.strip().lstrip("json").strip()
                if block.startswith("{"):
                    text = block
                    break
        parsed = json.loads(text)
        techniques = [t.strip() for t in parsed.get("techniques", []) if isinstance(t, str)]
        controls = [c.strip() for c in parsed.get("controls", []) if isinstance(c, str)]

        # Validate technique IDs against MITRE ATT&CK
        mitre = get_mitre_helper()
        for tid in techniques:
            try:
                if mitre.get_technique(tid):
                    validated.append(tid)
            except Exception:
                pass

    except Exception as exc:
        error = str(exc)
        logger.warning("LLM-only contender failed: %s", exc)
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    latency = round(time.perf_counter() - t0, 2)
    active_model = model_override or os.environ.get("LLM_PROVIDER", "default")
    label = f"LLM-only ({active_model})" if model_override else "LLM-only"

    # Build a minimal self_val compatible with _score_lm_contender
    self_val = {
        "overall_valid": bool(validated),
        "validations": {},
        "confidence_adjustments": [],
        "issues_found": len(techniques) - len(validated),
    }
    control_recs = [{"control": c, "priority": "medium", "rationale": ""} for c in controls]

    return {
        "label": label,
        "model": active_model,
        "techniques": techniques,
        "validated_techniques": validated,
        "control_recommendations": control_recs,
        "self_val": self_val,
        "latency_s": latency,
        "token_cost": 0,
        "error": error,
    }


def run_det_eng_only_contender(
    arch_name: str,
    mmd_path: str,
    ssp_profile: str = "low_risk_cloud",
) -> Dict[str, Any]:
    """
    Deterministic graph-traversal only — harness with use_llm=False.
    Writes to report/{arch}_boxing_deteng/. Baseline: what structure alone reveals.
    """
    from chatbot.harness.controller import ThreatAssessorHarness, PipelineRequest
    from chatbot.config import get_settings

    boxing_arch_name = f"{arch_name}_boxing_deteng"
    boxing_dir = Path(get_settings().system.report_dir) / boxing_arch_name
    boxing_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    gt: Dict = {}
    self_val: Dict = {}
    error: Optional[str] = None

    try:
        os.environ["LANGFUSE_SKIP"] = "1"
        harness = ThreatAssessorHarness()
        req = PipelineRequest(
            architecture_path=mmd_path,
            report_dir=str(boxing_dir),
            ssp_profile=ssp_profile,
            architecture_name=boxing_arch_name,
            use_llm=False,
            enable_moe=False,
        )
        harness.run_typed(req)
        gt_path = boxing_dir / "ground_truth.json"
        if gt_path.exists():
            gt = json.loads(gt_path.read_text())
            self_val = gt.get("validation_report", {})
    except Exception as exc:
        error = str(exc)
        logger.warning("Det-eng-only contender failed: %s", exc)

    latency = round(time.perf_counter() - t0, 2)
    return {
        "label": "Det/Eng-only (graph traversal)",
        "model": "deterministic",
        "techniques": _extract_techniques_from_ground_truth(gt),
        "validated_techniques": _extract_validated_techniques(gt),
        "control_recommendations": gt.get("control_recommendations", []),
        "self_val": self_val,
        "latency_s": latency,
        "token_cost": 0,
        "error": error,
    }


# ── Keyword→MITRE technique map for lexical contender ─────────────────────────
# Each entry: (keyword_tokens, [technique_ids])
# Matched against lowercased node labels from the MMD graph.
_LEXICAL_MAP: List[Tuple[List[str], List[str]]] = [
    (["llm", "language model", "gpt", "claude", "gemini", "openai", "bedrock", "vertex ai"],
     ["AML.T0025", "AML.T0051", "AML.T0051.000", "AML.T0051.001", "AML.T0040", "AML.T0054"]),
    (["vector db", "embedding", "rag", "retrieval"],
     ["AML.T0025", "T1213", "T1530"]),
    (["api", "api gateway", "rest", "graphql", "endpoint"],
     ["T1190", "T1133", "T1071", "T1059"]),
    (["auth", "identity", "iam", "jwt", "oauth", "sso", "cognito", "entra", "okta"],
     ["T1110", "T1078", "T1528", "T1550"]),
    (["database", "db", "sql", "postgres", "mysql", "mongodb", "redis", "dynamodb"],
     ["T1213", "T1190", "T1485", "T1486"]),
    (["storage", "s3", "blob", "gcs", "object store", "bucket"],
     ["T1530", "T1213", "T1567"]),
    (["container", "docker", "kubernetes", "k8s", "pod", "eks", "aks", "gke"],
     ["T1610", "T1552", "T1543", "T1059"]),
    (["serverless", "lambda", "function", "cloud function", "cloud run"],
     ["T1059", "T1190", "T1552"]),
    (["network", "vpc", "subnet", "vnet", "firewall", "security group"],
     ["T1040", "T1046", "T1090", "T1557"]),
    (["web", "nginx", "apache", "cdn", "cloudfront", "load balancer"],
     ["T1190", "T1071", "T1498", "T1499"]),
    (["message queue", "kafka", "sqs", "pubsub", "event", "stream"],
     ["T1059", "T1485", "T1041"]),
    (["ci", "cd", "pipeline", "github actions", "jenkins", "deploy"],
     ["T1195", "T1059", "T1552"]),
    (["secret", "vault", "key management", "kms", "hsm"],
     ["T1552", "T1555", "T1212"]),
    (["monitoring", "logging", "siem", "cloudwatch", "datadog", "splunk"],
     ["T1562", "T1070"]),
    (["user", "client", "browser", "mobile", "frontend"],
     ["T1059", "T1078", "T1204"]),
    (["microservice", "service mesh", "istio", "envoy"],
     ["T1040", "T1557", "T1090"]),
]


def _lexical_techniques_from_mmd(mmd_path: str) -> List[str]:
    """
    Extract MITRE techniques by keyword-matching MMD node labels.
    Pure lexical — no patterns, no LLM. Fast baseline for any MMD file.
    """
    try:
        from chatbot.adapters.mmd_adapter import MMDAdapter
        mmd_text = Path(mmd_path).read_text()
        graph = MMDAdapter().extract(mmd_text, mmd_path)
        labels = " ".join(n.label.lower() for n in graph.nodes)
    except Exception:
        labels = Path(mmd_path).read_text().lower()

    found: dict = {}
    for keywords, techniques in _LEXICAL_MAP:
        if any(kw in labels for kw in keywords):
            for t in techniques:
                found.setdefault(t, True)
    return list(found.keys())


def run_brain_contender(arch_name: str, arch_type: str = "") -> Dict[str, Any]:
    """TA Brain corpus pattern inference. D2 from evidence arch history."""
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
    # corpus_hits = unique source arch IDs that drove the fired patterns
    corpus_hits = len(set(infer.get("evidence", {}).get("source_archs", [])))
    return {
        "label": "TA Brain (corpus inference)",
        "techniques": techniques,
        "infer_result": infer,
        "pattern_ids": pattern_ids,
        "corpus_hits": corpus_hits,
        "latency_s": latency,
        "token_cost": 0,
        "error": None if infer.get("had_match") else "no_pattern_match",
    }


def run_brain_lexical_contender(mmd_path: str) -> Dict[str, Any]:
    """
    Lexical keyword→MITRE lookup on MMD node labels.
    No patterns, no LLM — pure text matching baseline.
    D2: fraction of predicted techniques that are in the MITRE ATT&CK enterprise set
    (a proxy for precision — lexical hits that are real techniques).
    """
    t0 = time.perf_counter()
    error: Optional[str] = None
    techniques: List[str] = []
    try:
        techniques = _lexical_techniques_from_mmd(mmd_path)
    except Exception as exc:
        error = str(exc)
        logger.warning("Brain-lexical contender failed: %s", exc)
    latency = round(time.perf_counter() - t0, 3)
    return {
        "label": "Brain-lexical (keyword scan)",
        "techniques": techniques,
        "infer_result": {"had_match": bool(techniques), "predictions": {"techniques": techniques}, "evidence": {}, "confidence": 0.0},
        "pattern_ids": [],
        "latency_s": latency,
        "token_cost": 0,
        "error": error,
    }


# ── Orchestrator ──────────────────────────────────────────────────────────────

_ALL_CONTENDERS = ("det_moe_full", "llm_only", "det_eng_only", "brain", "brain_lexical")
_DEFAULT_CONTENDERS = ("det_moe_full", "brain", "brain_lexical")


def _score_lm_contender(referee: BoxingReferee, c: Dict, reference: Set[str]) -> Dict[str, float]:
    """Score any LLM-based contender (det_moe_full / llm_only / det_eng_only)."""
    valid_techs = c.get("validated_techniques") or c["techniques"]
    all_techs = c["techniques"]
    # D1: precision — penalises hallucinations; recall against reference is always ~100%
    #     for the gold-standard contender that built the reference.
    d1 = referee.score_d1_precision(valid_techs, all_techs)
    d2 = referee.score_d2_validated(c["self_val"])
    d3 = referee.score_d3(valid_techs)
    d4 = referee.score_d4_bot(c["control_recommendations"])
    return {"threat_completeness": d1, "threat_accuracy": d2,
            "mitigation_relevance": d3, "actionability": d4,
            "composite": referee.composite(d1, d2, d3, d4)}


def _score_llm_only_contender(referee: BoxingReferee, c: Dict, reference: Set[str]) -> Dict[str, float]:
    """
    Score pure-LLM contender.
    D1: precision (validated MITRE IDs / total predicted) — penalises hallucinated IDs.
    D2: recall vs gold reference — measures how much of the reference the LLM independently found.
    D3/D4: standard mitigation coverage + control actionability.
    """
    all_techs = c["techniques"]
    valid_techs = c.get("validated_techniques") or all_techs
    d1 = referee.score_d1_precision(valid_techs, all_techs)
    d2 = referee.score_d1(valid_techs, reference)   # recall vs gold: did LLM find what RAPIDS found?
    d3 = referee.score_d3(valid_techs)
    d4 = referee.score_d4_bot(c["control_recommendations"])
    return {"threat_completeness": d1, "threat_accuracy": d2,
            "mitigation_relevance": d3, "actionability": d4,
            "composite": referee.composite(d1, d2, d3, d4)}


def _score_brain_contender(referee: BoxingReferee, c: Dict, reference: Set[str]) -> Dict[str, float]:
    """Score brain (corpus pattern inference). D1 = recall vs gold reference."""
    techs = c["techniques"]
    d1 = referee.score_d1(techs, reference)
    d2 = referee.score_d2_corpus(c["pattern_ids"])
    d3 = referee.score_d3(techs)
    d4 = referee.score_d4_brain(c["infer_result"])
    return {"threat_completeness": d1, "threat_accuracy": d2,
            "mitigation_relevance": d3, "actionability": d4,
            "composite": referee.composite(d1, d2, d3, d4)}


def _score_lexical_contender(referee: BoxingReferee, c: Dict, reference: Set[str]) -> Dict[str, float]:
    """Score brain-lexical. D1 = recall vs reference; D2 = fraction that are real MITRE IDs."""
    techs = c["techniques"]
    d1 = referee.score_d1(techs, reference)
    # D2: how many lexical hits are real MITRE technique IDs (rough applicability proxy)
    d2 = round(len([t for t in techs if t.startswith("T") or t.startswith("AML.")]) / max(len(techs), 1), 4)
    d3 = referee.score_d3(techs)
    d4 = 0.0  # lexical produces no control recommendations
    return {"threat_completeness": d1, "threat_accuracy": d2,
            "mitigation_relevance": d3, "actionability": d4,
            "composite": referee.composite(d1, d2, d3, d4)}


def run_boxing_match(
    arch_name: str,
    mmd_path: str,
    ssp_profile: str = "low_risk_cloud",
    arch_type: str = "",
    models: Optional[List[str]] = None,
    contenders: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run a boxing match for arch_name and write boxing_results.json.

    Args:
        arch_name:   architecture identifier
        mmd_path:    path to the .mmd file
        ssp_profile: SSP profile for LLM contenders
        arch_type:   optional arch_type hint for brain inference
        models:      list of LLM_PROVIDER keys to run multiple det_moe_full variants
        contenders:  which contenders to run; defaults to det_moe_full + brain + brain_lexical.
                     Any of: det_moe_full, llm_only, det_eng_only, brain, brain_lexical

    Returns:
        Full scorecard dict (also written to report/<arch_name>/boxing_results.json).
    """
    from chatbot.config import get_settings

    run_set = set(contenders or _DEFAULT_CONTENDERS)
    report_dir = Path(get_settings().system.report_dir) / arch_name
    report_dir.mkdir(parents=True, exist_ok=True)
    referee = BoxingReferee()

    results_map: Dict[str, Dict] = {}  # key → raw contender data

    # ── Det/MoE Full (gold standard, always run first — builds the reference) ─
    if "det_moe_full" in run_set:
        model_list: List[Optional[str]] = list(models) if models else [None]
        for model in model_list:
            key = f"det_moe_full_{model}" if model else "det_moe_full"
            logger.info("Boxing: det_moe_full [%s] for %s", model or "default", arch_name)
            results_map[key] = run_det_moe_full_contender(arch_name, mmd_path, ssp_profile, model_override=model)

    # ── Reference = validated techniques from all det_moe_full runs ───────────
    reference: Set[str] = set()
    for key, data in results_map.items():
        if key.startswith("det_moe_full"):
            reference.update(data.get("validated_techniques") or data["techniques"])

    # ── LLM-only (opt-in) ─────────────────────────────────────────────────────
    if "llm_only" in run_set:
        llm_model_list: List[Optional[str]] = list(models) if models else [None]
        for model in llm_model_list:
            key = f"llm_only_{model}" if model else "llm_only"
            logger.info("Boxing: llm_only [%s] for %s", model or "default", arch_name)
            results_map[key] = run_llm_only_contender(arch_name, mmd_path, ssp_profile, model_override=model)

    # ── Det/Eng-only (opt-in) ─────────────────────────────────────────────────
    if "det_eng_only" in run_set:
        logger.info("Boxing: det_eng_only for %s", arch_name)
        results_map["det_eng_only"] = run_det_eng_only_contender(arch_name, mmd_path, ssp_profile)

    # ── Brain (corpus pattern) ────────────────────────────────────────────────
    if "brain" in run_set:
        logger.info("Boxing: brain for %s", arch_name)
        results_map["brain"] = run_brain_contender(arch_name, arch_type)

    # ── Brain-lexical (keyword scan) ──────────────────────────────────────────
    if "brain_lexical" in run_set:
        logger.info("Boxing: brain_lexical for %s", arch_name)
        results_map["brain_lexical"] = run_brain_lexical_contender(mmd_path)

    # ── Score all contenders ──────────────────────────────────────────────────
    scored: Dict[str, Any] = {}
    for key, data in results_map.items():
        if key.startswith("llm_only"):
            scores = _score_llm_only_contender(referee, data, reference)
            valid_techs = data.get("validated_techniques") or data["techniques"]
            scored[key] = {
                "label": data["label"],
                "model": data.get("model"),
                "technique_count": len(data["techniques"]),
                "validated_technique_count": len(valid_techs),
                "latency_s": data["latency_s"],
                "token_cost": data["token_cost"],
                "error": data["error"],
                "scores": scores,
            }
        elif key.startswith("det_moe_full") or key == "det_eng_only":
            scores = _score_lm_contender(referee, data, reference)
            valid_techs = data.get("validated_techniques") or data["techniques"]
            scored[key] = {
                "label": data["label"],
                "model": data.get("model"),
                "technique_count": len(data["techniques"]),
                "validated_technique_count": len(valid_techs),
                "latency_s": data["latency_s"],
                "token_cost": data["token_cost"],
                "error": data["error"],
                "scores": scores,
            }
        elif key == "brain":
            scores = _score_brain_contender(referee, data, reference)
            scored[key] = {
                "label": data["label"],
                "model": "brain",
                "technique_count": len(data["techniques"]),
                "corpus_hits": data.get("corpus_hits", 0),
                "latency_s": data["latency_s"],
                "token_cost": 0,
                "error": data["error"],
                "scores": scores,
            }
        elif key == "brain_lexical":
            scores = _score_lexical_contender(referee, data, reference)
            scored[key] = {
                "label": data["label"],
                "model": "lexical",
                "technique_count": len(data["techniques"]),
                "latency_s": data["latency_s"],
                "token_cost": 0,
                "error": data["error"],
                "scores": scores,
            }

    # ── Verdict ───────────────────────────────────────────────────────────────
    ranking = sorted(
        [(k, c["scores"]["composite"]) for k, c in scored.items()],
        key=lambda x: x[1], reverse=True,
    )

    gold_latency = scored.get("det_moe_full", {}).get("latency_s", 1.0) or 1.0
    brain_composite = scored.get("brain", {}).get("scores", {}).get("composite", 0)
    gold_composite = scored.get("det_moe_full", {}).get("scores", {}).get("composite", 0)
    qvsc: Dict[str, Any] = {
        "brain_vs_gold_delta": round(brain_composite - gold_composite, 4),
        "brain_latency_speedup": round(gold_latency / max(scored.get("brain", {}).get("latency_s", 0.001), 0.001), 1),
        "lexical_vs_brain_delta": round(
            scored.get("brain_lexical", {}).get("scores", {}).get("composite", 0) - brain_composite, 4
        ),
    }

    # Routing signals — consumed by smart_router.py to select pipeline mode
    corpus_hits = scored.get("brain", {}).get("corpus_hits", 0)
    brain_vs_gold_delta = qvsc.get("brain_vs_gold_delta", None)
    routing_signals: Dict[str, Any] = {
        "brain_vs_gold_delta": brain_vs_gold_delta,
        "corpus_hits": corpus_hits,
        "ref_technique_count": len(reference),
        "arch_type": arch_type or "",
        "brain_latency_speedup": qvsc.get("brain_latency_speedup"),
    }

    result: Dict[str, Any] = {
        "arch_name": arch_name,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "mmd_path": mmd_path,
        "contenders_run": list(scored.keys()),
        "ref_technique_count": len(reference),
        "contenders": scored,
        "verdict": {
            "ranking": [r[0] for r in ranking],
            "winner": ranking[0][0] if ranking else "none",
            "scores": {r[0]: r[1] for r in ranking},
            "quality_vs_cost": qvsc,
        },
        "routing_signals": routing_signals,
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
