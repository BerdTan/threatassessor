#!/usr/bin/env python3
"""brain-ingest.py — add one arch dir to the instance layer incrementally."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from chatbot.modules.ta_brain_builder import (
    extract_instance, run_distiller, build_brain, REPORT_DIR, MIN_EVIDENCE,
)

# ── Colour helpers ────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def bold(t):  return _c(t, "1")
def green(t): return _c(t, "92")
def amber(t): return _c(t, "33")
def red(t):   return _c(t, "31")
def grey(t):  return _c(t, "2")
def cyan(t):  return _c(t, "36")


def main():
    ap = argparse.ArgumentParser(description="TA Brain ingest — add one arch dir incrementally")
    ap.add_argument("--arch-dir", required=True, help="path to report dir (must have ground_truth.json)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be extracted without writing")
    args = ap.parse_args()

    arch_dir = Path(args.arch_dir).resolve()
    if not arch_dir.exists():
        print(red(f"arch-dir not found: {arch_dir}"))
        sys.exit(1)
    if not (arch_dir / "ground_truth.json").exists():
        print(red(f"ground_truth.json not found in {arch_dir}"))
        sys.exit(1)

    instances_path = REPORT_DIR / "ta_brain_instances.jsonl"
    brain_path = REPORT_DIR / "ta_brain.json"

    # Check if already ingested
    existing_ids: set = set()
    if instances_path.exists():
        for line in instances_path.read_text().strip().splitlines():
            try:
                existing_ids.add(json.loads(line)["arch_id"])
            except Exception:
                pass

    inst = extract_instance(arch_dir)
    if inst is None:
        print(red(f"Could not extract instance from {arch_dir} — check ground_truth.json and governance_signals.json"))
        sys.exit(1)

    arch_id = inst["arch_id"]
    arch_type = inst.get("arch_type", "?")
    techniques = inst.get("techniques", [])
    controls = inst.get("controls_missing", [])
    topo_sig = inst.get("topology_signature", "?")

    print(bold("Extracted instance:"))
    print(f"  arch_id       : {cyan(arch_id)}")
    print(f"  arch_type     : {arch_type}")
    print(f"  topology_sig  : {grey(topo_sig)}")
    print(f"  techniques    : {len(techniques)}")
    print(f"  controls miss : {len(controls)}")
    if controls:
        print(f"  top controls  : {', '.join(controls[:5])}")
    print()

    if arch_id in existing_ids:
        print(amber(f"Already ingested: {arch_id} — skipping"))
        sys.exit(0)

    if args.dry_run:
        print(grey("Dry run — not writing to instances.jsonl"))
        sys.exit(0)

    # Append instance
    with instances_path.open("a") as f:
        f.write(json.dumps(inst) + "\n")
    print(green(f"Appended to instances.jsonl"))

    # Re-run distiller on all instances
    all_instances = []
    for line in instances_path.read_text().strip().splitlines():
        try:
            all_instances.append(json.loads(line))
        except Exception:
            pass

    if brain_path.exists():
        brain = json.loads(brain_path.read_text())
        hold_out = frozenset()  # don't re-split hold-out on single ingest
        new_patterns = run_distiller(all_instances, min_evidence=MIN_EVIDENCE)
        brain["patterns"] = new_patterns
        brain["pattern_version"] = brain.get("pattern_version", 0) + 1
        brain_path.write_text(json.dumps(brain, indent=2))
        print(green(f"Patterns updated: {len(new_patterns)} patterns (pattern_version {brain['pattern_version']})"))
    else:
        print(amber("ta_brain.json not found — patterns not updated. Run brain-grow to initialise."))

    print()
    print(bold("Done.") + f"  Total instances: {len(all_instances)}")


if __name__ == "__main__":
    main()
