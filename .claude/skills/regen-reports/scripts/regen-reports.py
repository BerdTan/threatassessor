#!/usr/bin/env python3
"""
regen-reports — Regenerate report MD/MMD files from existing JSON data.

Regenerates all report files for one or all corpus architectures without
re-running the analysis engine or Expert Review. Use after changes to
any report generator module (threat_report.py, improvement_summary_generator.py,
executive_dashboard_generator.py, adr_generator.py, narrative_enricher.py).

Usage:
    python3 regen-reports.py 21_agentic_ai_system
    python3 regen-reports.py --all
    python3 regen-reports.py 21_agentic_ai_system --md-only
    python3 regen-reports.py 21_agentic_ai_system --dashboard-only
    python3 regen-reports.py 21_agentic_ai_system --improvement-only
    python3 regen-reports.py --all --dry-run
"""

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[4]
REPORT_DIR = REPO_ROOT / "report"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def regen_arch(arch: str, opts: argparse.Namespace) -> dict:
    """
    Regenerate report files for a single architecture.
    Returns: {ok: int, skipped: int, failed: int, details: list[str]}
    """
    arch_dir = REPORT_DIR / arch
    gt_path  = arch_dir / "ground_truth.json"

    if not gt_path.exists():
        return {"ok": 0, "skipped": 0, "failed": 0,
                "details": [DIM(f"  –  SKIP: no ground_truth.json in {arch}")]}

    result = {"ok": 0, "skipped": 0, "failed": 0, "details": []}

    def _write(rel_name: str, content: str, fmt: str = "md"):
        path = arch_dir / rel_name
        if opts.dry_run:
            result["details"].append(DIM(f"  ~  {rel_name}  (dry-run)"))
            result["ok"] += 1
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            result["details"].append(GREEN(f"  ✓  {rel_name}"))
            result["ok"] += 1
        except Exception as e:
            result["details"].append(RED(f"  ✗  {rel_name}  [{e}]"))
            result["failed"] += 1

    def _skip(rel_name: str, reason: str):
        result["details"].append(DIM(f"  –  {rel_name}  [{reason}]"))
        result["skipped"] += 1

    # ── Load data ─────────────────────────────────────────────────────────────
    sys.path.insert(0, str(REPO_ROOT))
    gt = _load_json(gt_path)
    moe = _load_json(arch_dir / "07_moe_orchestrator.json")
    has_moe = bool(moe)

    do_md          = not (opts.dashboard_only or opts.improvement_only)
    do_dashboard   = not (opts.md_only or opts.improvement_only)
    do_improvement = not (opts.md_only or opts.dashboard_only)

    # ── MD reports (01–03, 09, 10) ────────────────────────────────────────────
    if do_md:
        try:
            from chatbot.modules.threat_report import (
                generate_executive_summary,
                generate_technical_report,
                generate_action_plan,
                generate_threat_model_report,
                generate_adr_report,
                generate_before_after_diagrams,
                generate_final_diagram,
                _append_bh_subgraphs,
            )
            from chatbot.config.settings import get_settings
            settings = get_settings()

            # Run enrichment pipeline if data is missing (non-destructive)
            try:
                if settings.adr.enabled and "architecture_decision_records" not in gt:
                    from chatbot.modules.adr_generator import generate_adrs_from_ground_truth
                    generate_adrs_from_ground_truth(gt)
                if settings.narratives.enabled and not gt.get("threat_model"):
                    from chatbot.modules.narrative_enricher import enrich_ground_truth
                    enrich_ground_truth(gt)
                try:
                    from chatbot.modules.threat_scene_deepener import deepen_threat_scenes
                    from chatbot.modules.mitre import get_mitre_helper
                    deepen_threat_scenes(gt, get_mitre_helper())
                except Exception:
                    pass
                if settings.threat_model.enabled and not gt.get("threat_model"):
                    from chatbot.modules.threat_model_builder import build_threat_model
                    build_threat_model(gt)
            except Exception as enrich_exc:
                result["details"].append(DIM(f"  ~  enrichment partial: {enrich_exc}"))

            # Locate original MMD for diagram generation
            mmd_candidates = [
                REPO_ROOT / "tests" / "data" / "architectures" / f"{arch}.mmd",
                arch_dir / "before.mmd",
            ]
            orig_mmd = next((str(p) for p in mmd_candidates if p.exists()), str(arch_dir / "before.mmd"))

            _write("01_executive_summary.md", generate_executive_summary(gt))
            _write("02_technical_report.md",  generate_technical_report(gt))
            _write("03_action_plan.md",        generate_action_plan(gt))

            if settings.threat_model.enabled and gt.get("threat_model"):
                _write("09_threat_model.md", generate_threat_model_report(gt))
            else:
                _skip("09_threat_model.md", "no threat_model data")

            if settings.adr.enabled and gt.get("architecture_decision_records"):
                _write("10_adr_report.md", generate_adr_report(gt))
            else:
                _skip("10_adr_report.md", "no architecture_decision_records")

            before_mmd, after_mmd = generate_before_after_diagrams(orig_mmd, gt)
            _write("before.mmd", before_mmd, "mmd")
            _write("after.mmd",  after_mmd,  "mmd")

            if settings.threat_model.enabled and gt.get("architecture_decision_records"):
                final_mmd = generate_final_diagram(gt)
                _write("threatmodel_adr.mmd", final_mmd, "mmd")
                if gt.get("blackhat_critique"):
                    bh_mmd = _append_bh_subgraphs(final_mmd, gt["blackhat_critique"])
                    _write("threatmodel_adr_bh.mmd", bh_mmd, "mmd")
                else:
                    _skip("threatmodel_adr_bh.mmd", "no blackhat_critique")
            else:
                _skip("threatmodel_adr.mmd", "no ADR data")

        except Exception as e:
            result["details"].append(RED(f"  ✗  MD reports failed: {e}"))
            result["failed"] += 1

    # ── Executive dashboard (00) ───────────────────────────────────────────────
    if do_dashboard:
        if has_moe:
            try:
                from chatbot.modules.executive_dashboard_generator import generate_executive_dashboard
                if not opts.dry_run:
                    out = generate_executive_dashboard(str(arch_dir))
                    result["details"].append(GREEN(f"  ✓  00_executive_dashboard.md"))
                else:
                    result["details"].append(DIM(f"  ~  00_executive_dashboard.md  (dry-run)"))
                result["ok"] += 1
            except Exception as e:
                result["details"].append(RED(f"  ✗  00_executive_dashboard.md: {e}"))
                result["failed"] += 1
        else:
            _skip("00_executive_dashboard.md", "no 07_moe_orchestrator.json")

    # ── Improvement summary + MMDs (08) ───────────────────────────────────────
    if do_improvement:
        if has_moe:
            try:
                from chatbot.modules.improvement_summary_generator import generate_summary
                if not opts.dry_run:
                    generate_summary(str(arch_dir), orchestrator_result=None)
                    result["details"].append(GREEN(f"  ✓  08_improvement_summary.md"))
                else:
                    result["details"].append(DIM(f"  ~  08_improvement_summary.md  (dry-run)"))
                result["ok"] += 1
            except Exception as e:
                result["details"].append(RED(f"  ✗  08_improvement_summary.md: {e}"))
                result["failed"] += 1

            try:
                from chatbot.modules.mmd_improvement_generator import generate_improvement_mmds
                if not opts.dry_run:
                    generated = generate_improvement_mmds(str(arch_dir), orchestrator_result=moe)
                    for g in generated:
                        result["details"].append(GREEN(f"  ✓  {Path(g).name}"))
                        result["ok"] += 1
                else:
                    result["details"].append(DIM(f"  ~  08a/b/c_*.mmd  (dry-run)"))
                    result["ok"] += 1
            except Exception as e:
                result["details"].append(AMBER(f"  ~  08a/b/c_*.mmd skipped: {e}"))
                result["skipped"] += 1
        else:
            _skip("08_improvement_summary.md", "no 07_moe_orchestrator.json")
            _skip("08a/b/c_*.mmd",             "no 07_moe_orchestrator.json")

    return result


def main():
    parser = argparse.ArgumentParser(description="Regenerate report files from existing JSON data")
    parser.add_argument("arch", nargs="?", help="Architecture name (directory under report/)")
    parser.add_argument("--all",             action="store_true", help="Process all architectures")
    parser.add_argument("--md-only",         action="store_true", help="Regenerate MD + diagrams only (01–03, 09, 10)")
    parser.add_argument("--dashboard-only",  action="store_true", help="Regenerate 00_executive_dashboard.md only")
    parser.add_argument("--improvement-only",action="store_true", help="Regenerate 08_improvement_summary + MMDs only")
    parser.add_argument("--dry-run",         action="store_true", help="Show what would be written without writing")
    args = parser.parse_args()

    if not args.arch and not args.all:
        parser.print_help()
        sys.exit(1)

    if args.arch and args.all:
        print(RED("Pass either an arch name or --all, not both."))
        sys.exit(1)

    # Collect targets
    if args.all:
        targets = sorted(
            d.name for d in REPORT_DIR.iterdir()
            if d.is_dir() and (d / "ground_truth.json").exists()
        )
        if not targets:
            print(RED(f"No report directories with ground_truth.json found under {REPORT_DIR}"))
            sys.exit(1)
    else:
        targets = [args.arch]
        if not (REPORT_DIR / args.arch).exists():
            print(RED(f"Architecture '{args.arch}' not found under {REPORT_DIR}"))
            sys.exit(1)

    mode_tag = ""
    if args.md_only:         mode_tag = " [MD only]"
    elif args.dashboard_only: mode_tag = " [dashboard only]"
    elif args.improvement_only: mode_tag = " [improvement only]"
    elif args.dry_run:        mode_tag = " [dry-run]"

    total_ok = total_skip = total_fail = 0
    t0 = time.time()

    for arch in targets:
        print(f"\n{BOLD(CYAN('Regen Reports'))} — {arch}{mode_tag}")
        r = regen_arch(arch, args)
        for line in r["details"]:
            print(line)
        total_ok   += r["ok"]
        total_skip += r["skipped"]
        total_fail += r["failed"]

    elapsed = time.time() - t0
    summary = f"\n  Done: {GREEN(str(total_ok))} regenerated"
    if total_skip: summary += f" · {DIM(str(total_skip))} skipped"
    if total_fail: summary += f" · {RED(str(total_fail))} failed"
    summary += f"  ({elapsed:.1f}s)"
    print(summary)

    if total_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
