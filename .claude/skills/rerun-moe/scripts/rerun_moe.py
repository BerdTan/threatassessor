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

def _api_url() -> str:
    return os.environ.get("TM_API_BASE_URL", "http://localhost:8000")

def _api_key() -> str:
    key = os.environ.get("TM_API_KEY") or os.environ.get("API_KEY", "")
    if not key:
        # Try loading from .env
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"')
                    break
    return key

def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "TM-API-KEY": _api_key(),
    }

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

# ── Job runner ────────────────────────────────────────────────────────────────

def _submit_job(arch: str) -> str:
    import urllib.request
    url = f"{_api_url()}/api/v1/jobs/expert-review"
    payload = json.dumps({
        "arch_name": arch,
        "critic_mode": "partial_parallel",
    }).encode()
    req = urllib.request.Request(url, data=payload, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["job_id"]


def _poll_job(job_id: str, arch: str, timeout: int = 300) -> dict:
    import urllib.request
    url = f"{_api_url()}/api/v1/jobs/{job_id}/status"
    req = urllib.request.Request(url, headers=_headers())
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(req, timeout=15) as r:
            status = json.loads(r.read())
        if status["status"] == "completed":
            return {"ok": True, "status": status}
        if status["status"] == "failed":
            return {"ok": False, "error": status.get("error", "unknown")}
        time.sleep(8)
    return {"ok": False, "error": f"timeout after {timeout}s"}


def _run_one(arch: str, dry_run: bool = False) -> dict:
    t0 = time.time()
    if dry_run:
        return {"arch": arch, "ok": True, "elapsed": 0, "dry_run": True}
    try:
        job_id = _submit_job(arch)
        result = _poll_job(job_id, arch)
        elapsed = time.time() - t0
        conf = None
        if result["ok"]:
            conf = result["status"].get("result", {}).get("confidence")
        return {"arch": arch, "ok": result["ok"],
                "elapsed": elapsed, "confidence": conf,
                "error": result.get("error")}
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

    mode = "DRY RUN" if args.dry_run else f"FULL_MOE (concurrency={args.concurrency})"
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
            r = _run_one(arch, dry_run=args.dry_run)
            if args.dry_run:
                print(DIM("(dry run)"))
            elif r["ok"]:
                conf_str = f"conf={r['confidence']:.1f}%" if r.get("confidence") else ""
                print(GRN(f"✓ {r['elapsed']:.0f}s {conf_str}"))
            else:
                print(RED(f"✗ {r.get('error', 'failed')}"))
            results.append(r)
    else:
        # Concurrent
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futures = {ex.submit(_run_one, arch, args.dry_run): arch for arch in archs}
            done = 0
            for fut in as_completed(futures):
                arch = futures[fut]
                r = fut.result()
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
