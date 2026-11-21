#!/usr/bin/env python3
"""Hijack/drift gap map (Entry 264 step 4). Read-only, no API, deterministic.

For each DETECT rule: its class (hijack|drift, from rule_class.yaml) and the
strongest pipeline response its actions actually trigger. Then the mismatches.

Response from actions: block_run -> block; reduce_budget -> throttle;
block_deployment -> deploy_label (label only, no pipeline gate); anything else
(page_soc, quarantine, flag, audit...) -> alert_only: detected,
but nothing in the pipeline is stopped or slowed. ``steer`` does not exist yet.
"""
import collections
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "policies" / "soc_detection_rules.yaml"
CLASSES = Path(__file__).resolve().parent / "cases" / "rule_class.yaml"


def response(rule: dict) -> str:
    acts = {a.get("type") for a in rule.get("actions", []) if isinstance(a, dict)}
    if "block_run" in acts:
        return "block"
    if "reduce_budget" in acts:
        return "throttle"
    if "block_deployment" in acts:
        return "deploy_label"  # SOC label on the architecture; the pipeline is not stopped
    return "alert_only"


def build() -> dict:
    rules = yaml.safe_load(RULES.read_text())["rules"]
    cfg = yaml.safe_load(CLASSES.read_text())
    rows, gaps = [], collections.defaultdict(list)
    for r in rules:
        cls = cfg["overrides"].get(r["id"]) or cfg["domains"].get(r["domain"])
        resp = response(r)
        rows.append({"id": r["id"], "domain": r["domain"], "class": cls,
                     "severity": r["severity"], "response": resp})
        if cls == "hijack" and resp not in ("block", "kill"):
            gaps["hijack_unenforced"].append(r["id"])
            if r["severity"] == "Critical":
                key = "critical_accepted" if r["id"] in cfg.get("accepted_alert_only", {}) else "hijack_unenforced_critical"
                gaps[key].append(r["id"])
        if cls == "drift" and resp == "block":
            gaps["drift_overblocked"].append(r["id"])
        if cls == "drift" and resp not in ("throttle", "steer"):
            gaps["drift_no_graduated_response"].append(r["id"])
    return {"rows": rows, "gaps": dict(gaps)}


def main() -> int:
    out = build()
    rows = out["rows"]
    if "--json" in sys.argv:
        print(json.dumps(out, indent=1))
        return 0
    print(f"{'class':7} {'rules':>5} {'block':>6} {'throttle':>9} {'deploy_label':>13} {'alert_only':>11}")
    for cls in ("hijack", "drift"):
        sub = [r for r in rows if r["class"] == cls]
        c = collections.Counter(r["response"] for r in sub)
        print(f"{cls:7} {len(sub):5} {c['block']:6} {c['throttle']:9} {c['deploy_label']:13} {c['alert_only']:11}")
    for k, v in out["gaps"].items():
        print(f"\n{k}: {len(v)}")
        if k != "drift_no_graduated_response":
            print("  " + ", ".join(i.replace("DETECT-", "") for i in v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
