#!/usr/bin/env python3
"""
tmleaderboard.py — TMbench leaderboard viewer and open submission tool.

Modes (default: show leaderboard):
  --show                        Print ranked leaderboard (default)
  --ingest <tool> <dir>         Score + store a new tool's TM JSONs
  --rescore <tool>              Re-score a stored tool against current spec
  --rescore-all                 Re-score all tools (after spec update)
  --diff <tool_a> <tool_b>      Per-arch dimension diff between two tools
  --breakdown <tool>            Full per-arch TATB breakdown for one tool
  --export md                   Print leaderboard as markdown table
  --list                        List all registered tools with arch counts
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[4]
RESULTS_DIR = ROOT / "docs/tmbench/results"
CORPUS_DIR  = ROOT / "docs/tmbench/corpus"
SPEC_PATH   = ROOT / "docs/tmbench/threatmodel.md"

SPEC_VERSION   = "threatmodel/0.1"
PASS_THRESHOLD = 8

# T-tier weights — primary ranking key is weighted mean
TIER_WEIGHTS = {"t1": 1.0, "t2": 1.5, "t3": 2.0, "t4": 2.5}

# ── import scorer from tmbench-check ─────────────────────────────────────────

_CHECKER = ROOT / ".claude/skills/tmbench-check/scripts/tmbench-check.py"

def _load_scorer():
    import importlib.util
    spec = importlib.util.spec_from_file_location("tmbench_check", _CHECKER)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

try:
    _scorer = _load_scorer()
    score_tm = _scorer.score_tm
except Exception as e:
    print(f"[error] cannot load tmbench-check scorer: {e}", file=sys.stderr)
    sys.exit(1)

# ── helpers ───────────────────────────────────────────────────────────────────

def tier_of(arch_id: str) -> str:
    for prefix in ("t4", "t3", "t2", "t1"):
        if arch_id.startswith(prefix + "_") or arch_id == prefix:
            return prefix
    return "t1"

def weight_of(arch_id: str) -> float:
    return TIER_WEIGHTS.get(tier_of(arch_id), 1.0)

def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [error] {path.name}: {e}", file=sys.stderr)
        return None

def score_tool_dir(tool_dir: Path) -> list[dict]:
    results = []
    for f in sorted(tool_dir.glob("*.json")):
        tm = load_json(f)
        if tm:
            result = score_tm(tm, arch_id=f.stem)
            result["_arch_id"]  = f.stem
            result["_tier"]     = tier_of(f.stem)
            result["_weight"]   = weight_of(f.stem)
            result["_tool_dir"] = str(tool_dir.name)
            results.append(result)
    return results

def tool_summary(tool_name: str, arch_results: list[dict]) -> dict:
    if not arch_results:
        return {"tool": tool_name, "arches": 0, "mean": 0.0, "wmean": 0.0, "passes": 0, "tier_means": {}}
    scores   = [r["total"] for r in arch_results]
    passes   = sum(1 for r in arch_results if r["status"] == "PASS")
    wsum     = sum(r["total"] * r["_weight"] for r in arch_results)
    wtot     = sum(r["_weight"] for r in arch_results)
    wmean    = wsum / wtot if wtot else 0.0

    tier_means = {}
    for tier in ("t1", "t2", "t3", "t4"):
        tier_rs = [r for r in arch_results if r["_tier"] == tier]
        if tier_rs:
            tier_means[tier] = sum(r["total"] for r in tier_rs) / len(tier_rs)

    return {
        "tool":       tool_name,
        "arches":     len(arch_results),
        "mean":       sum(scores) / len(scores),
        "wmean":      wmean,
        "passes":     passes,
        "tier_means": tier_means,
        "details":    arch_results,
    }

def load_all_tools() -> list[dict]:
    summaries = []
    for tool_dir in sorted(RESULTS_DIR.iterdir()):
        if not tool_dir.is_dir():
            continue
        arch_results = score_tool_dir(tool_dir)
        if arch_results:
            summaries.append(tool_summary(tool_dir.name, arch_results))
    return sorted(summaries, key=lambda s: (-s["wmean"], -s["mean"]))

# ── display ───────────────────────────────────────────────────────────────────

def print_leaderboard(summaries: list[dict]) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\nTMbench Leaderboard  spec {SPEC_VERSION}  |  {today}")
    print(f"Weighted mean: T1×1.0  T2×1.5  T3×2.0  T4×2.5  |  Pass threshold: {PASS_THRESHOLD}/13 (no zeros)\n")

    hdr = f"  {'Rank':>4}  {'Tool':<22}  {'Arches':>6}  {'Mean':>6}  {'W.Mean':>7}  {'Pass':>5}  {'T1':>5}  {'T2':>5}  {'T3':>5}  {'T4':>5}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for i, s in enumerate(summaries, 1):
        tm = s["tier_means"]
        def tf(tier): return f"{tm[tier]:.1f}" if tier in tm else "  —  "
        arches_str = f"{s['arches']}/10"
        passes_str = f"{s['passes']}/{s['arches']}"
        print(
            f"  {i:>4}  {s['tool']:<22}  {arches_str:>6}  {s['mean']:>6.2f}  {s['wmean']:>7.3f}  "
            f"{passes_str:>5}  {tf('t1'):>5}  {tf('t2'):>5}  {tf('t3'):>5}  {tf('t4'):>5}"
        )

    print()

def print_leaderboard_md(summaries: list[dict]) -> None:
    print(f"\n| Rank | Tool | Arches | Mean | W.Mean | Pass | T1 | T2 | T3 | T4 |")
    print(f"|------|------|--------|------|--------|------|----|----|----|----|")
    for i, s in enumerate(summaries, 1):
        tm = s["tier_means"]
        def tf(tier): return f"{tm[tier]:.1f}" if tier in tm else "—"
        arches_str = f"{s['arches']}/10"
        passes_str = f"{s['passes']}/{s['arches']}"
        print(
            f"| {i} | {s['tool']} | {arches_str} | {s['mean']:.2f} | {s['wmean']:.3f} | "
            f"{passes_str} | {tf('t1')} | {tf('t2')} | {tf('t3')} | {tf('t4')} |"
        )
    print()

def print_breakdown(tool_name: str) -> None:
    tool_dir = RESULTS_DIR / tool_name
    if not tool_dir.exists():
        print(f"[error] tool not found: {tool_name}")
        sys.exit(1)

    arch_results = score_tool_dir(tool_dir)
    if not arch_results:
        print(f"[error] no scored results for {tool_name}")
        sys.exit(1)

    summary = tool_summary(tool_name, arch_results)
    print(f"\nBreakdown: {tool_name}  —  mean {summary['mean']:.2f}  w.mean {summary['wmean']:.3f}  passes {summary['passes']}/{summary['arches']}\n")
    print(f"  {'Arch':<30}  {'Tier':>4}  {'TR':>3}  {'TA':>3}  {'RD':>3}  {'PA':>3}  {'Bonus':>5}  {'Score':>6}  {'Status'}")
    print("  " + "-" * 80)

    for r in sorted(arch_results, key=lambda x: x["_arch_id"]):
        tr = r["tatb"]["threat_relevant"][0]
        ta = r["tatb"]["ttp_accurate"][0]
        rd = r["tatb"]["risk_defensible"][0]
        pa = r["tatb"]["plan_actionable"][0]
        bonus = r["bonus"]["completeness"][0] + r["bonus"]["agentic"][0]
        effective_bonus = min(bonus, 1)
        print(
            f"  {r['_arch_id']:<30}  {r['_tier'].upper():>4}  {tr:>3}  {ta:>3}  {rd:>3}  {pa:>3}  "
            f"  +{effective_bonus}   {r['total']:>4}/13  {r['status']}"
        )
    print()

def print_diff(tool_a: str, tool_b: str) -> None:
    dir_a = RESULTS_DIR / tool_a
    dir_b = RESULTS_DIR / tool_b
    for d, name in [(dir_a, tool_a), (dir_b, tool_b)]:
        if not d.exists():
            print(f"[error] tool not found: {name}")
            sys.exit(1)

    results_a = {r["_arch_id"]: r for r in score_tool_dir(dir_a)}
    results_b = {r["_arch_id"]: r for r in score_tool_dir(dir_b)}
    arches = sorted(set(results_a) | set(results_b))

    print(f"\nDiff: {tool_a}  vs  {tool_b}\n")
    print(f"  {'Arch':<30}  {'Tier':>4}  {'Score A':>7}  {'Score B':>7}  {'Delta':>6}  {'TR':>4}  {'TA':>4}  {'RD':>4}  {'PA':>4}")
    print("  " + "-" * 85)

    for arch in arches:
        ra = results_a.get(arch)
        rb = results_b.get(arch)
        sa = ra["total"] if ra else None
        sb = rb["total"] if rb else None
        delta = (sb - sa) if (sa is not None and sb is not None) else None

        def dim(r, dim_key):
            return str(r["tatb"][dim_key][0]) if r else "—"

        def fmtdelta(d):
            if d is None: return "   —"
            if d > 0: return f"+{d:>3}"
            return f"{d:>4}"

        tier = tier_of(arch).upper()
        print(
            f"  {arch:<30}  {tier:>4}  "
            f"  {(str(sa) if sa is not None else '—'):>5}/13  "
            f"  {(str(sb) if sb is not None else '—'):>5}/13  "
            f"  {fmtdelta(delta):>5}  "
            f"  {dim(ra, 'threat_relevant'):>1}→{dim(rb, 'threat_relevant'):<1}  "
            f"  {dim(ra, 'ttp_accurate'):>1}→{dim(rb, 'ttp_accurate'):<1}  "
            f"  {dim(ra, 'risk_defensible'):>1}→{dim(rb, 'risk_defensible'):<1}  "
            f"  {dim(ra, 'plan_actionable'):>1}→{dim(rb, 'plan_actionable'):<1}"
        )
    print()

def print_list() -> None:
    print(f"\nRegistered tools in {RESULTS_DIR.relative_to(ROOT)}/\n")
    for tool_dir in sorted(RESULTS_DIR.iterdir()):
        if not tool_dir.is_dir():
            continue
        jsons = list(tool_dir.glob("*.json"))
        tiers = set(tier_of(f.stem) for f in jsons)
        tier_str = "  ".join(sorted(tiers)).upper()
        print(f"  {tool_dir.name:<25}  {len(jsons):>3} arches  tiers: {tier_str}")
    print()

# ── ingest ────────────────────────────────────────────────────────────────────

def ingest(tool_name: str, src_dir: Path) -> None:
    if not src_dir.exists():
        print(f"[error] directory not found: {src_dir}")
        sys.exit(1)

    jsons = list(src_dir.glob("*.json"))
    if not jsons:
        print(f"[error] no JSON files found in {src_dir}")
        sys.exit(1)

    dest_dir = RESULTS_DIR / tool_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nIngesting {len(jsons)} file(s) as tool '{tool_name}'...")
    arch_results = []
    errors = 0

    for f in sorted(jsons):
        tm = load_json(f)
        if tm is None:
            errors += 1
            continue

        sv = tm.get("spec_version", "")
        if sv != SPEC_VERSION:
            print(f"  [warn] {f.name}: spec_version '{sv}' != '{SPEC_VERSION}' — scoring anyway")

        arch_id = tm.get("architecture_id") or f.stem
        dest_name = arch_id + ".json"
        dest_path = dest_dir / dest_name

        result = score_tm(tm, arch_id=arch_id)
        result["_arch_id"] = arch_id
        result["_tier"]    = tier_of(arch_id)
        result["_weight"]  = weight_of(arch_id)

        shutil.copy2(f, dest_path)
        status_sym = "PASS" if result["status"] == "PASS" else "FAIL"
        tr = result["tatb"]["threat_relevant"][0]
        ta = result["tatb"]["ttp_accurate"][0]
        rd = result["tatb"]["risk_defensible"][0]
        pa = result["tatb"]["plan_actionable"][0]
        print(f"  {status_sym}  {arch_id:<30}  {result['total']:>2}/13  TR:{tr} TA:{ta} RD:{rd} PA:{pa}")
        arch_results.append(result)

    if errors:
        print(f"\n  {errors} file(s) skipped due to errors.")

    if arch_results:
        summary = tool_summary(tool_name, arch_results)
        print(f"\nIngested: {summary['arches']} arches  mean {summary['mean']:.2f}  w.mean {summary['wmean']:.3f}  passes {summary['passes']}/{summary['arches']}")
        print(f"Stored at: docs/tmbench/results/{tool_name}/\n")

        print("Updated leaderboard:")
        all_summaries = load_all_tools()
        print_leaderboard(all_summaries)

# ── rescore ───────────────────────────────────────────────────────────────────

def rescore(tool_name: str) -> None:
    tool_dir = RESULTS_DIR / tool_name
    if not tool_dir.exists():
        print(f"[error] tool not found: {tool_name}")
        sys.exit(1)
    print(f"\nRe-scoring {tool_name} against spec {SPEC_VERSION}...")
    arch_results = score_tool_dir(tool_dir)
    summary = tool_summary(tool_name, arch_results)
    print(f"  {summary['arches']} arches  mean {summary['mean']:.2f}  w.mean {summary['wmean']:.3f}  passes {summary['passes']}/{summary['arches']}\n")

def rescore_all() -> None:
    print(f"\nRe-scoring all tools against spec {SPEC_VERSION}...\n")
    for tool_dir in sorted(RESULTS_DIR.iterdir()):
        if tool_dir.is_dir() and list(tool_dir.glob("*.json")):
            rescore(tool_dir.name)
    print_leaderboard(load_all_tools())

# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="TMbench leaderboard and submission tool")
    ap.add_argument("--show",        action="store_true",  help="Show leaderboard (default)")
    ap.add_argument("--ingest",      nargs=2,  metavar=("TOOL", "DIR"), help="Ingest tool results from directory")
    ap.add_argument("--rescore",     metavar="TOOL",       help="Re-score stored tool")
    ap.add_argument("--rescore-all", action="store_true",  help="Re-score all tools")
    ap.add_argument("--diff",        nargs=2,  metavar=("TOOL_A", "TOOL_B"), help="Diff two tools per arch")
    ap.add_argument("--breakdown",   metavar="TOOL",       help="Per-arch TATB breakdown")
    ap.add_argument("--export",      choices=["md"],       help="Export format (md)")
    ap.add_argument("--list",        action="store_true",  help="List registered tools")
    args = ap.parse_args()

    if args.ingest:
        ingest(args.ingest[0], Path(args.ingest[1]))
    elif args.rescore:
        rescore(args.rescore)
        print_leaderboard(load_all_tools())
    elif getattr(args, "rescore_all"):
        rescore_all()
    elif args.diff:
        print_diff(args.diff[0], args.diff[1])
    elif args.breakdown:
        print_breakdown(args.breakdown)
    elif args.export == "md":
        print_leaderboard_md(load_all_tools())
    elif args.list:
        print_list()
    else:
        print_leaderboard(load_all_tools())


if __name__ == "__main__":
    main()
