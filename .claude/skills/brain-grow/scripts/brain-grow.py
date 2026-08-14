#!/usr/bin/env python3
"""brain-grow.py — rebuild brain + multi-round synthetic generation to close Brier gaps."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import requests

from chatbot.modules.ta_brain_builder import build_brain, REPORT_DIR
from chatbot.modules.ta_brain_benchmarks import save_calibration
from chatbot.modules.ta_brain_mmd_generator import (
    generate_synthetic_mmds, update_synthetic_status, list_synthetic_queue,
)

# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):  return _c(t, "1")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def grey(t):  return _c(t, "2")
def cyan(t):  return _c(t, "36")

BRIER_THRESHOLD = 0.35
API_BASE = "http://localhost:8000/api/v1"


def _get_api_key() -> str:
    import os
    return os.getenv("API_KEY", "")


def _brier_color(v):
    if v is None: return grey
    if v <= BRIER_THRESHOLD: return green
    if v <= 0.5: return amber
    return red


def _print_state(brain: dict, bench: dict, instances_count: int):
    gaps = brain.get("gaps", [])
    forced = [g for g in gaps if g.get("forced_gap")]
    print(bold("Brain State"))
    print(f"  Instances : {instances_count}")
    print(f"  Patterns  : {len(brain.get('patterns', []))}")
    print(f"  Gaps      : {len(gaps)} total, {len(forced)} forced")
    print(f"  Pattern v : {brain.get('pattern_version', '?')}")
    print()
    brier_scores = bench.get("brier_scores", {})
    if brier_scores:
        print(bold("Brier Scores (hold-out calibration)"))
        for pid, s in brier_scores.items():
            arch_type = s.get("arch_type", "?")
            combined = s.get("brier_combined")
            samples = s.get("samples_used", 0)
            col = _brier_color(combined)
            val = f"{combined:.3f}" if combined is not None else "n/a"
            status = green("✓") if (combined is not None and combined <= BRIER_THRESHOLD) else (red("✗ DIVERGENT") if combined is not None else grey("no data"))
            print(f"  {pid} ({arch_type:12s})  Brier={col(val)}  samples={samples}  {status}")
    print()


def _submit_mmd(arch_name: str, mmd_content: str, api_key: str) -> bool:
    try:
        resp = requests.post(
            f"{API_BASE}/analyze-stream",
            headers={"TM-API-KEY": api_key},
            data={"mmd_text": mmd_content, "mmd_name": arch_name, "include_validation": "true"},
            stream=True,
            timeout=180,
        )
        if resp.status_code != 200:
            print(f"    {red('✗')} HTTP {resp.status_code}")
            return False
        current_event = None
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode()
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and current_event == "complete":
                return True
            elif line.startswith("data:") and current_event == "error":
                try:
                    msg = json.loads(line[5:].strip()).get("message", "")
                except Exception:
                    msg = line[5:50]
                print(f"    {red('✗')} pipeline error: {msg}")
                return False
        return False
    except requests.exceptions.ConnectionError:
        return None  # API not reachable


def main():
    ap = argparse.ArgumentParser(description="TA Brain grow — rebuild + synthetic generation loop")
    ap.add_argument("--rounds", type=int, default=3, help="max generate→ingest→calibrate cycles")
    ap.add_argument("--dry-run", action="store_true", help="show state only, no LLM calls")
    ap.add_argument("--status", action="store_true", help="print current state and exit")
    args = ap.parse_args()

    brain_path = REPORT_DIR / "ta_brain.json"
    bench_path = REPORT_DIR / "ta_brain_benchmarks.json"
    instances_path = REPORT_DIR / "ta_brain_instances.jsonl"

    if not brain_path.exists():
        print(red("ta_brain.json not found — run build_brain first"))
        sys.exit(1)

    brain = json.loads(brain_path.read_text())
    bench = json.loads(bench_path.read_text()) if bench_path.exists() else {}
    instances_count = sum(1 for _ in instances_path.open()) if instances_path.exists() else 0

    _print_state(brain, bench, instances_count)

    if args.status:
        sys.exit(0)

    # Ingest any new corpus archs first
    print(bold("Ingesting new corpus archs..."))
    result = build_brain(incremental=True)
    new_ingested = result.get("ingested", 0)
    print(f"  {green(str(new_ingested))} new instances ingested  (total: {result['total_instances']})")
    print()

    if args.dry_run:
        gaps = brain.get("gaps", [])
        forced = [g for g in gaps if g.get("forced_gap")]
        print(bold("Dry run — gaps that would be generated:"))
        for g in forced:
            print(f"  {amber(g['id'])}  {g['region']}  Brier={g.get('confidence_floor', '?'):.3f}")
            print(f"    {grey(g.get('generation_prompt','')[:100])}")
        print()
        print(grey("Use without --dry-run to run the full generation loop."))
        sys.exit(0)

    api_key = _get_api_key()
    api_ok = True

    # Brier baseline
    cal = save_calibration()
    brier_baseline = {
        s["arch_type"]: s.get("brier_combined")
        for s in (json.loads(bench_path.read_text()) if bench_path.exists() else {}).get("brier_scores", {}).values()
        if s.get("brier_combined") is not None
    }

    total_synthetics = 0

    for rnd in range(1, args.rounds + 1):
        brain = json.loads(brain_path.read_text())
        forced_gaps = [g for g in brain.get("gaps", []) if g.get("forced_gap")]
        if not forced_gaps:
            print(green(f"All gaps resolved after round {rnd - 1}. Done."))
            break

        print(bold(f"Round {rnd}/{args.rounds}"))

        # Generate
        staged = generate_synthetic_mmds(max_per_run=2)
        if not staged:
            print(f"  {amber('No new MMDs generated')} (gaps may already be staged)")
        else:
            for s in staged:
                print(f"  Generated: {cyan(s['gen_id'])} ({s['arch_type']})")

        # Auto-approve + submit
        queue = list_synthetic_queue()
        approved_items = [q for q in queue if q["status"] == "approved" or q["status"] == "staged"]
        for item in queue:
            if item["status"] == "staged":
                update_synthetic_status(item["gen_id"], "approved")

        queue = list_synthetic_queue()
        submitted = []
        queue_dir = REPORT_DIR / "brain_synthetic_queue"
        for item in queue:
            if item["status"] != "approved":
                continue
            mmd_path = queue_dir / item["mmd_file"]
            if not mmd_path.exists():
                continue
            gap_short = item["gap_id"].replace("-", "").lower()
            arch_name = f"syn_{item['arch_type']}_r{rnd}_{gap_short}"
            mmd_content = mmd_path.read_text()
            print(f"  Submitting {arch_name}...", end=" ", flush=True)
            ok = _submit_mmd(arch_name, mmd_content, api_key)
            if ok is None:
                print(amber("⚠ API unreachable — skipping submission"))
                api_ok = False
                break
            elif ok:
                print(green("✓"))
                submitted.append(item["gen_id"])
            else:
                print(red("✗"))

        total_synthetics += len(submitted)

        if not api_ok:
            print(amber("  API not reachable — skipping ingest/calibrate for this round"))
            break

        # Ingest + calibrate
        build_brain(incremental=True)
        save_calibration()

        # Mark ingested
        for gen_id in submitted:
            try:
                update_synthetic_status(gen_id, "ingested")
            except FileNotFoundError:
                pass

        # Brier delta
        new_bench = json.loads(bench_path.read_text()) if bench_path.exists() else {}
        print(f"  Brier delta:")
        for pid, s in new_bench.get("brier_scores", {}).items():
            arch_type = s.get("arch_type", "?")
            new_val = s.get("brier_combined")
            old_val = brier_baseline.get(arch_type)
            if new_val is None:
                continue
            col = _brier_color(new_val)
            if old_val is not None:
                delta = new_val - old_val
                arrow = green("↓") if delta < -0.005 else (red("↑") if delta > 0.005 else grey("→"))
                print(f"    {arch_type:12s}  {old_val:.3f} → {col(f'{new_val:.3f}')}  {arrow} ({delta:+.3f})")
            else:
                print(f"    {arch_type:12s}  {col(f'{new_val:.3f}')}")
            brier_baseline[arch_type] = new_val

        remaining_forced = [g for g in json.loads(brain_path.read_text()).get("gaps", []) if g.get("forced_gap")]
        print(f"  Gaps remaining: {len(remaining_forced)} forced")
        print()

    # Final summary
    brain_final = json.loads(brain_path.read_text())
    bench_final = json.loads(bench_path.read_text()) if bench_path.exists() else {}
    instances_final = sum(1 for _ in instances_path.open()) if instances_path.exists() else 0
    print(bold("─" * 50))
    print(bold("Final Brain State"))
    _print_state(brain_final, bench_final, instances_final)
    print(f"  Total synthetics generated this run: {bold(str(total_synthetics))}")
    forced_remaining = [g for g in brain_final.get("gaps", []) if g.get("forced_gap")]
    if forced_remaining:
        print(amber(f"  {len(forced_remaining)} forced gap(s) remain — run again to continue narrowing"))
    else:
        print(green("  All forced gaps resolved ✓"))


if __name__ == "__main__":
    main()
