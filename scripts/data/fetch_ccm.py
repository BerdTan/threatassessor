"""
Fetch CSA CCM v4.1 → MITRE ATT&CK Enterprise mapping from CTID Mappings Explorer.

Source: Center for Threat-Informed Defense (Apache 2.0)
URL: https://center-for-threat-informed-defense.github.io/mappings-explorer/data/
     csa_ccm/attack-17.1/csa_ccm-4.1/enterprise/
     csa_ccm-4.1_attack-17.1-enterprise.yaml

Produces two output files in chatbot/data/ccm/ (git-ignored):
  ccm_by_technique.yaml  — {T1078.004: [{ccm_id, description, group, comments, mapping_type}, ...]}
  ccm_by_control.yaml    — {IAM-16: {description, group, techniques: [T####, ...]}}

Usage:
    python3 scripts/data/fetch_ccm.py
    python3 scripts/data/fetch_ccm.py --output-dir path/to/ccm/
"""

import sys
import argparse
import logging
from collections import defaultdict
from pathlib import Path

try:
    import requests
    import yaml
except ImportError:
    print("Install missing deps: pip install requests pyyaml")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_SOURCE_URL = (
    "https://center-for-threat-informed-defense.github.io/mappings-explorer"
    "/data/csa_ccm/attack-17.1/csa_ccm-4.1/enterprise"
    "/csa_ccm-4.1_attack-17.1-enterprise.yaml"
)

_REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUT_DIR = _REPO_ROOT / "chatbot" / "data" / "ccm"


def fetch_and_index(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Fetching CSA CCM → ATT&CK mapping from CTID...")
    resp = requests.get(_SOURCE_URL, timeout=60)
    resp.raise_for_status()
    raw = yaml.safe_load(resp.text)
    objs = raw.get("mapping_objects", [])
    log.info(f"Downloaded {len(objs)} mapping entries")

    # Filter to mitigates-only (skip non_mappable)
    mitigates = [o for o in objs if o.get("mapping_type") == "mitigates"]
    log.info(f"  {len(mitigates)} mitigates, {len(objs) - len(mitigates)} non_mappable (skipped)")

    # Index 1: by technique ID → list of CCM controls
    by_technique: dict[str, list] = defaultdict(list)
    for o in mitigates:
        tid = o["attack_object_id"]
        entry = {
            "ccm_id":      o["capability_id"],
            "description": o["capability_description"],
            "group":       o["capability_group"],
            "comments":    (o.get("comments") or "").strip(),
        }
        # Deduplicate: skip if same ccm_id already present for this technique
        existing_ids = {e["ccm_id"] for e in by_technique[tid]}
        if entry["ccm_id"] not in existing_ids:
            by_technique[tid].append(entry)

    # Index 2: by CCM control ID → description + technique list
    by_control: dict[str, dict] = {}
    for o in mitigates:
        cid = o["capability_id"]
        if cid not in by_control:
            by_control[cid] = {
                "description": o["capability_description"],
                "group":       o["capability_group"],
                "techniques":  [],
            }
        tid = o["attack_object_id"]
        if tid not in by_control[cid]["techniques"]:
            by_control[cid]["techniques"].append(tid)

    # Sort technique lists for determinism
    for v in by_control.values():
        v["techniques"].sort()

    _write(out_dir / "ccm_by_technique.yaml",
           {"source": _SOURCE_URL, "technique_count": len(by_technique),
            "data": dict(sorted(by_technique.items()))})

    _write(out_dir / "ccm_by_control.yaml",
           {"source": _SOURCE_URL, "control_count": len(by_control),
            "data": dict(sorted(by_control.items()))})

    log.info(
        f"Wrote {len(by_technique)} technique entries, "
        f"{len(by_control)} CCM control entries to {out_dir}"
    )

    # Sanity check
    loaded = yaml.safe_load((out_dir / "ccm_by_technique.yaml").read_text())
    assert loaded["technique_count"] == len(by_technique)
    log.info("Validation passed.")


def _write(path: Path, data: dict) -> None:
    if path.exists():
        backup = path.with_suffix(".yaml.bak")
        backup.write_bytes(path.read_bytes())
        log.info(f"Backed up {path.name} → {backup.name}")
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    log.info(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch CSA CCM → ATT&CK mapping from CTID")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()
    fetch_and_index(Path(args.output_dir))


if __name__ == "__main__":
    main()
