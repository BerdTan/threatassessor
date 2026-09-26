"""
JevTATBLabeller — System 1 TATB quality scorer via Jev (typesafe.ai).

Sends 4 score questions per instance in one /v1/systemone call:
  threat_relevant  — threats plausible for this arch type and topology
  ttp_accurate     — ATT&CK techniques reflect the real attack surface
  risk_defensible  — AIVSS composite proportionate to arch profile
  plan_actionable  — missing controls actionable against detected techniques

Validation path (--validate-jev in ta_brain_builder.py):
  1. Run on HOLD_OUT_ARCHS instances from ta_brain_instances.jsonl
  2. For each: brain infer → technique recall vs actual techniques in instance
  3. Brier = mean( (jev_ttp_accurate - brain_recall)^2 )
  4. Compare to baseline Brier (na0ive 0.5 labeller)
  5. Promote if jev_brier < baseline_brier (or explicit --promote flag)

Not an LLM — no generation, no variability. Falls back to neutral 0.5 on
API failure so callers are never blocked.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from chatbot.modules.ta_brain_query import query_brain

logger = logging.getLogger(__name__)

JEV_API_URL = os.environ.get("JEV_API_URL", "https://api.typesafe.ai/v1/systemone")

_QUESTIONS = {
    "threat_relevant": {
        "type": "score",
        "question": (
            "Are the identified threats relevant and plausible for this architecture "
            "type, scale, and topology?"
        ),
    },
    "ttp_accurate": {
        "type": "score",
        "question": (
            "Do the predicted MITRE ATT&CK techniques accurately reflect the "
            "attack surface implied by the architecture profile?"
        ),
    },
    "risk_defensible": {
        "type": "score",
        "question": (
            "Is the composite risk severity defensible given the node count, "
            "edge count, and architecture type?"
        ),
    },
    "plan_actionable": {
        "type": "score",
        "question": (
            "Are the identified missing controls actionable and proportionate to "
            "the detected threat techniques?"
        ),
    },
}

_DIMS = list(_QUESTIONS.keys())


class JevTATBLabeller:
    """
    System 1 TATB labeller: 4 score dims per instance, one Jev API call.
    Thread-safe — no shared mutable state.
    """

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key or os.environ.get("JEV_API_KEY", "")
        self.timeout = timeout
        if not self.api_key:
            logger.warning("JEV_API_KEY not set — label() will return neutral scores")

    # ── Public API ────────────────────────────────────────────────────────────

    def label(self, instance: dict) -> dict:
        """
        Score one instance.
        Returns {threat_relevant, ttp_accurate, risk_defensible, plan_actionable,
                 composite, error?}.
        Never raises — falls back to neutral 0.5 on API failure.
        """
        import requests  # lazy — only loaded when Jev is active

        state = _build_state(instance)
        try:
            resp = requests.post(
                JEV_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"state": state, "questions": _QUESTIONS},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            answers = resp.json().get("answers", {})
        except Exception as exc:
            logger.warning("Jev API error for %s: %s", instance.get("arch_id", "?"), exc)
            return {d: 0.5 for d in _DIMS} | {"composite": 0.5, "error": str(exc)}

        scores = {d: float(answers.get(d, {}).get("score", 0.5)) for d in _DIMS}
        scores["composite"] = round(sum(scores[d] for d in _DIMS) / len(_DIMS), 4)
        return scores

    def brier_on_corpus(
        self,
        instances: list[dict],
        brain_path: Path,
    ) -> dict:
        """
        Brier score for Jev's ttp_accurate predictions vs actual technique
        recall on the supplied corpus (typically the hold-out set).

        For each instance:
          brain_recall = |brain_predicted_techniques ∩ actual| / |actual|
          brier_term   = (jev_ttp_accurate - brain_recall)^2

        Also computes naive baseline Brier (fixed 0.5 labeller) so callers
        can assess whether Jev adds signal beyond the prior.

        Returns:
          {n_instances, avg_brier, baseline_brier, improvement, per_instance}
        """
        brier_terms: list[float] = []
        baseline_terms: list[float] = []
        per_instance: list[dict] = []

        for inst in instances:
            arch_id = inst.get("arch_id", "?")
            actual = set(inst.get("techniques", []))
            if not actual:
                continue

            brain_result = query_brain(
                mode="infer",
                arch_name=arch_id,
                topology_signature=inst.get("topology_signature", ""),
                arch_type=inst.get("arch_type", ""),
                caller_type="jev_validation",
            )
            predicted = set(brain_result.get("techniques", []))
            recall = len(predicted & actual) / len(actual)

            jev = self.label(inst)
            ttp = jev.get("ttp_accurate", 0.5)

            brier = (ttp - recall) ** 2
            baseline = (0.5 - recall) ** 2

            brier_terms.append(brier)
            baseline_terms.append(baseline)
            per_instance.append({
                "arch_id": arch_id,
                "actual_technique_count": len(actual),
                "predicted_technique_count": len(predicted),
                "brain_recall": round(recall, 4),
                "jev_ttp_accurate": round(ttp, 4),
                "jev_composite": jev.get("composite", 0.5),
                "brier": round(brier, 4),
                "baseline_brier": round(baseline, 4),
            })

        if not brier_terms:
            return {"error": "no instances with techniques to score"}

        avg_brier = round(sum(brier_terms) / len(brier_terms), 6)
        avg_baseline = round(sum(baseline_terms) / len(baseline_terms), 6)
        improvement = round(avg_baseline - avg_brier, 6)

        return {
            "n_instances": len(brier_terms),
            "avg_brier": avg_brier,
            "baseline_brier": avg_baseline,
            "improvement": improvement,  # positive = Jev beats naive prior
            "promote": avg_brier < avg_baseline,
            "per_instance": per_instance,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_state(instance: dict) -> dict:
    return {
        "arch_type": instance.get("arch_type", "unknown"),
        "node_count": instance.get("node_count", 0),
        "edge_count": instance.get("edge_count", 0),
        "technique_count": len(instance.get("techniques", [])),
        "aivss_composite": instance.get("aivss_composite", 0.0),
        "aivss_severity": instance.get("aivss_severity", "UNKNOWN"),
        "controls_missing_count": len(instance.get("controls_missing", [])),
        "hub_node_count": len(instance.get("hub_nodes", [])),
    }


# ── Standalone runner ─────────────────────────────────────────────────────────

def run_jev_validation(
    instances_path: Path,
    brain_path: Path,
    hold_out_archs: frozenset,
    api_key: Optional[str] = None,
) -> dict:
    """
    Load hold-out instances and run Brier comparison. Called from ta_brain_builder CLI.
    """
    if not instances_path.exists():
        return {"error": f"Instances file not found: {instances_path}"}

    all_instances = []
    with instances_path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    all_instances.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Deduplicate: last write wins (matches JSONL append contract)
    seen: dict[str, dict] = {}
    for inst in all_instances:
        seen[inst["arch_id"]] = inst
    all_instances = list(seen.values())

    hold_out = [i for i in all_instances if i["arch_id"] in hold_out_archs]
    if not hold_out:
        return {"error": "No hold-out instances found — run build_brain first"}

    labeller = JevTATBLabeller(api_key=api_key)
    return labeller.brier_on_corpus(hold_out, brain_path)
