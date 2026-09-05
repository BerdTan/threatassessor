#!/usr/bin/env python3
"""
ta-boxing — Brain vs Bot evaluation for a single architecture.

Usage:
    python3 ta-boxing.py --arch <arch_name> --mmd <path/to/arch.mmd>
    python3 ta-boxing.py --arch 22_generic_ai_nodes --mmd tests/data/architectures/22_generic_ai_nodes.mmd
    python3 ta-boxing.py --arch 22_generic_ai_nodes --mmd ... --gate bot:actionability:0.6
    python3 ta-boxing.py --list                         # list past boxing results
    python3 ta-boxing.py --arch 22_generic_ai_nodes --show-last  # show last stored result
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


CONTENDER_LABELS = {
    "bot":        "LLM Pipeline",
    "brain":      "TA Brain (corpus)",
    "brain_mini": "TA Brain-mini (arch-specific)",
}

DIM_LABELS = {
    "threat_completeness":  "D1 Completeness",
    "threat_accuracy":      "D2 Accuracy",
    "mitigation_relevance": "D3 Mitigations",
    "actionability":        "D4 Actionability",
    "composite":            "Composite",
}


def _bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def _pct(v) -> str:
    return f"{v * 100:.1f}%" if v is not None else "—"


def render_scorecard(result: dict) -> None:
    arch      = result.get("arch_name", "?")
    run_at    = (result.get("run_at") or "")[:16].replace("T", " ")
    ref_count = result.get("ref_technique_count", "?")
    contenders = result.get("contenders", {})
    verdict   = result.get("verdict", {})
    winner    = verdict.get("winner", "")
    qvsc      = verdict.get("quality_vs_cost", {})

    col_w = 16
    print()
    print(f"  ╔══ TA Boxing: {arch} ══╗")
    print(f"  Run: {run_at}  |  Reference techniques: {ref_count}")
    print()

    # Header
    header = f"  {'Dimension':<24}"
    for key in contenders:
        label = CONTENDER_LABELS.get(key, key)
        win_mark = " ★" if key == winner else "  "
        header += f"{(label + win_mark):<{col_w}}"
    print(header)
    print("  " + "─" * (24 + col_w * len(contenders)))

    # Score rows
    for dim, dim_label in DIM_LABELS.items():
        is_composite = dim == "composite"
        row = f"  {'> ' + dim_label if is_composite else dim_label:<24}"
        best_score = max(
            (c.get("scores", {}).get(dim) or 0) for c in contenders.values()
        )
        for key, c in contenders.items():
            score = (c.get("scores") or {}).get(dim)
            mark = " ◀" if score is not None and score == best_score and not is_composite else ""
            row += f"{_pct(score) + mark:<{col_w}}"
        print(row)

    print("  " + "─" * (24 + col_w * len(contenders)))

    # Efficiency rows
    lat_row = f"  {'Latency':<24}"
    for c in contenders.values():
        lat = c.get("latency_s")
        lat_row += f"{(str(lat) + 's'):<{col_w}}" if lat is not None else f"{'—':<{col_w}}"
    print(lat_row)

    tok_row = f"  {'Token Cost':<24}"
    for c in contenders.values():
        tok = c.get("token_cost", 0)
        tok_row += f"{(f'{tok:,}' if tok else '0'):<{col_w}}"
    print(tok_row)

    print()
    print(f"  Winner: {CONTENDER_LABELS.get(winner, winner)}")
    delta = qvsc.get("brain_vs_bot_quality_delta")
    if delta is not None:
        sign = "+" if delta > 0 else ""
        print(f"  Brain vs Bot quality delta: {sign}{delta * 100:.1f}%")
    spd = qvsc.get("brain_latency_speedup")
    if spd is not None:
        print(f"  Brain speedup: {spd}×  |  Brain-mini speedup: {qvsc.get('brain_mini_latency_speedup', '?')}×")
    print()


def run_match(arch_name: str, mmd_path: str, ssp_profile: str, arch_type: str,
              models: list | None = None) -> dict:
    from chatbot.modules.ta_boxing import run_boxing_match
    print(f"  Running boxing match for {arch_name}…")
    print(f"  MMD: {mmd_path}")
    if models:
        print(f"  Bot contenders: {', '.join(models)} (LANGFUSE_SKIP=1, ~30s each)")
    else:
        print(f"  Bot pipeline starting (LANGFUSE_SKIP=1, ~30s)…")
    result = run_boxing_match(
        arch_name=arch_name,
        mmd_path=mmd_path,
        ssp_profile=ssp_profile,
        arch_type=arch_type,
        models=models,
    )
    return result


def list_results() -> None:
    from chatbot.config import get_settings
    report_dir = Path(get_settings().system.report_dir)
    results = sorted(report_dir.glob("*/boxing_results.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not results:
        print("  No boxing results found. Run a match first.")
        return
    print(f"\n  {'Architecture':<32} {'Run At':<18} {'Winner':<14} Composite Scores")
    print("  " + "─" * 90)
    for p in results:
        try:
            d = json.loads(p.read_text())
            arch  = d.get("arch_name", p.parent.name)
            run   = (d.get("run_at") or "")[:16].replace("T", " ")
            win   = CONTENDER_LABELS.get(d.get("verdict", {}).get("winner", ""), "?")
            scores = d.get("verdict", {}).get("scores", {})
            s_str = "  ".join(f"{k}: {v * 100:.1f}%" for k, v in scores.items())
            print(f"  {arch:<32} {run:<18} {win:<14} {s_str}")
        except Exception:
            pass
    print()


def check_gate(result: dict, gate_spec: str) -> bool:
    """Parse contender:dimension:threshold and exit 1 if below threshold."""
    parts = gate_spec.split(":")
    if len(parts) != 3:
        print(f"  ERROR: --gate must be contender:dimension:threshold e.g. bot:actionability:0.7")
        sys.exit(2)
    contender, dim, threshold_str = parts
    try:
        threshold = float(threshold_str)
    except ValueError:
        print(f"  ERROR: threshold must be a float, got {threshold_str!r}")
        sys.exit(2)
    score = result.get("contenders", {}).get(contender, {}).get("scores", {}).get(dim)
    if score is None:
        print(f"  GATE: {contender}.{dim} — no score found")
        return False
    passed = score >= threshold
    status = "PASS" if passed else "FAIL"
    print(f"  GATE {status}: {contender}.{dim} = {_pct(score)} (threshold {_pct(threshold)})")
    return passed


def main() -> None:
    ap = argparse.ArgumentParser(description="TA Boxing — Brain vs Bot evaluation")
    ap.add_argument("--arch",      help="Architecture name")
    ap.add_argument("--mmd",       help="Path to .mmd file")
    ap.add_argument("--ssp-profile", default="low_risk_cloud")
    ap.add_argument("--arch-type", default="")
    ap.add_argument("--model",     help="Single LLM_PROVIDER override for the bot contender (e.g. gemini_flash)")
    ap.add_argument("--models",    help="Comma-separated LLM_PROVIDER keys for multi-model comparison (e.g. hetzner,gemini_flash,minimax)")
    ap.add_argument("--gate",      help="contender:dimension:threshold — exit 1 if below")
    ap.add_argument("--list",      action="store_true", help="List past boxing results")
    ap.add_argument("--show-last", action="store_true", help="Show last stored result for --arch")
    args = ap.parse_args()

    if args.list:
        list_results()
        return

    if args.show_last:
        if not args.arch:
            print("  ERROR: --show-last requires --arch")
            sys.exit(1)
        from chatbot.config import get_settings
        result_path = Path(get_settings().system.report_dir) / args.arch / "boxing_results.json"
        if not result_path.exists():
            print(f"  No boxing results for {args.arch}")
            sys.exit(1)
        render_scorecard(json.loads(result_path.read_text()))
        return

    if not args.arch or not args.mmd:
        ap.print_help()
        sys.exit(1)

    # Resolve model list
    models = None
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    elif args.model:
        models = [args.model]

    mmd_abs = str(Path(args.mmd).resolve())
    result = run_match(args.arch, mmd_abs, args.ssp_profile, args.arch_type, models=models)
    render_scorecard(result)

    if args.gate:
        passed = check_gate(result, args.gate)
        sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
