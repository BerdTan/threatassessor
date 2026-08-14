#!/usr/bin/env python3
"""brain-cache.py — cache inspection and management for TA Brain."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from chatbot.modules.ta_brain_cache import get_cache_manager, CACHE_PATH
from chatbot.modules.ta_brain_builder import REPORT_DIR

# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):  return _c(t, "1")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def grey(t):  return _c(t, "2")
def cyan(t):  return _c(t, "36")


def _print_stats(cm):
    brain_path = REPORT_DIR / "ta_brain.json"
    current_pv = None
    if brain_path.exists():
        try:
            current_pv = json.loads(brain_path.read_text()).get("pattern_version")
        except Exception:
            pass

    stats = cm.stats()
    total = stats.get("total", 0)
    hits = stats.get("total_hits", 0)
    confirmed = stats.get("confirmed_entries", 0)
    pv_dist = stats.get("pattern_versions", {})
    arch_dist = stats.get("arch_types", {})

    stale = sum(c for pv, c in pv_dist.items() if current_pv is not None and int(pv) < current_pv)

    print(bold("Cache Stats"))
    print(f"  Total entries     : {total}")
    print(f"  Total hits        : {hits}")
    print(f"  Confirmed entries : {confirmed}")
    print(f"  Current pv        : {current_pv}")
    stale_col = red(str(stale)) if stale > 0 else green("0")
    print(f"  Stale entries     : {stale_col}  (pattern_version < {current_pv})")
    print()

    if arch_dist:
        print(bold("By Arch Type"))
        for arch, cnt in sorted(arch_dist.items(), key=lambda x: -x[1]):
            print(f"  {arch:15s} : {cnt} entries")
        print()

    if pv_dist:
        print(bold("By Pattern Version"))
        for pv, cnt in sorted(pv_dist.items(), key=lambda x: int(x[0])):
            stale_flag = grey("  (stale)") if (current_pv is not None and int(pv) < current_pv) else ""
            print(f"  v{str(pv):>3s} : {cnt} entries{stale_flag}")
        print()


def _pre_warm(cm):
    instances_path = REPORT_DIR / "ta_brain_instances.jsonl"
    if not instances_path.exists():
        print(red("ta_brain_instances.jsonl not found"))
        sys.exit(1)

    from chatbot.modules.ta_brain_query import query_brain

    instances = []
    for line in instances_path.read_text().strip().splitlines():
        try:
            instances.append(json.loads(line))
        except Exception:
            pass

    modes = ["infer", "patterns"]
    seen_combos: set = set()
    added = 0
    skipped = 0

    for inst in instances:
        arch_type = inst.get("arch_type", "")
        topo_sig = inst.get("topology_signature", "")
        if not arch_type or not topo_sig:
            continue
        for mode in modes:
            key = f"{topo_sig}:{mode}"
            if key in seen_combos:
                continue
            seen_combos.add(key)
            # Check if already cached by routing
            route_result = cm.route(topo_sig, arch_type, mode)
            if route_result[0] == "same":
                skipped += 1
                continue
            # Not cached — query to populate
            query_brain(mode=mode, arch_type=arch_type,
                       topology_signature=topo_sig, caller_type="brain-cache")
            added += 1

    print(green(f"Pre-warm complete: {added} entries added, {skipped} already cached"))


def _evict_stale(cm):
    brain_path = REPORT_DIR / "ta_brain.json"
    if not brain_path.exists():
        print(red("ta_brain.json not found"))
        sys.exit(1)
    current_pv = json.loads(brain_path.read_text()).get("pattern_version", 0)
    evicted = cm.evict_stale(current_pv)
    if evicted > 0:
        print(green(f"Evicted {evicted} stale cache entries (pattern_version < {current_pv})"))
    else:
        print(grey(f"No stale entries found (all at pattern_version {current_pv})"))


def _record_feedback(cm, feedback: str, sig: str):
    if feedback not in ("confirmed", "wrong"):
        print(red("--feedback must be 'confirmed' or 'wrong'"))
        sys.exit(1)
    if not sig:
        print(red("--sig TOPOLOGY_SIG is required with --feedback"))
        sys.exit(1)
    confirmed = feedback == "confirmed"
    # record_feedback expects (topology_sig, arch_type, mode, confirmed)
    # We try infer mode as default
    try:
        cm.record_feedback(sig, "", "infer", confirmed)
        status = green("confirmed") if confirmed else red("wrong")
        print(f"Feedback recorded: {sig[:16]}... → {status}")
    except Exception as e:
        print(red(f"Failed to record feedback: {e}"))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="TA Brain cache — inspect and manage the TACO cache")
    ap.add_argument("--stats", action="store_true", help="print cache statistics (default)")
    ap.add_argument("--pre-warm", action="store_true", help="pre-warm cache from all corpus instances")
    ap.add_argument("--evict-stale", action="store_true", help="remove entries with old pattern_version")
    ap.add_argument("--feedback", choices=["confirmed", "wrong"], help="record feedback for a topology sig")
    ap.add_argument("--sig", default="", help="topology signature for --feedback")
    args = ap.parse_args()

    cm = get_cache_manager()

    if args.feedback:
        _record_feedback(cm, args.feedback, args.sig)
    elif args.pre_warm:
        _pre_warm(cm)
    elif args.evict_stale:
        _evict_stale(cm)
    else:
        # Default: stats
        _print_stats(cm)


if __name__ == "__main__":
    main()
