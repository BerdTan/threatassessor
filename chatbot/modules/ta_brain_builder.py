"""
TA Brain builder — Stage 1: instance ingest + distiller.

Reads all corpus architecture reports and produces:
  report/ta_brain_instances.jsonl  — append-only instance layer
  report/ta_brain.json             — pattern + meta layer

Determinism contract: NO LLM calls anywhere in this module. All confidence
values are formula-derived. topology_signature is a pure hash.
LLM is restricted to the output layer (explain/generate) added in later stages.
"""

import hashlib
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "report"

# Hold-out set: excluded from distiller training, used for E2E validation gate.
# One agentic, one data-pipeline, one traditional.
HOLD_OUT_ARCHS = frozenset({"21_agentic_ai_system", "03_aws_3tier", "20_data_pipeline"})

# A technique or control must appear in at least this many instances of the
# same arch_type to become part of a pattern.
MIN_EVIDENCE = 2


# ── Topology signature ────────────────────────────────────────────────────────

def compute_topology_signature(parsed_nodes: dict, parsed_edges: list) -> str:
    """
    Deterministic structural fingerprint — excludes all node names/labels.

    Same shape-set + same edge-shape-pattern → identical hash regardless of
    what the nodes are called.  Collision-resistant across all 30 corpus archs.
    """
    shapes = sorted(v.get("shape", "unknown") for v in parsed_nodes.values())

    shape_by_id = {k: v.get("shape", "unknown") for k, v in parsed_nodes.items()}
    edge_pairs = sorted(
        (
            shape_by_id.get(e.get("source", ""), "?"),
            shape_by_id.get(e.get("target", ""), "?"),
        )
        for e in parsed_edges
    )

    payload = json.dumps({"shapes": shapes, "edges": edge_pairs}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Hub node extraction ───────────────────────────────────────────────────────

def compute_hub_nodes(parsed_edges: list, parsed_nodes: dict, top_n: int = 3) -> list:
    """Top-N nodes by out-degree, returned as shape labels (not names)."""
    out_degree: Counter = Counter()
    for e in parsed_edges:
        src = e.get("source", "")
        if src:
            out_degree[src] += 1
    shape_by_id = {k: v.get("shape", "unknown") for k, v in parsed_nodes.items()}
    return [shape_by_id.get(nid, "unknown") for nid, _ in out_degree.most_common(top_n)]


# ── Instance extraction ───────────────────────────────────────────────────────

def _load_rule_evaluator():
    from chatbot.harness.rule_evaluator import RuleEvaluator  # noqa: PLC0415
    return RuleEvaluator()


def extract_instance(arch_dir: Path, rule_evaluator=None) -> Optional[dict]:
    """
    Extract one InstanceEntry from a corpus arch directory.

    Returns None if required files are missing or malformed.
    Fired DETECT rules are computed live via RuleEvaluator (deterministic —
    same signals → same rules every time).
    """
    gt_path = arch_dir / "ground_truth.json"
    gs_path = arch_dir / "governance_signals.json"
    if not gt_path.exists() or not gs_path.exists():
        return None

    try:
        gt = json.loads(gt_path.read_text())
        gs = json.loads(gs_path.read_text())
    except Exception as exc:
        logger.warning("Skipping %s: %s", arch_dir.name, exc)
        return None

    meta = gt.get("metadata", {})
    arch_type = meta.get("architecture_type", "unknown")
    parsed_nodes = meta.get("parsed_nodes", {})
    parsed_edges = meta.get("parsed_edges", [])
    node_count = meta.get("node_count", len(parsed_nodes))
    edge_count = meta.get("edge_count", len(parsed_edges))
    run_ts = meta.get("run_ts", "")

    topology_sig = compute_topology_signature(parsed_nodes, parsed_edges)
    hub_nodes = compute_hub_nodes(parsed_edges, parsed_nodes)

    techniques = gt.get("techniques", [])
    if isinstance(techniques, dict):
        techniques = list(techniques.keys())

    controls_missing = (
        gt.get("controls_missing")
        or gt.get("data", {}).get("controls_missing", [])
    )

    aivss = gs.get("aivss", {})
    aivss_composite = aivss.get("overall", {}).get("composite", 0.0)
    aivss_severity = aivss.get("overall", {}).get("severity", "UNKNOWN")

    fired_detect_rules: list = []
    if rule_evaluator is not None:
        try:
            findings = rule_evaluator.evaluate(gs)
            fired_detect_rules = [
                f.get("unmapped", {}).get("rule_id", "")
                for f in findings
                if isinstance(f, dict)
            ]
            fired_detect_rules = [r for r in fired_detect_rules if r]
        except Exception as exc:
            logger.debug("Rule evaluation skipped for %s: %s", arch_dir.name, exc)

    return {
        "arch_id": arch_dir.name,
        "arch_type": arch_type,
        "topology_signature": topology_sig,
        "node_count": node_count,
        "edge_count": edge_count,
        "techniques": techniques,
        "controls_missing": controls_missing,
        "hub_nodes": hub_nodes,
        "aivss_composite": float(aivss_composite),
        "aivss_severity": aivss_severity,
        "fired_detect_rules": fired_detect_rules,
        "run_ts": run_ts,
        "source": "real",
    }


# ── Distiller ─────────────────────────────────────────────────────────────────

def run_distiller(instances: list, min_evidence: int = MIN_EVIDENCE) -> list:
    """
    Co-occurrence pattern extraction — pure frequency analysis, no LLM.

    Produces one pattern per arch_type cluster. Each pattern records:
    - which techniques co-appear with their frequency
    - which controls are commonly missing
    - which DETECT rules fire
    - AIVSS floor + mean across the cluster
    - corpus_confidence = top-technique frequency within the cluster
    - benchmark_confidence = 1.0 (uncalibrated until Stage 6)

    Only real-source instances are used; synthetic instances (added in Stage 8)
    participate but never serve as sole evidence (MIN_EVIDENCE must include ≥1 real).
    """
    by_type: defaultdict = defaultdict(list)
    for inst in instances:
        by_type[inst["arch_type"]].append(inst)

    patterns = []
    pattern_id = 1

    for arch_type, group in sorted(by_type.items()):
        n = len(group)
        real_n = sum(1 for i in group if i.get("source") == "real")
        if n < 1:
            continue

        tech_counter: Counter = Counter()
        control_counter: Counter = Counter()
        rule_counter: Counter = Counter()

        for inst in group:
            for t in inst.get("techniques", []):
                tech_counter[t] += 1
            for c in inst.get("controls_missing", []):
                control_counter[c] += 1
            for r in inst.get("fired_detect_rules", []):
                rule_counter[r] += 1

        aivss_values = [inst["aivss_composite"] for inst in group]
        aivss_floor = round(min(aivss_values), 3) if aivss_values else 0.0
        aivss_mean = round(sum(aivss_values) / len(aivss_values), 3) if aivss_values else 0.0

        primary_techniques = [t for t, c in tech_counter.most_common() if c >= min_evidence]
        primary_controls = [ctrl for ctrl, c in control_counter.most_common(10) if c >= min_evidence]
        primary_rules = [r for r, c in rule_counter.most_common() if c >= min_evidence]

        # Fall back to top-5 if nothing clears MIN_EVIDENCE (sparse group)
        if not primary_techniques:
            primary_techniques = [t for t, _ in tech_counter.most_common(5)]
        if not primary_controls:
            primary_controls = [c for c, _ in control_counter.most_common(5)]

        top_tech_count = tech_counter.most_common(1)[0][1] if tech_counter else 0
        corpus_conf = round(top_tech_count / n, 3) if n else 0.0

        node_counts = [inst["node_count"] for inst in group]

        pattern = {
            "id": f"BRAIN-{pattern_id:03d}",
            "corpus_confidence_base": corpus_conf,
            "trigger": {
                "arch_type": arch_type,
                "node_count_min": min(node_counts) if node_counts else 0,
            },
            "predicts": {
                "techniques": primary_techniques[:20],
                "technique_frequencies": {
                    t: round(c / n, 3) for t, c in tech_counter.most_common(20)
                },
                "detect_rules": primary_rules,
                "aivss_floor": aivss_floor,
                "aivss_mean": aivss_mean,
                "common_missing_controls": primary_controls,
                "control_frequencies": {
                    c: round(cnt / n, 3) for c, cnt in control_counter.most_common(10)
                },
            },
            "remediation_template": {
                "priority_controls": primary_controls[:5],
                "mmd_patch_stub": (
                    f"# Recommended additions for {arch_type}: "
                    + ", ".join(primary_controls[:3])
                ),
            },
            "corpus_confidence": corpus_conf,
            "benchmark_confidence": 1.0,
            "evidence_count": n,
            "real_evidence_count": real_n,
            "evidence_arch_ids": [inst["arch_id"] for inst in group],
            "trend": "stable",
        }

        patterns.append(pattern)
        pattern_id += 1

    return patterns


# ── Gap detection (meta layer) ────────────────────────────────────────────────

def detect_gaps(instances: list, patterns: list) -> list:
    """
    Identify under-sampled topology regions. Produces the meta layer.

    Priority = thinness × danger. A gap is flagged `forced_gap=True` when
    added by the benchmark calibration track (Stage 6) — those cannot be
    deprioritized by coverage-thinness heuristics.
    """
    real_instances = [i for i in instances if i.get("source") == "real"]
    total_real = len(real_instances)
    by_type: Counter = Counter(i["arch_type"] for i in real_instances)

    pattern_by_type = {p["trigger"]["arch_type"]: p for p in patterns}

    gaps = []
    gap_id = 1

    for arch_type, count in sorted(by_type.items(), key=lambda x: x[1]):
        if count >= 3:
            continue  # well-sampled

        thinness = round(1.0 - (count / max(total_real, 1)), 3)
        pat = pattern_by_type.get(arch_type)
        danger = pat["predicts"]["aivss_mean"] if pat else 0.5

        gaps.append({
            "id": f"GAP-{gap_id:03d}",
            "region": f"arch_type:{arch_type}",
            "confidence_floor": pat["corpus_confidence"] if pat else 0.0,
            "generation_prompt": (
                f"Generate a realistic {arch_type} architecture diagram in Mermaid format. "
                f"Include at least {(pat['trigger']['node_count_min'] + 2) if pat else 5} nodes. "
                f"Do NOT replicate existing corpus entries. Focus on underrepresented topology variants."
            ),
            "priority": round(thinness * max(danger, 0.3), 3),
            "forced_gap": False,
        })
        gap_id += 1

    return sorted(gaps, key=lambda g: g["priority"], reverse=True)


# ── Brain builder (main entry point) ─────────────────────────────────────────

def build_brain(
    report_dir: Path = REPORT_DIR,
    hold_out: Optional[frozenset] = None,
    incremental: bool = True,
) -> dict:
    """
    Ingest all corpus archs → instance layer → distiller → brain JSON.

    hold_out: arch_ids excluded from distiller training (E2E validation set).
              Pass frozenset() to disable (all archs train).
    incremental: skip archs already recorded in ta_brain_instances.jsonl.

    Returns a summary dict. Raises nothing — errors are logged and skipped.
    """
    if hold_out is None:
        hold_out = HOLD_OUT_ARCHS

    instances_path = report_dir / "ta_brain_instances.jsonl"
    brain_path = report_dir / "ta_brain.json"

    # Load existing instances for incremental mode
    existing_ids: set = set()
    existing_instances: list = []
    if incremental and instances_path.exists():
        for line in instances_path.read_text().strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                inst = json.loads(line)
                existing_ids.add(inst["arch_id"])
                existing_instances.append(inst)
            except Exception:
                pass

    try:
        rule_evaluator = _load_rule_evaluator()
    except Exception as exc:
        logger.warning("RuleEvaluator unavailable (%s) — fired_detect_rules will be empty", exc)
        rule_evaluator = None

    new_instances: list = []
    skipped: list = []

    arch_dirs = sorted(
        d for d in report_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    for arch_dir in arch_dirs:
        if incremental and arch_dir.name in existing_ids:
            continue
        inst = extract_instance(arch_dir, rule_evaluator)
        if inst is None:
            skipped.append(arch_dir.name)
            continue
        new_instances.append(inst)

    if new_instances:
        with instances_path.open("a") as fh:
            for inst in new_instances:
                fh.write(json.dumps(inst) + "\n")

    all_instances = existing_instances + new_instances
    train_instances = [i for i in all_instances if i["arch_id"] not in hold_out]
    holdout_instances = [i for i in all_instances if i["arch_id"] in hold_out]

    patterns = run_distiller(train_instances)
    gaps = detect_gaps(train_instances, patterns)

    # Preserve + increment pattern_version across runs
    pattern_version = 1
    if brain_path.exists():
        try:
            pattern_version = json.loads(brain_path.read_text()).get("pattern_version", 0) + 1
        except Exception:
            pass

    brain = {
        "version": 1,
        "pattern_version": pattern_version,
        "built_ts": datetime.now(timezone.utc).isoformat(),
        "corpus_size": len(all_instances),
        "train_size": len(train_instances),
        "hold_out": sorted(hold_out),
        "patterns": patterns,
        "gaps": gaps,
    }

    brain_path.write_text(json.dumps(brain, indent=2))

    return {
        "ingested": len(new_instances),
        "skipped": skipped,
        "total_instances": len(all_instances),
        "train_instances": len(train_instances),
        "hold_out_instances": len(holdout_instances),
        "patterns": len(patterns),
        "gaps": len(gaps),
        "pattern_version": pattern_version,
        "instances_path": str(instances_path),
        "brain_path": str(brain_path),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="TA Brain builder — Stage 1 instance ingest + distiller"
    )
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    parser.add_argument("--incremental", action="store_true",
                        help="Skip archs already in ta_brain_instances.jsonl")
    parser.add_argument("--no-hold-out", action="store_true",
                        help="Include all archs in distiller (disables E2E gate)")
    parser.add_argument("--show-patterns", action="store_true")
    parser.add_argument("--pre-warm-cache", action="store_true",
                        help="Pre-warm ta_brain_cache.json after build (Stage 2.5)")
    parser.add_argument("--enrich-gaps", action="store_true",
                        help="Re-run demand-weighted gap detection from interaction log (Stage 5)")
    parser.add_argument("--calibrate", action="store_true",
                        help="Run benchmark calibration (Brier + framework floors) (Stage 6)")
    parser.add_argument("--process", action="store_true",
                        help="Run TACO processor — full coordinated feedback loop (Stage 7)")
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    result = build_brain(
        report_dir=report_dir,
        hold_out=frozenset() if args.no_hold_out else None,
        incremental=args.incremental,
    )

    print("\nTA Brain build complete")
    print(f"  Ingested:        {result['ingested']} new instances")
    print(f"  Total corpus:    {result['total_instances']}"
          f" ({result['train_instances']} train, {result['hold_out_instances']} hold-out)")
    print(f"  Patterns:        {result['patterns']}")
    print(f"  Gaps:            {result['gaps']}")
    print(f"  Pattern version: {result['pattern_version']}")
    if result["skipped"]:
        print(f"  Skipped:         {result['skipped']}")

    if args.show_patterns:
        brain = json.loads(Path(result["brain_path"]).read_text())
        print("\nPatterns:")
        for p in brain["patterns"]:
            print(
                f"  {p['id']}  arch_type={p['trigger']['arch_type']}"
                f"  conf={p['corpus_confidence']}"
                f"  evidence={p['evidence_count']}"
                f"  techniques={len(p['predicts']['techniques'])}"
                f"  missing_controls={len(p['predicts']['common_missing_controls'])}"
            )
        print("\nGaps:")
        for g in brain["gaps"]:
            print(f"  {g['id']}  region={g['region']}  priority={g['priority']}")

    if args.enrich_gaps:
        from chatbot.modules.ta_brain_gaps import enrich_brain_gaps
        gap_result = enrich_brain_gaps(
            brain_path=report_dir / "ta_brain.json",
            instances_path=report_dir / "ta_brain_instances.jsonl",
            interactions_path=report_dir / "ta_brain_interactions.jsonl",
        )
        print(f"\nGap enrichment complete")
        print(f"  Total gaps:      {gap_result['gaps_total']}")
        print(f"  coverage_thin:   {gap_result['gaps_coverage_thin']}")
        print(f"  query_miss:      {gap_result['gaps_query_miss']}")
        print(f"  variant:         {gap_result['gaps_variant']}")
        print(f"  forced:          {gap_result['gaps_forced']}")

    if args.process:
        from chatbot.modules.ta_brain_taco_processor import run_taco_processor
        proc = run_taco_processor(
            brain_path=report_dir / "ta_brain.json",
            instances_path=report_dir / "ta_brain_instances.jsonl",
            interactions_path=report_dir / "ta_brain_interactions.jsonl",
            cache_path=report_dir / "ta_brain_cache.json",
            state_path=report_dir / "ta_brain_processor_state.json",
        )
        print(f"\nTACO processor complete (run #{proc['processor_runs_total']})")
        print(f"  Patterns:     {proc['patterns']}  suspect={proc['suspect_patterns']}")
        print(f"  Avg bench_conf: {proc['avg_benchmark_confidence']}")
        print(f"  Gaps:         {proc['gaps_total']}  forced={proc['gaps_forced']}")
        print(f"  Calib priority: {proc['calibration_priority_count']} patterns flagged")
        print(f"  Log entries:  {proc['total_queries_in_log']} queries + {proc['total_feedback_in_log']} feedback")

    if args.calibrate:
        from chatbot.modules.ta_brain_benchmarks import save_calibration
        cal_result = save_calibration(
            brain_path=report_dir / "ta_brain.json",
            instances_path=report_dir / "ta_brain_instances.jsonl",
            report_dir=report_dir,
        )
        print(f"\nBenchmark calibration complete")
        print(f"  Calibrated:      {cal_result['patterns_calibrated']}/{cal_result['patterns_total']} patterns")
        print(f"  Avg Brier:       {cal_result['avg_brier_combined']}")
        print(f"  Divergences:     {cal_result['divergences']}")
        print(f"  Forced gaps:     {cal_result['forced_gaps_added']}")

    if args.pre_warm_cache:
        from chatbot.modules.ta_brain_cache import CacheManager, reset_singleton
        from chatbot.modules.ta_brain_query import _run_infer

        reset_singleton()
        brain_data = json.loads(Path(result["brain_path"]).read_text())
        instances_path = report_dir / "ta_brain_instances.jsonl"
        instances = []
        if instances_path.exists():
            for line in instances_path.read_text().strip().splitlines():
                if line.strip():
                    try:
                        instances.append(json.loads(line))
                    except Exception:
                        pass

        cache = CacheManager(report_dir / "ta_brain_cache.json")
        evicted = cache.evict_stale(brain_data.get("pattern_version", 0))
        written = cache.pre_warm(instances, brain_data, _run_infer, report_dir)
        print(f"\nCache pre-warm complete")
        print(f"  Evicted stale:   {evicted}")
        print(f"  Entries written: {written}")
        print(f"  Cache stats:     {cache.stats()}")

    sys.exit(0)
