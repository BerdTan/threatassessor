#!/usr/bin/env python3
"""
rerun-moe — Batch FULL_MOE expert review runner.

Submits expert review jobs to the REST API for all or selected corpus
architectures and polls each to completion.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR = ROOT / "report"

# Critic files written by the MoE orchestrator — cleared before rerun so the
# orchestrator doesn't load cached results and skip LLM calls.
CRITIC_FILES_TO_CLEAR = [
    "04_architect_critique.json",
    "05_tester_critique.json",
    "06_red_team_critique.json",
    "06b_purple_team_critique.json",
    "06c_blackhat_critique.json",
    "07_moe_orchestrator.json",
    "07_orchestrator_report.json",
    "08_scrum_master.json",
]

# ── Terminal helpers ──────────────────────────────────────────────────────────

def _c(code, text): return f"\033[{code}m{text}\033[0m"
BOLD  = lambda t: _c("1", t)
RED   = lambda t: _c("31", t)
GRN   = lambda t: _c("32", t)
YLW   = lambda t: _c("33", t)
CYAN  = lambda t: _c("36", t)
DIM   = lambda t: _c("2", t)

# ── Config ────────────────────────────────────────────────────────────────────

AI_ARCH_TYPES = {"ai_system", "rag_system", "llm_agent", "agentic"}

# ── Arch discovery ────────────────────────────────────────────────────────────

def _all_archs() -> list:
    return sorted(p.name for p in REPORT_DIR.iterdir() if p.is_dir())

def _arch_type(arch: str) -> str:
    gt = REPORT_DIR / arch / "ground_truth.json"
    if not gt.exists():
        return "unknown"
    try:
        d = json.loads(gt.read_text())
        return d.get("metadata", {}).get("architecture_type", "unknown")
    except Exception:
        return "unknown"

def _ai_archs() -> list:
    return [a for a in _all_archs() if _arch_type(a) in AI_ARCH_TYPES]

# ── Runner ───────────────────────────────────────────────────────────────────

def _clear_critic_files(arch: str) -> int:
    """Delete existing critic JSON files so orchestrator runs fresh LLM calls."""
    arch_dir = REPORT_DIR / arch
    deleted = 0
    for fname in CRITIC_FILES_TO_CLEAR:
        p = arch_dir / fname
        if p.exists():
            p.unlink()
            deleted += 1
    return deleted


def _run_one(arch: str, dry_run: bool = False, force: bool = True) -> dict:
    """Run FULL_MOE for one arch by calling the harness directly in-process.

    Uses ThreatAssessorHarness.run_typed() directly — same path as the
    streaming endpoint. Avoids the async job API which doesn't reliably
    flush critic files before reporting completion.
    """
    t0 = time.time()
    if dry_run:
        existing = sum(1 for f in CRITIC_FILES_TO_CLEAR if (REPORT_DIR / arch / f).exists())
        return {"arch": arch, "ok": True, "elapsed": 0, "dry_run": True, "would_clear": existing}
    try:
        if force:
            _clear_critic_files(arch)

        sys.path.insert(0, str(ROOT))
        from chatbot.harness.controller import (
            ThreatAssessorHarness, PipelineRequest, ScenarioConfig
        )

        report_dir = REPORT_DIR / arch
        mmd_path = report_dir / "before.mmd"
        if not mmd_path.exists():
            mmd_path = report_dir / f"{arch}.mmd"
        if not mmd_path.exists():
            return {"arch": arch, "ok": False, "elapsed": time.time() - t0,
                    "error": "no .mmd file found in report dir"}

        ssp_profile = "low_risk_cloud"
        gt_path = report_dir / "ground_truth.json"
        if gt_path.exists():
            gt = json.loads(gt_path.read_text())
            ssp_profile = (gt.get("ssp_profile")
                           or gt.get("metadata", {}).get("ssp_profile")
                           or ssp_profile)

        request = PipelineRequest(
            architecture_path=str(mmd_path),
            report_dir=str(report_dir),
            ssp_profile=ssp_profile,
            enable_ssp=True,
            enable_moe=True,
            enable_scrum_master=True,
            critic_mode="parallel",
            architecture_name=arch,
        )

        harness = ThreatAssessorHarness(scenario=ScenarioConfig.FULL_MOE)
        response = harness.run_typed(request)

        elapsed = time.time() - t0
        ok = bool(response and response.success)
        conf = response.confidence if response else None
        return {"arch": arch, "ok": ok, "elapsed": elapsed, "confidence": conf,
                "error": None if ok else "harness returned failure"}

    except Exception as exc:
        return {"arch": arch, "ok": False, "elapsed": time.time() - t0, "error": str(exc)}


# ── TATB summary ──────────────────────────────────────────────────────────────

def _tatb_summary(archs: list):
    tatb_script = ROOT / ".claude/skills/tatb-corpus/scripts/tatb-corpus.py"
    if not tatb_script.exists():
        print(DIM("  /tatb-corpus script not found — run manually to see corpus delta"))
        return
    import subprocess
    print(f"\n{BOLD('── TATB corpus summary (post-rerun) ─────────────────')}")
    r = subprocess.run(
        [sys.executable, str(tatb_script)],
        capture_output=True, text=True, timeout=120, cwd=str(ROOT),
    )
    if r.returncode == 0:
        # Print last 20 lines — the summary table
        lines = r.stdout.strip().splitlines()
        for line in lines[-20:]:
            print(line)
    else:
        print(YLW("  tatb-corpus failed — run /tatb-corpus manually"))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch FULL_MOE rerun across corpus")
    parser.add_argument("--all",         action="store_true", help="Rerun all corpus archs")
    parser.add_argument("--ai-only",     action="store_true", help="Rerun AI/agentic archs only")
    parser.add_argument("--arch",        default=None, help="Comma-separated arch name(s)")
    parser.add_argument("--concurrency", type=int, default=1,
                        help="Concurrent jobs (default 1 — sequential)")
    parser.add_argument("--dry-run",     action="store_true", help="Show what would run, no API calls")
    parser.add_argument("--no-force",    action="store_true", help="Skip clearing cached critic files (use orchestrator resume)")
    parser.add_argument("--tatb",        action="store_true", help="Run tatb-corpus after completion")
    args = parser.parse_args()

    # Resolve arch list
    if args.arch:
        archs = [a.strip() for a in args.arch.split(",") if a.strip()]
    elif args.ai_only:
        archs = _ai_archs()
        print(f"AI/agentic archs: {archs}")
    elif args.all:
        archs = _all_archs()
    else:
        print(BOLD("── Corpus overview ──────────────────────────────────"))
        all_a = _all_archs()
        ai_a  = _ai_archs()
        print(f"  Total archs : {len(all_a)}")
        print(f"  AI/agentic  : {len(ai_a)}")
        print(f"\n  Usage:")
        print(f"    {DIM('python3 rerun_moe.py --all')}")
        print(f"    {DIM('python3 rerun_moe.py --ai-only')}")
        print(f"    {DIM('python3 rerun_moe.py --arch 01_minimal_vulnerable,10_complex_enterprise')}")
        print(f"    {DIM('python3 rerun_moe.py --all --concurrency 3')}")
        print(f"    {DIM('python3 rerun_moe.py --dry-run --all')}")
        return

    if not archs:
        print(YLW("No architectures found."))
        return

    force = not args.no_force
    mode = "DRY RUN" if args.dry_run else f"FULL_MOE (concurrency={args.concurrency}, force={'yes' if force else 'no'})"
    print(f"\n{BOLD('── rerun-moe ─────────────────────────────────────────')}")
    print(f"  Mode    : {CYAN(mode)}")
    print(f"  Archs   : {len(archs)}")
    est = len(archs) * 90 / max(args.concurrency, 1)
    if not args.dry_run:
        print(f"  Est time: ~{int(est//60)}m {int(est%60)}s")
    print()

    results = []

    if args.concurrency == 1:
        # Sequential — shows live progress
        for i, arch in enumerate(archs, 1):
            prefix = f"  [{i:02d}/{len(archs):02d}]"
            print(f"{prefix} {arch:<40} ", end="", flush=True)
            r = _run_one(arch, dry_run=args.dry_run, force=force)
            if args.dry_run:
                print(DIM(f"(dry run — would clear {r.get('would_clear',0)} critic files)"))
            elif r["ok"]:
                conf_str = f"conf={r['confidence']:.1f}%" if r.get("confidence") else ""
                print(GRN(f"✓ {r['elapsed']:.0f}s {conf_str}"))
            else:
                print(RED(f"✗ {r.get('error', 'failed')}"))
            results.append(r)
    else:
        # Concurrent
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futures = {ex.submit(_run_one, arch, args.dry_run, force): arch for arch in archs}
            done = 0
            for fut in as_completed(futures):
                arch = futures[fut]
                r = fut.result()  # already has force baked in from the lambda below
                done += 1
                if r["ok"]:
                    conf_str = f"conf={r['confidence']:.1f}%" if r.get("confidence") else ""
                    print(f"  [{done:02d}/{len(archs):02d}] {GRN('✓')} {arch:<38} {r['elapsed']:.0f}s {conf_str}")
                else:
                    print(f"  [{done:02d}/{len(archs):02d}] {RED('✗')} {arch:<38} {r.get('error','failed')}")
                results.append(r)

    # Summary
    passed = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    total_time = sum(r["elapsed"] for r in results)

    print(f"\n{BOLD('── Summary ───────────────────────────────────────────')}")
    print(f"  {GRN(f'✓ {len(passed)} passed')}  {RED(f'✗ {len(failed)} failed')}  "
          f"total={total_time:.0f}s ({total_time/60:.1f}m)")

    if failed:
        print(f"\n{RED('Failed archs:')}")
        for r in failed:
            print(f"  {r['arch']}: {r.get('error', 'unknown')}")

    if args.tatb and not args.dry_run and passed:
        _tatb_summary([r["arch"] for r in passed])


if __name__ == "__main__":
    main()
