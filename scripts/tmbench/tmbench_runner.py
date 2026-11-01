#!/usr/bin/env python3
"""
tmbench_runner.py — TMbench Step 36: corpus runner + ground truth comparison.

Manages docs/tmbench/results/<tool>/ and diffs tool scores against corpus GT.

Modes:
  --ingest <tool> <file>    Copy a TM JSON into results/<tool>/ and score vs GT
  --score-all <tool>        Re-score all JSONs in results/<tool>/ vs GT
  --leaderboard             Cross-tool leaderboard ranked by mean score
  --status                  Coverage grid: which corpus archs have results per tool
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "docs/tmbench/corpus"
RESULTS_DIR = ROOT / "docs/tmbench/results"

# Import scorer from the tmbench-check skill
_SCORER_PATH = ROOT / ".claude/skills/tmbench-check/scripts/tmbench-check.py"

# Dynamically import score_tm from tmbench-check.py
import importlib.util as _ilu

def _load_scorer():
    spec = _ilu.spec_from_file_location("tmbench_check", _SCORER_PATH)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_scorer = _load_scorer()
score_tm = _scorer.score_tm
load_json = _scorer.load_json

SPEC_VERSION = "threatmodel/0.1"
PASS_THRESHOLD = 8

CORPUS_ARCHS = [
    "t1_web_app", "t1_rest_api",
    "t2_microservices", "t2_cicd_pipeline", "t2_saas_integration",
    "t3_multicloud_data", "t3_hybrid_identity", "t3_container_orchestration",
    "t4_rag_pipeline", "t4_agent_fleet",
]


def load_gt_scores(arch_id: str) -> dict | None:
    path = CORPUS_DIR / f"{arch_id}_scores.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def tatb_from_result(result: dict) -> dict:
    """Extract TATB int scores from a score_tm() result dict."""
    return {k: v[0] for k, v in result["tatb"].items()}


def tatb_from_gt(gt: dict) -> dict:
    """Extract TATB int scores from a ground truth scores JSON."""
    return gt.get("tatb", {})


def delta(tool_val: int, gt_val: int) -> str:
    d = tool_val - gt_val
    if d > 0:
        return f"+{d}"
    return str(d)


def score_file_vs_gt(tm_path: Path, verbose: bool = True) -> dict | None:
    tm = load_json(tm_path)
    if not tm:
        return None

    arch_id = tm.get("architecture_id") or tm_path.stem
    result = score_tm(tm, arch_id=arch_id)
    gt = load_gt_scores(arch_id)

    tool_tatb = tatb_from_result(result)
    gt_tatb = tatb_from_gt(gt) if gt else None

    output = {
        "arch_id": arch_id,
        "produced_by": result["produced_by"],
        "total": result["total"],
        "max_score": result["max_score"],
        "status": result["status"],
        "confidence": result["confidence"],
        "tatb": tool_tatb,
        "gaps": result["gaps"],
    }

    if gt:
        output["gt_total"] = gt.get("total", "?")
        output["gt_tatb"] = gt_tatb
        output["tatb_delta"] = {
            k: tool_tatb.get(k, 0) - gt_tatb.get(k, 0)
            for k in gt_tatb
        }
        output["score_delta"] = result["total"] - gt.get("total", 0)

    if verbose:
        _print_single(output, show_gt=bool(gt))

    return output


def _print_single(r: dict, show_gt: bool = True) -> None:
    dims = ["threat_relevant", "ttp_accurate", "risk_defensible", "plan_actionable"]
    dim_labels = ["TR", "TA", "RD", "PA"]

    print(f"\n  arch:       {r['arch_id']}")
    print(f"  tool:       {r['produced_by']}")
    print(f"  score:      {r['total']}/{r['max_score']}  [{r['status']} — {r['confidence']}]")

    tool_vals = [r["tatb"].get(d, 0) for d in dims]
    print(f"  TATB:       {' '.join(f'{l}={v}' for l, v in zip(dim_labels, tool_vals))}")

    if show_gt and "gt_tatb" in r:
        gt_vals = [r["gt_tatb"].get(d, 0) for d in dims]
        deltas = [r["tatb_delta"].get(d, 0) for d in dims]
        print(f"  GT TATB:    {' '.join(f'{l}={v}' for l, v in zip(dim_labels, gt_vals))}")
        delta_str = "  ".join(
            (f"+{d}" if d > 0 else str(d)) for d in deltas
        )
        score_d = r.get("score_delta", 0)
        score_d_str = f"+{score_d}" if score_d > 0 else str(score_d)
        print(f"  Δ vs GT:    TR  TA  RD  PA    total")
        print(f"              {delta_str}       {score_d_str}")

    if r.get("gaps"):
        priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        sorted_gaps = sorted(r["gaps"], key=lambda g: priority_order.get(g[0], 4))
        print(f"  gaps ({len(sorted_gaps)}):")
        for sev, msg in sorted_gaps[:5]:
            print(f"    [{sev}] {msg}")
        if len(sorted_gaps) > 5:
            print(f"    ... +{len(sorted_gaps) - 5} more")


def cmd_ingest(tool: str, file_path: str) -> None:
    src = Path(file_path)
    if not src.exists():
        print(f"[error] file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    tm = load_json(src)
    if not tm:
        sys.exit(1)

    arch_id = tm.get("architecture_id") or src.stem
    dest_dir = RESULTS_DIR / tool
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{arch_id}.json"
    shutil.copy2(src, dest)
    print(f"Ingested: {src.name} → results/{tool}/{arch_id}.json")
    score_file_vs_gt(dest, verbose=True)


def cmd_score_all(tool: str) -> list[dict]:
    tool_dir = RESULTS_DIR / tool
    if not tool_dir.exists():
        print(f"[error] results/{tool}/ does not exist — run --ingest first", file=sys.stderr)
        sys.exit(1)

    files = sorted(tool_dir.glob("*.json"))
    if not files:
        print(f"No JSON files in results/{tool}/")
        return []

    print(f"\nScoring all {len(files)} result(s) for tool: {tool}")
    results = []
    for f in files:
        r = score_file_vs_gt(f, verbose=True)
        if r:
            results.append(r)

    _print_summary(tool, results)
    return results


def _print_summary(tool: str, results: list[dict]) -> None:
    if not results:
        return
    scores = [r["total"] for r in results]
    mean = sum(scores) / len(scores)
    passing = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n  ── Summary for {tool} ──")
    print(f"  Archs scored:  {len(results)}")
    print(f"  Mean score:    {mean:.2f}/13")
    print(f"  Pass rate:     {passing}/{len(results)}")
    if any("score_delta" in r for r in results):
        deltas = [r["score_delta"] for r in results if "score_delta" in r]
        mean_delta = sum(deltas) / len(deltas)
        print(f"  Mean Δ vs GT:  {mean_delta:+.2f}")


def cmd_leaderboard() -> None:
    tool_dirs = [d for d in RESULTS_DIR.iterdir() if d.is_dir()] if RESULTS_DIR.exists() else []
    if not tool_dirs:
        print("No tool results found. Run --ingest <tool> <file> to add results.")
        return

    rows = []
    for tool_dir in sorted(tool_dirs):
        tool = tool_dir.name
        files = sorted(tool_dir.glob("*.json"))
        tool_results = []
        for f in files:
            tm = load_json(f)
            if tm:
                arch_id = tm.get("architecture_id") or f.stem
                result = score_tm(tm, arch_id=arch_id)
                gt = load_gt_scores(arch_id)
                tool_results.append({
                    "arch_id": arch_id,
                    "total": result["total"],
                    "gt_total": gt.get("total", "?") if gt else "?",
                    "status": result["status"],
                    "tatb": {k: v[0] for k, v in result["tatb"].items()},
                })

        if not tool_results:
            continue

        scores = [r["total"] for r in tool_results]
        mean = sum(scores) / len(scores)
        passing = sum(1 for r in tool_results if r["status"] == "PASS")
        gt_scores = [r["gt_total"] for r in tool_results if isinstance(r.get("gt_total"), int)]
        mean_delta = (sum(scores) - sum(gt_scores)) / len(gt_scores) if gt_scores else None

        rows.append({
            "tool": tool,
            "archs": len(tool_results),
            "mean": mean,
            "passing": passing,
            "mean_delta": mean_delta,
        })

    rows.sort(key=lambda x: -x["mean"])

    print(f"\nTMbench Leaderboard  (spec {SPEC_VERSION})")
    print(f"  {'Tool':<28} {'Archs':>6} {'Mean':>6} {'Pass':>6} {'Δ vs GT':>8}")
    print(f"  {'-'*28} {'-----':>6} {'----':>6} {'----':>6} {'-------':>8}")
    for r in rows:
        delta_str = f"{r['mean_delta']:+.2f}" if r["mean_delta"] is not None else "  —"
        print(f"  {r['tool']:<28} {r['archs']:>6} {r['mean']:>6.2f} {r['passing']:>6} {delta_str:>8}")

    print(f"\n  Corpus size: {len(CORPUS_ARCHS)} reference architectures")
    print(f"  Pass threshold: ≥{PASS_THRESHOLD} with no TATB dimension at 0")


def cmd_status() -> None:
    print(f"\nTMbench Coverage Status")
    print(f"  Corpus: {len(CORPUS_ARCHS)} architectures\n")

    tool_dirs = sorted(d for d in RESULTS_DIR.iterdir() if d.is_dir()) if RESULTS_DIR.exists() else []
    tools = [d.name for d in tool_dirs]

    if not tools:
        print("  No tool results yet. Run --ingest <tool> <file> to add results.")
        return

    # Header
    header = f"  {'arch_id':<32}"
    for t in tools:
        header += f" {t[:10]:>10}"
    print(header)
    print("  " + "-" * (32 + 11 * len(tools)))

    for arch_id in CORPUS_ARCHS:
        row = f"  {arch_id:<32}"
        for t in tools:
            result_path = RESULTS_DIR / t / f"{arch_id}.json"
            if result_path.exists():
                tm = load_json(result_path)
                if tm:
                    r = score_tm(tm, arch_id=arch_id)
                    cell = f"{r['total']:2}/{r['max_score']}"
                else:
                    cell = "  err"
            else:
                cell = "  — "
            row += f" {cell:>10}"
        print(row)

    total_slots = len(CORPUS_ARCHS) * len(tools)
    filled = sum(
        1 for arch_id in CORPUS_ARCHS
        for t in tools
        if (RESULTS_DIR / t / f"{arch_id}.json").exists()
    )
    print(f"\n  Coverage: {filled}/{total_slots} slots filled across {len(tools)} tool(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="TMbench runner — Step 36")
    parser.add_argument("--ingest", nargs=2, metavar=("TOOL", "FILE"),
                        help="Ingest a TM JSON for a tool and score vs ground truth")
    parser.add_argument("--score-all", metavar="TOOL",
                        help="Re-score all results for a tool vs ground truth")
    parser.add_argument("--leaderboard", action="store_true",
                        help="Cross-tool leaderboard ranked by mean score")
    parser.add_argument("--status", action="store_true",
                        help="Coverage grid: corpus archs × tools")
    args = parser.parse_args()

    if args.ingest:
        cmd_ingest(args.ingest[0], args.ingest[1])
    elif args.score_all:
        cmd_score_all(args.score_all)
    elif args.leaderboard:
        cmd_leaderboard()
    elif args.status:
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
