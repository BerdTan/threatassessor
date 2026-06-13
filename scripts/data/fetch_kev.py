"""
Fetch CISA Known Exploited Vulnerabilities (KEV) + CTID KEV→ATT&CK mappings.

Sources:
  CTID: https://github.com/center-for-threat-informed-defense/mappings-explorer
        (Apache 2.0 — CVE→ATT&CK technique mappings, ~550 CVEs, 1,183 T-code links)
  CISA: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json
        (Public domain — 1,600+ actively exploited CVEs with ransomware flags + metadata)

Produces in chatbot/data/kev/:
  kev_ctid_by_technique.json  — {T1190: [{cve_id, mapping_types, capability_group}]}
  kev_cisa_by_cve.json        — {CVE-2021-44228: {vendor, product, dateAdded, ransomware, ...}}
  kev_meta.json               — source URLs, record counts, fetch timestamp

Usage:
    python3 scripts/data/fetch_kev.py
    python3 scripts/data/fetch_kev.py --output-dir path/to/kev/
"""

import sys
import json
import argparse
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install missing dep: pip install requests")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_CISA_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

_CTID_API_URL = (
    "https://api.github.com/repos/center-for-threat-informed-defense/"
    "mappings-explorer/contents/mappings/kev"
)

_REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUT_DIR = _REPO_ROOT / "chatbot" / "data" / "kev"


# ── CTID resolution ───────────────────────────────────────────────────────────

def _resolve_ctid_url() -> str:
    """
    Resolve the latest CTID KEV enterprise JSON URL by listing the GitHub directory tree.
    The path structure is: mappings/kev/attack-{ver}/kev-{date}/enterprise/{file}.json
    Returns the raw.githubusercontent.com URL for the newest kev-date folder.
    """
    log.info("Resolving latest CTID KEV file via GitHub API...")
    resp = requests.get(_CTID_API_URL, timeout=30)
    resp.raise_for_status()

    # List attack version folders (e.g. attack-16.1), take the latest numerically
    attack_dirs = [e for e in resp.json() if e["type"] == "dir"]
    if not attack_dirs:
        raise RuntimeError("No attack version directories found in CTID KEV path")

    def _ver_key(d):
        name = d["name"]  # e.g. "attack-16.1"
        parts = name.replace("attack-", "").split(".")
        return tuple(int(p) for p in parts if p.isdigit())

    latest_attack = sorted(attack_dirs, key=_ver_key)[-1]
    log.info(f"  Latest ATT&CK version: {latest_attack['name']}")

    # List kev-date folders inside the attack version dir
    resp2 = requests.get(latest_attack["url"], timeout=30)
    resp2.raise_for_status()
    kev_dirs = [e for e in resp2.json() if e["type"] == "dir" and e["name"].startswith("kev-")]
    if not kev_dirs:
        raise RuntimeError(f"No kev-date directories found under {latest_attack['name']}")

    latest_kev = sorted(kev_dirs, key=lambda d: d["name"])[-1]
    log.info(f"  Latest KEV date folder: {latest_kev['name']}")

    # List enterprise/ subfolder
    resp3 = requests.get(latest_kev["url"], timeout=30)
    resp3.raise_for_status()
    ent_dirs = [e for e in resp3.json() if e["type"] == "dir" and e["name"] == "enterprise"]
    if not ent_dirs:
        raise RuntimeError("No enterprise/ subfolder found")

    resp4 = requests.get(ent_dirs[0]["url"], timeout=30)
    resp4.raise_for_status()
    json_files = [e for e in resp4.json() if e["name"].endswith(".json")]
    if not json_files:
        raise RuntimeError("No JSON file found in enterprise/ subfolder")

    # Convert blob URL to raw URL
    file_entry = json_files[0]
    raw_url = (
        "https://raw.githubusercontent.com/center-for-threat-informed-defense/"
        f"mappings-explorer/main/{file_entry['path']}"
    )
    log.info(f"  Resolved CTID URL: {raw_url}")
    return raw_url, latest_attack["name"], latest_kev["name"]


# ── Fetch + index ─────────────────────────────────────────────────────────────

def fetch_ctid(out_dir: Path) -> dict:
    """Download CTID KEV JSON and build technique→CVE index."""
    url, attack_ver, kev_date = _resolve_ctid_url()

    log.info("Fetching CTID KEV→ATT&CK mappings...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    raw = resp.json()

    mapping_objects = raw.get("mapping_objects", [])
    log.info(f"  {len(mapping_objects)} raw mapping entries")

    # Build technique → CVE list index
    by_technique: dict[str, list] = defaultdict(list)
    seen: dict[str, set] = defaultdict(set)  # technique → set of CVE IDs (dedup)

    for obj in mapping_objects:
        technique_id = obj.get("attack_object_id", "")
        cve_id = obj.get("capability_id", "")
        if not technique_id or not cve_id or not cve_id.upper().startswith("CVE-"):
            continue
        cve_id = cve_id.upper()
        if cve_id in seen[technique_id]:
            continue
        seen[technique_id].add(cve_id)
        by_technique[technique_id].append({
            "cve_id":           cve_id,
            "mapping_types":    [obj.get("mapping_type", "")],
            "capability_group": obj.get("capability_group", ""),
            "cve_description":  obj.get("capability_description", ""),
        })

    # Sort CVE lists per technique for determinism
    for tid in by_technique:
        by_technique[tid].sort(key=lambda e: e["cve_id"])

    out = {
        "source_url":    url,
        "attack_version": attack_ver,
        "kev_date":      kev_date,
        "technique_count": len(by_technique),
        "total_mappings":  sum(len(v) for v in by_technique.values()),
        "data":          dict(sorted(by_technique.items())),
    }

    _write_json(out_dir / "kev_ctid_by_technique.json", out)
    log.info(
        f"  CTID: {len(by_technique)} techniques mapped, "
        f"{out['total_mappings']} CVE-technique links"
    )
    return out


def fetch_cisa(out_dir: Path) -> dict:
    """Download CISA KEV JSON and build CVE→metadata index."""
    log.info(f"Fetching CISA KEV from {_CISA_URL}...")
    resp = requests.get(_CISA_URL, timeout=60)
    resp.raise_for_status()
    raw = resp.json()

    vulns = raw.get("vulnerabilities", [])
    log.info(f"  {len(vulns)} CISA KEV entries")

    by_cve = {}
    ransomware_count = 0
    for v in vulns:
        cve_id = v.get("cveID", "").upper()
        if not cve_id:
            continue
        is_ransomware = (v.get("knownRansomwareCampaignUse", "") == "Known")
        if is_ransomware:
            ransomware_count += 1
        by_cve[cve_id] = {
            "vendor":          v.get("vendorProject", ""),
            "product":         v.get("product", ""),
            "vulnerability_name": v.get("vulnerabilityName", ""),
            "date_added":      v.get("dateAdded", ""),
            "description":     v.get("shortDescription", ""),
            "ransomware":      is_ransomware,
            "required_action": v.get("requiredAction", ""),
            "cwes":            v.get("cwes", []),
        }

    out = {
        "source_url":       _CISA_URL,
        "catalog_version":  raw.get("catalogVersion", ""),
        "date_released":    raw.get("dateReleased", ""),
        "cve_count":        len(by_cve),
        "ransomware_count": ransomware_count,
        "data":             dict(sorted(by_cve.items())),
    }

    _write_json(out_dir / "kev_cisa_by_cve.json", out)
    log.info(
        f"  CISA: {len(by_cve)} CVEs indexed, {ransomware_count} ransomware-linked"
    )
    return out


def write_meta(out_dir: Path, ctid_out: dict, cisa_out: dict) -> None:
    meta = {
        "fetched_at":          datetime.now(timezone.utc).isoformat(),
        "ctid_source":         ctid_out["source_url"],
        "ctid_attack_version": ctid_out["attack_version"],
        "ctid_kev_date":       ctid_out["kev_date"],
        "ctid_technique_count": ctid_out["technique_count"],
        "ctid_total_mappings": ctid_out["total_mappings"],
        "cisa_source":         cisa_out["source_url"],
        "cisa_cve_count":      cisa_out["cve_count"],
        "cisa_ransomware_count": cisa_out["ransomware_count"],
    }
    _write_json(out_dir / "kev_meta.json", meta)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_json(path: Path, data: dict) -> None:
    if path.exists():
        backup = path.with_suffix(".json.bak")
        backup.write_bytes(path.read_bytes())
        log.info(f"  Backed up {path.name} → {backup.name}")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    log.info(f"  Wrote {path}")


def _verify(out_dir: Path, ctid_out: dict, cisa_out: dict) -> None:
    ctid_loaded = json.loads((out_dir / "kev_ctid_by_technique.json").read_text())
    assert ctid_loaded["technique_count"] == ctid_out["technique_count"]
    cisa_loaded = json.loads((out_dir / "kev_cisa_by_cve.json").read_text())
    assert cisa_loaded["cve_count"] == cisa_out["cve_count"]
    log.info("Validation passed.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch CISA KEV + CTID KEV→ATT&CK mappings")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ctid_out = fetch_ctid(out_dir)
    cisa_out = fetch_cisa(out_dir)
    write_meta(out_dir, ctid_out, cisa_out)
    _verify(out_dir, ctid_out, cisa_out)

    log.info(
        f"\nDone. Output in {out_dir}/\n"
        f"  kev_ctid_by_technique.json  — {ctid_out['technique_count']} techniques, "
        f"{ctid_out['total_mappings']} CVE links\n"
        f"  kev_cisa_by_cve.json        — {cisa_out['cve_count']} CVEs "
        f"({cisa_out['ransomware_count']} ransomware-linked)\n"
        f"  kev_meta.json               — fetch provenance"
    )


if __name__ == "__main__":
    main()
