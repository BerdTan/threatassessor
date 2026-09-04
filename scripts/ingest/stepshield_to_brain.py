"""
StepShield catalog → TA Brain instance ingest.

Downloads the StepShield incident catalog (127 entries) from GitHub and appends
one brain instance per entry to report/brain/ta_brain_instances.jsonl, then
rebuilds the brain pattern layer.

Usage:
    python3 scripts/ingest/stepshield_to_brain.py [--dry-run]

Requires: gh CLI authenticated (gh auth status), or set GITHUB_TOKEN env var.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAIN_DIR = ROOT / "report" / "brain"
INSTANCES_PATH = BRAIN_DIR / "ta_brain_instances.jsonl"

REPO = "glo26/stepshield"
CATALOG_PATH = "data/incidents/catalog.json"

# StepShield category → TA DETECT rule IDs (best-fit mapping)
CATEGORY_TO_DETECT: dict[str, list[str]] = {
    "INV": ["DETECT-023", "DETECT-011"],        # Data Exfiltration
    "SEC": ["DETECT-022", "DETECT-009"],        # Privilege Escalation
    "RES": ["DETECT-032", "DETECT-021"],        # Resource Hijacking
    "TST": ["DETECT-028", "DETECT-034"],        # Supply Chain Attack
    "DEC": ["DETECT-019", "DETECT-005"],        # Destructive Action
    "UFO": ["DETECT-025", "DETECT-004"],        # Covert Persistence
}

# Severity level → approximate AIVSS composite
SEVERITY_TO_AIVSS: dict[str, float] = {
    "L1": 0.40,
    "L2": 0.65,
    "L3": 0.90,
}


def _gh_api(path: str) -> bytes:
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{path}"],
        capture_output=True, check=True
    )
    return result.stdout


def fetch_catalog() -> list[dict]:
    raw = json.loads(_gh_api(CATALOG_PATH))
    content = base64.b64decode(raw["content"])
    return json.loads(content)


def catalog_entry_to_instance(entry: dict) -> dict:
    incident_id = entry["incident_id"]          # e.g. "INC-001"
    category = entry["category"]                # e.g. "UFO"
    attck = entry.get("attck_technique", "")    # e.g. "T1059.004"
    severity_levels = entry.get("severity_levels", ["L2"])
    max_severity = severity_levels[-1] if severity_levels else "L2"

    # Normalise ATT&CK ID to base technique (strip sub-technique for Brain lookup)
    base_technique = attck.split(".")[0] if attck else None
    techniques = [base_technique] if base_technique else []
    if attck and "." in attck:
        techniques.append(attck)  # keep sub-technique too

    return {
        "arch_id": f"ss_{incident_id.lower().replace('-', '_')}",
        "arch_type": "agentic",
        "topology_signature": f"stepshield_{category.lower()}_{incident_id.lower()}",
        "node_count": 0,          # trajectories have no node graph
        "edge_count": 0,
        "techniques": techniques,
        "controls_missing": _controls_missing_for_category(category),
        "hub_nodes": [],
        "aivss_composite": SEVERITY_TO_AIVSS.get(max_severity, 0.65),
        "aivss_severity": _aivss_severity(max_severity),
        "fired_detect_rules": CATEGORY_TO_DETECT.get(category, []),
        "run_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "stepshield/v1",
        "stepshield_meta": {
            "incident_id": incident_id,
            "category": category,
            "category_name": entry.get("category_name", ""),
            "severity_levels": severity_levels,
            "task_title": entry.get("task_specification", {}).get("title", ""),
        },
    }


def _controls_missing_for_category(category: str) -> list[str]:
    return {
        "INV": ["dlp", "egress filtering", "secrets management", "least privilege"],
        "SEC": ["mfa", "least privilege", "rbac", "privileged access management"],
        "RES": ["rate limiting", "resource quotas", "cost alerting", "auto-scaling limits"],
        "TST": ["code signing", "dependency pinning", "sbom", "supply chain verification"],
        "DEC": ["backup", "immutable storage", "change control", "rollback"],
        "UFO": ["edr", "behavioral analysis", "file integrity monitoring", "process allowlisting"],
    }.get(category, [])


def _aivss_severity(level: str) -> str:
    return {"L1": "LOW", "L2": "MEDIUM", "L3": "HIGH"}.get(level, "MEDIUM")


def load_existing_ids() -> set[str]:
    if not INSTANCES_PATH.exists():
        return set()
    ids = set()
    with INSTANCES_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ids.add(json.loads(line)["arch_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest StepShield catalog into TA Brain")
    parser.add_argument("--dry-run", action="store_true", help="Print instances without writing")
    args = parser.parse_args()

    print("Fetching StepShield incident catalog…")
    try:
        catalog = fetch_catalog()
    except subprocess.CalledProcessError as e:
        print(f"ERROR: gh api failed — {e.stderr.decode().strip()}", file=sys.stderr)
        print("Ensure 'gh auth status' is authenticated.", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(catalog)} incidents loaded")

    existing_ids = load_existing_ids()
    print(f"  {len(existing_ids)} existing brain instances (will skip duplicates)")

    instances = []
    skipped = 0
    for entry in catalog:
        inst = catalog_entry_to_instance(entry)
        if inst["arch_id"] in existing_ids:
            skipped += 1
            continue
        instances.append(inst)

    print(f"  {len(instances)} new instances to write, {skipped} already present")

    if not instances:
        print("Nothing to write.")
        return

    if args.dry_run:
        print("\n--- DRY RUN (first 3 instances) ---")
        for inst in instances[:3]:
            print(json.dumps(inst, indent=2))
        return

    INSTANCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INSTANCES_PATH.open("a") as f:
        for inst in instances:
            f.write(json.dumps(inst) + "\n")

    print(f"\n✓ Appended {len(instances)} StepShield instances to {INSTANCES_PATH.relative_to(ROOT)}")

    # Rebuild brain pattern layer
    print("\nRebuilding TA Brain pattern layer (incremental=True)…")
    result = subprocess.run(
        [sys.executable, "-m", "chatbot.modules.ta_brain_builder", "--incremental"],
        cwd=ROOT, capture_output=False
    )
    if result.returncode != 0:
        print("WARNING: brain rebuild exited non-zero — check output above", file=sys.stderr)
    else:
        print("✓ Brain rebuild complete")


if __name__ == "__main__":
    main()
