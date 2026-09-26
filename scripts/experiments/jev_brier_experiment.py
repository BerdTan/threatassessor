#!/usr/bin/env python3
"""
Jev Brier experiment — three variants compared on hold-out set.

  A. noul   no prose  — current baseline (0.2158 from Session 96)
  B. noul + prose     — arch_description from MMD added to state
  C. score  w/ truth  — ttp_accurate swapped to score type,
                        criteria = list(actual_techniques)

Run:
  cd "$(git rev-parse --show-toplevel)" && source .venv/bin/activate
  python3 scripts/experiments/jev_brier_experiment.py

Requires JEV_API_KEY in .env or environment.
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Load .env
_dotenv = ROOT / ".env"
if _dotenv.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv, override=False)
    except ImportError:
        for _line in _dotenv.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS
from chatbot.modules.ta_brain_query import query_brain
from chatbot.modules.jev_client import JevClient

INSTANCES_PATH = ROOT / "report/brain/ta_brain_instances.jsonl"
BRAIN_PATH = ROOT / "report/brain/ta_brain.json"
MMD_DIR = ROOT / "tests/data/architectures"

NOUL_QUESTIONS = {
    "threat_relevant": {
        "type": "noul",
        "instructions": "Are the identified threats relevant and plausible for this architecture type, scale, and topology?",
    },
    "ttp_accurate": {
        "type": "noul",
        "instructions": "Do the predicted MITRE ATT&CK techniques accurately reflect the attack surface described in the architecture?",
    },
    "risk_defensible": {
        "type": "noul",
        "instructions": "Is the composite AIVSS risk severity defensible and proportionate given the architecture description and node complexity?",
    },
    "plan_actionable": {
        "type": "noul",
        "instructions": "Are the identified missing controls actionable and relevant to the detected threat techniques and architecture?",
    },
}


def load_hold_out():
    seen = {}
    with INSTANCES_PATH.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                inst = json.loads(line)
                seen[inst["arch_id"]] = inst
    return [v for v in seen.values() if v["arch_id"] in HOLD_OUT_ARCHS]


def load_mmd(arch_id: str) -> str:
    path = MMD_DIR / f"{arch_id}.mmd"
    if path.exists():
        return path.read_text().strip()
    # Try stripping variant suffix
    base = re.sub(r"_\d+$", "", arch_id)
    path = MMD_DIR / f"{base}.mmd"
    return path.read_text().strip() if path.exists() else ""


def build_state(instance: dict, with_prose: bool = False) -> dict:
    techniques = instance.get("techniques", [])
    controls = instance.get("controls_missing", [])
    state = {
        "arch_type": instance.get("arch_type", "unknown"),
        "node_count": instance.get("node_count", 0),
        "edge_count": instance.get("edge_count", 0),
        "technique_count": len(techniques),
        "techniques": techniques,
        "aivss_composite": instance.get("aivss_composite", 0.0),
        "aivss_severity": instance.get("aivss_severity", "UNKNOWN"),
        "controls_missing": controls,
        "controls_missing_count": len(controls),
        "hub_node_count": len(instance.get("hub_nodes", [])),
    }
    if with_prose:
        mmd = load_mmd(instance["arch_id"])
        if mmd:
            state["arch_description"] = mmd[:2000]
    return state


def score_questions_for(instance: dict) -> dict:
    """score type for ttp_accurate — criteria = actual technique list."""
    actual = list(instance.get("techniques", []))
    qs = dict(NOUL_QUESTIONS)
    qs["ttp_accurate"] = {
        "type": "score",
        "criteria": actual,
    }
    return qs


def run_variant(label: str, instances: list, client: JevClient,
                with_prose: bool, use_score: bool) -> dict:
    JevClient.reset_circuit()
    brier_terms = []
    baseline_terms = []
    rows = []

    for inst in instances:
        arch_id = inst["arch_id"]
        actual = set(inst.get("techniques", []))
        if not actual:
            continue

        brain_result = query_brain(
            mode="infer",
            arch_name=arch_id,
            topology_signature=inst.get("topology_signature", ""),
            arch_type=inst.get("arch_type", ""),
            caller_type="jev_experiment",
        )
        predicted = set(brain_result.get("predictions", {}).get("techniques", []))
        recall = len(predicted & actual) / len(actual) if actual else 0.0

        state = build_state(inst, with_prose=with_prose)
        questions = score_questions_for(inst) if use_score else NOUL_QUESTIONS
        answers = client.ask(state, questions)

        if not answers:
            ttp = 0.5
        elif use_score:
            ttp = float(answers.get("ttp_accurate", {}).get("score", 0.5))
        else:
            ttp = float(answers.get("ttp_accurate", {}).get("noul", 0.5))

        brier = (ttp - recall) ** 2
        baseline = (0.5 - recall) ** 2
        brier_terms.append(brier)
        baseline_terms.append(baseline)
        rows.append({
            "arch_id": arch_id,
            "recall": round(recall, 3),
            "ttp": round(ttp, 3),
            "brier": round(brier, 4),
        })

    avg_brier = sum(brier_terms) / len(brier_terms) if brier_terms else 0.0
    avg_base = sum(baseline_terms) / len(baseline_terms) if baseline_terms else 0.0
    return {
        "label": label,
        "n": len(brier_terms),
        "avg_brier": round(avg_brier, 6),
        "baseline": round(avg_base, 6),
        "improvement": round(avg_base - avg_brier, 6),
        "promote": avg_brier < avg_base,
        "rows": rows,
    }


def main():
    print("=" * 60)
    print("Jev Brier experiment — three variants")
    print("=" * 60)

    instances = load_hold_out()
    print(f"Hold-out instances: {len(instances)}")
    prose_count = sum(1 for i in instances if load_mmd(i["arch_id"]))
    print(f"With MMD prose available: {prose_count}/{len(instances)}")
    print()

    client = JevClient()
    if not client.is_enabled():
        print("ERROR: Jev not enabled — set JEV_API_KEY in .env")
        sys.exit(1)

    results = []

    print("Running variant A: noul, no prose ...")
    results.append(run_variant("A  noul  no-prose", instances, client,
                               with_prose=False, use_score=False))

    print("Running variant B: noul + prose ...")
    results.append(run_variant("B  noul  +prose  ", instances, client,
                               with_prose=True, use_score=False))

    print("Running variant C: score + actual techniques ...")
    results.append(run_variant("C  score +actual ", instances, client,
                               with_prose=False, use_score=True))

    print()
    print("=" * 60)
    print(f"{'Variant':<20} {'n':>4}  {'Brier':>8}  {'Baseline':>8}  {'Δ':>8}  Promote")
    print("-" * 60)
    for r in results:
        flag = "✓ PROMOTE" if r["promote"] else "  skip"
        print(f"{r['label']:<20} {r['n']:>4}  {r['avg_brier']:>8.4f}  {r['baseline']:>8.4f}"
              f"  {r['improvement']:>+8.4f}  {flag}")

    print()
    print("Per-instance breakdown:")
    print(f"  {'arch_id':<30} {'recall':>7}  ", end="")
    for r in results:
        print(f"  {r['label'][:6]:>7}", end="")
    print()
    arch_ids = [row["arch_id"] for row in results[0]["rows"]]
    for arch_id in arch_ids:
        print(f"  {arch_id:<30} ", end="")
        for r in results:
            row = next((x for x in r["rows"] if x["arch_id"] == arch_id), None)
            if row:
                print(f"  {row['recall']:>6.3f}  ", end="")
        for r in results:
            row = next((x for x in r["rows"] if x["arch_id"] == arch_id), None)
            if row:
                print(f"  {row['ttp']:>6.3f}", end="")
        print()


if __name__ == "__main__":
    main()
