#!/usr/bin/env python3
"""
backfill-aivss.py — Generate/refresh governance_signals.json + AIVSS scores for
existing report directories that are missing them.

Usage:
    python3 backfill-aivss.py                    # all reports in report/
    python3 backfill-aivss.py 00_serviceentry    # one arch by directory name
    python3 backfill-aivss.py path/to/arch.mmd   # run full analysis on an MMD file first
    python3 backfill-aivss.py --force            # re-score even if governance_signals.json exists

When a directory name is given: reads existing ground_truth.json (no re-analysis).
When an MMD path is given: runs AnalysisStage + ReportStage first, then scores.
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


def _col(text, code):
    return f"\033[{code}m{text}\033[0m"

def green(t):  return _col(t, "32")
def yellow(t): return _col(t, "33")
def red(t):    return _col(t, "31")
def cyan(t):   return _col(t, "36")
def bold(t):   return _col(t, "1")


def _sev_color(s):
    if not s: return "—"
    c = {"CRITICAL": red, "HIGH": yellow, "MEDIUM": yellow, "LOW": green}.get(s, str)
    return c(s)


def _aivss_str(composite, severity):
    if composite is None:
        return "—"
    return f"{composite:.1f} {_sev_color(severity)}"


def score_directory(report_dir: Path, force: bool = False) -> dict:
    """
    Load ground_truth + any available MoE/SM results, run QualityStage, return summary.
    Returns dict with keys: name, status, dims, aivss_inbound, aivss_internal,
    aivss_outbound, aivss_overall, used_moe, used_sm, error
    """
    from chatbot.harness.controller import PipelineContext, HarnessModelGuardian
    from chatbot.harness.stages import QualityStage

    name = report_dir.name
    result = {
        "name": name, "status": "skip", "error": None,
        "dims": {}, "aivss_inbound": None, "aivss_internal": None,
        "aivss_outbound": None, "aivss_overall": None,
        "used_moe": False, "used_sm": False,
    }

    gt_path  = report_dir / "ground_truth.json"
    mmd_path = report_dir / "before.mmd"

    if not gt_path.exists():
        result["status"] = "skip"
        result["error"] = "no ground_truth.json"
        return result

    gov_path = report_dir / "governance_signals.json"
    if gov_path.exists() and not force:
        # Check if AIVSS is already populated
        try:
            gs = json.loads(gov_path.read_text())
            existing_overall = (gs.get("aivss") or {}).get("overall") or {}
            if existing_overall.get("composite") is not None:
                result["status"] = "already_scored"
                _fill_result_from_gs(result, gs)
                return result
        except Exception:
            pass  # re-score if file is corrupt

    try:
        gt = json.loads(gt_path.read_text())
        mmd = mmd_path.read_text() if mmd_path.exists() else ""

        ctx = PipelineContext({
            "_raw_mmd_content": mmd,
            "architecture_path": str(mmd_path) if mmd_path.exists() else str(gt_path),
            "architecture_name": name,
            "ground_truth": gt,
            "report_dir": str(report_dir),
            "_model_guardian": HarnessModelGuardian(),
        })

        # Load MoE result if available — passes to AIVSS internal flow scorer
        moe_path = report_dir / "07_moe_orchestrator.json"
        if moe_path.exists():
            try:
                ctx["moe_result"] = json.loads(moe_path.read_text())
                result["used_moe"] = True
            except Exception:
                pass

        # Load SM result if available — sm_result.retrigger_count affects internal score
        sm_path = report_dir / "08_scrum_master.json"
        if sm_path.exists():
            try:
                sm_data = json.loads(sm_path.read_text())
                # Wrap as a simple namespace so getattr works
                class _SMProxy:
                    def __init__(self, d):
                        self.retrigger_count = d.get("iterations_run", 0)
                        self.redesign_signal = d.get("redesign_signal", False)
                ctx["scrum_master_result"] = _SMProxy(sm_data)
                result["used_sm"] = True
            except Exception:
                pass

        QualityStage()._logic(ctx)

        gs = ctx.get("governance_signals", {})
        _fill_result_from_gs(result, gs)
        result["status"] = "scored"

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        result["_tb"] = traceback.format_exc()

    return result


def _fill_result_from_gs(result, gs):
    aivss = gs.get("aivss") or {}
    result["dims"] = {
        "D1": (gs.get("exploitation") or {}).get("severity"),
        "D2": (gs.get("manipulation") or {}).get("severity"),
        "D3": (gs.get("leakage") or {}).get("severity"),
        "D4": (gs.get("identity") or {}).get("severity"),
        "D5": (gs.get("sovereignty") or {}).get("severity"),
    }
    result["aivss_inbound"]  = (aivss.get("inbound")  or {}).get("composite")
    result["aivss_internal"] = (aivss.get("internal") or {}).get("composite")
    result["aivss_outbound"] = (aivss.get("outbound") or {}).get("composite")
    overall = aivss.get("overall") or {}
    result["aivss_overall"]  = overall.get("composite")
    result["aivss_severity"] = overall.get("severity")


def run_full_analysis(mmd_path: Path, force: bool = False) -> Path:
    """
    Run AnalysisStage + ReportStage + QualityStage on an MMD file.
    Returns the report_dir Path.
    """
    from chatbot.harness.controller import ThreatAssessorHarness, ScenarioConfig

    base_name = mmd_path.stem.replace(".", "_").replace(" ", "_")
    report_base = REPO_ROOT / "report"
    arch_name = base_name
    counter = 1
    while (report_base / arch_name).exists() and not force:
        arch_name = f"{base_name}_{counter}"
        counter += 1

    report_dir = report_base / arch_name
    print(f"  Running full analysis → {cyan(arch_name)}")

    harness = ThreatAssessorHarness(scenario=ScenarioConfig.API_ONLY)
    harness.run(
        architecture_path=str(mmd_path),
        report_dir=str(report_dir),
        architecture_name=arch_name,
        include_validation=True,
    )
    return report_dir


def print_result(r, verbose=False):
    name = r["name"]
    status = r["status"]
    error = r.get("error", "")

    if status == "skip":
        print(f"  {yellow('SKIP')}  {name:45} {error}")
        return
    if status == "error":
        print(f"  {red('ERR ')}  {name:45} {error}")
        if verbose and r.get("_tb"):
            print(r["_tb"])
        return
    if status == "already_scored":
        tag = cyan("OK  ")
    else:
        tag = green("NEW ")

    dims = r.get("dims", {})
    dim_str = " ".join(
        f"{k}:{_sev_color(v) if v else '—'}"
        for k, v in dims.items() if v
    ) or "all clear"

    moe_tag = f" {cyan('[MoE]')}" if r.get("used_moe") else ""
    sm_tag  = f" {cyan('[SM]')}"  if r.get("used_sm")  else ""

    aivss_parts = []
    if r["aivss_inbound"]  is not None: aivss_parts.append(f"in:{r['aivss_inbound']:.1f}")
    if r["aivss_internal"] is not None: aivss_parts.append(f"int:{r['aivss_internal']:.1f}")
    if r["aivss_outbound"] is not None: aivss_parts.append(f"out:{r['aivss_outbound']:.1f}")
    aivss_str = "  AIVSS " + " ".join(aivss_parts) if aivss_parts else ""

    overall = f"  overall:{_aivss_str(r.get('aivss_overall'), r.get('aivss_severity'))}" if r.get("aivss_overall") is not None else ""

    print(f"  {tag}  {name:45} {dim_str}{moe_tag}{sm_tag}{aivss_str}{overall}")


def main():
    parser = argparse.ArgumentParser(description="Backfill AIVSS scores for existing report directories.")
    parser.add_argument("target", nargs="?", default=None,
                        help="Architecture directory name, path to .mmd file, or omit for all reports")
    parser.add_argument("--force", action="store_true",
                        help="Re-score even if governance_signals.json already has AIVSS data")
    parser.add_argument("--verbose", action="store_true",
                        help="Print full tracebacks on errors")
    args = parser.parse_args()

    report_base = REPO_ROOT / "report"

    print(bold("\n=== AIVSS Backfill ===\n"))

    # ── Mode 1: single MMD file ───────────────────────────────────────────────
    if args.target and args.target.endswith(".mmd"):
        mmd_path = Path(args.target)
        if not mmd_path.is_absolute():
            mmd_path = Path.cwd() / mmd_path
        if not mmd_path.exists():
            print(red(f"File not found: {mmd_path}"))
            sys.exit(1)
        print(f"Mode: {bold('Single MMD')} — {mmd_path.name}\n")
        report_dir = run_full_analysis(mmd_path, force=args.force)
        r = score_directory(report_dir, force=True)
        print_result(r, verbose=args.verbose)
        print()
        return

    # ── Mode 2: single arch by directory name ────────────────────────────────
    if args.target:
        arch_dir = report_base / args.target
        if not arch_dir.is_dir():
            # Try as a relative path
            arch_dir = Path(args.target)
        if not arch_dir.is_dir():
            print(red(f"Directory not found: {args.target}"))
            sys.exit(1)
        print(f"Mode: {bold('Single arch')} — {arch_dir.name}\n")
        r = score_directory(arch_dir, force=args.force)
        print_result(r, verbose=args.verbose)
        print()
        _print_summary([r])
        return

    # ── Mode 3: all reports ───────────────────────────────────────────────────
    dirs = sorted([d for d in report_base.iterdir() if d.is_dir() and not d.name.startswith(".")])
    # Skip dirs with no ground_truth
    candidates = [d for d in dirs if (d / "ground_truth.json").exists()]

    print(f"Mode: {bold('All reports')} — {len(candidates)} directories\n")

    results = []
    for d in candidates:
        r = score_directory(d, force=args.force)
        print_result(r, verbose=args.verbose)
        results.append(r)

    print()
    _print_summary(results)


def _print_summary(results):
    scored  = [r for r in results if r["status"] == "scored"]
    already = [r for r in results if r["status"] == "already_scored"]
    skipped = [r for r in results if r["status"] == "skip"]
    errors  = [r for r in results if r["status"] == "error"]
    used_moe = [r for r in scored if r.get("used_moe")]
    used_sm  = [r for r in scored if r.get("used_sm")]

    print(bold("Summary"))
    print(f"  {green(str(len(scored)))} newly scored   "
          f"  {cyan(str(len(already)))} already had AIVSS   "
          f"  {yellow(str(len(skipped)))} skipped   "
          f"  {red(str(len(errors)))} errors")
    if used_moe:
        print(f"  {cyan(str(len(used_moe)))} used MoE data for richer internal flow score")
    if used_sm:
        print(f"  {cyan(str(len(used_sm)))} used ScrumMaster retrigger count")
    if errors:
        print(f"\n  {red('Errors:')} " + ", ".join(r["name"] for r in errors))
    print(f"\n  {bold('Insights /api/v1/insights/all')} will now return AIVSS data for all scored architectures.")
    print()


if __name__ == "__main__":
    main()
