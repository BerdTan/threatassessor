"""
ThreatAssessor Export Bundle — ta_export.json

Produces a single, versioned JSON file from all artefacts for one architecture.
Schema: ta-export/1.0

Consumers:
  - CI/CD gate: read gate.result (PASS|BLOCK) + gate.blocking_signals
  - Downstream threat tools: read otm.threats / otm.mitigations (OTM-compatible)
  - SIEM/SOAR: read detect_findings (OCSF DetectionFinding 2004)
  - Dashboards: read assessment, tatb, governance
  - MCP tool: export_assessment → returns this bundle as JSON
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── helpers ──────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> Dict:
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _read_ocsf(path: Path) -> List[Dict]:
    """Read ocsf_findings.json — may be a list or {findings: [...]}."""
    d = _read_json(path)
    if isinstance(d, list):
        return d
    return d.get("findings", [])


# ── section builders ──────────────────────────────────────────────────────────

def _build_architecture(arch_name: str, gt: Dict) -> Dict:
    meta = gt.get("metadata", {})
    return {
        "name":       arch_name,
        "type":       meta.get("architecture_type", "unknown"),
        "node_count": meta.get("node_count", 0),
        "edge_count": meta.get("edge_count", 0),
        "ssp_profile": meta.get("ssp_profile", ""),
        "run_id":     meta.get("run_id", ""),
    }


def _build_gate(gov: Dict, ocsf: List[Dict]) -> Dict:
    exp = gov.get("exploitation", {})
    blocked = exp.get("blocked", False) or exp.get("severity") == "CRITICAL"
    risk = gov.get("overall_risk_level", "UNKNOWN")

    blocking = []
    if exp.get("severity") == "CRITICAL":
        blocking.append(f"exploitation.severity=CRITICAL")
    if gov.get("sovereignty", {}).get("flagged"):
        blocking.append("sovereignty.flagged=true")
    for f in ocsf:
        sev = str(f.get("severity") or "").upper()
        rule = f.get("unmapped", {}).get("rule_id", "")
        if sev in ("CRITICAL", "HIGH") and rule:
            blocking.append(f"detect:{rule}")

    return {
        "result":           "BLOCK" if blocked else "PASS",
        "risk_level":       risk,
        "blocking_signals": list(dict.fromkeys(blocking)),  # dedupe, preserve order
    }


def _build_assessment(gt: Dict) -> Dict:
    aps = gt.get("attack_paths", [])
    techs = gt.get("techniques", [])
    controls = gt.get("control_recommendations", [])
    val = gt.get("validation", {}) or gt.get("validation_report", {}) or {}

    return {
        "risk_score_before":   gt.get("residual_risk_before", {}) or None,
        "risk_score_after":    gt.get("residual_risk_after", {})  or None,
        "confidence":          gt.get("confidence"),
        "val_pct":             val.get("val_pct"),
        "attack_paths": [
            {
                "id":         ap.get("id"),
                "entry":      ap.get("entry"),
                "target":     ap.get("target"),
                "criticality": ap.get("criticality_tier") or ap.get("criticality"),
                "techniques": ap.get("techniques", [])[:10],
                "hop_count":  ap.get("hop_count"),
            }
            for ap in aps
        ],
        "mitre_techniques":    techs if isinstance(techs, list) else [],
        "controls_recommended": [
            {
                "control":  c.get("control"),
                "priority": c.get("priority"),
                "score":    c.get("score"),
            }
            for c in controls[:20]
        ],
    }


def _build_tatb(tatb_scores: Optional[Dict], arch_name: str) -> Dict:
    if not tatb_scores:
        return {}
    archs = tatb_scores.get("architectures", [])
    row = next((a for a in archs if a.get("name") == arch_name), None)
    if not row:
        return {}
    return {
        "threat":  row.get("threat"),
        "ttp":     row.get("ttp"),
        "risk":    row.get("risk"),
        "plan":    row.get("plan"),
        "overall": row.get("overall"),
    }


def _build_governance(gov: Dict) -> Dict:
    aivss = gov.get("aivss", {})
    return {
        "aivss_composite":    aivss.get("overall", {}).get("composite"),
        "outbound_composite": aivss.get("outbound", {}).get("composite"),
        "risk_level":         gov.get("overall_risk_level"),
        "signals": {
            "exploitation_severity": gov.get("exploitation", {}).get("severity"),
            "manipulation_severity": gov.get("manipulation", {}).get("severity"),
            "leakage_flagged":       gov.get("leakage", {}).get("flagged"),
            "sovereignty_flagged":   gov.get("sovereignty", {}).get("flagged"),
            "cross_boundary_nodes":  gov.get("sovereignty", {}).get("cross_boundary_nodes", []),
        },
    }


def _build_moe_consensus(moe: Dict) -> Dict:
    if not moe:
        return {}
    return {
        "confidence":        moe.get("confidence"),
        "redesign_required": moe.get("redesign_required", False),
        "critics": {
            k: {
                "status":     v.get("status"),
                "confidence": v.get("confidence"),
                "top_gap":    (v.get("gaps") or [{}])[0].get("description") if v.get("gaps") else None,
            }
            for k, v in (moe.get("critics") or {}).items()
        },
    }


def _build_otm(gt: Dict, arch_name: str) -> Dict:
    """
    OTM-compatible section.
    Maps TA artefacts to Open Threat Model (OTM) concepts:
      assets     → parsed_nodes from metadata
      threats    → attack_paths
      mitigations → control_recommendations
    """
    meta = gt.get("metadata", {})
    nodes = meta.get("parsed_nodes", {})

    assets = [
        {"id": k, "name": v.get("label", k), "type": v.get("shape", "component")}
        for k, v in nodes.items()
    ]

    aps = gt.get("attack_paths", [])
    threats = [
        {
            "id":          ap.get("id", f"TH-{i+1:03d}"),
            "name":        f"{ap.get('entry','?')} → {ap.get('target','?')}",
            "description": ap.get("rationale", ""),
            "risk":        ap.get("criticality_tier") or ap.get("criticality"),
            "mitre_techniques": ap.get("techniques", []),
            "affected_assets":  list({n for n in (ap.get("path") or "").split("→") if n.strip()})
                                if isinstance(ap.get("path"), str) else [],
        }
        for i, ap in enumerate(aps)
    ]

    controls = gt.get("control_recommendations", [])
    mitigations = [
        {
            "id":          f"MIT-{i+1:03d}",
            "name":        c.get("control", ""),
            "priority":    c.get("priority"),
            "mitre_mitigations": [m.get("id") for m in (c.get("mitigations") or []) if isinstance(m, dict) and m.get("id")],
        }
        for i, c in enumerate(controls[:20])
    ]

    return {
        "otm_version": "0.2.0",
        "project":     {"name": arch_name, "id": arch_name},
        "assets":      assets,
        "threats":     threats,
        "mitigations": mitigations,
    }


# ── main export ───────────────────────────────────────────────────────────────

def build_export(
    arch_name: str,
    report_dir: Path,
    tatb_scores: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Assemble ta_export.json for one architecture.

    Args:
        arch_name:   Architecture directory name.
        report_dir:  Path to report/<arch_name>/.
        tatb_scores: Optional pre-fetched tatb-corpus response dict.

    Returns:
        Export bundle dict (schema ta-export/1.0).
    """
    gt  = _read_json(report_dir / "ground_truth.json")
    gov = _read_json(report_dir / "governance_signals.json")
    moe = _read_json(report_dir / "07_moe_orchestrator.json")
    ocsf = _read_ocsf(report_dir / "ocsf_findings.json")

    return {
        "schema":       "ta-export/1.0",
        "exported_at":  datetime.now(timezone.utc).isoformat(),
        "architecture": _build_architecture(arch_name, gt),
        "gate":         _build_gate(gov, ocsf),
        "assessment":   _build_assessment(gt),
        "tatb":         _build_tatb(tatb_scores, arch_name),
        "governance":   _build_governance(gov),
        "moe_consensus": _build_moe_consensus(moe),
        "detect_findings": [f for f in ocsf if f.get("class_uid") == 2004],
        "security_findings": [f for f in ocsf if f.get("class_uid") == 2001],
        "otm":          _build_otm(gt, arch_name),
    }


def save_export(arch_name: str, report_dir: Path, tatb_scores: Optional[Dict] = None) -> Path:
    """Write ta_export.json to report_dir. Returns the path."""
    bundle = build_export(arch_name, report_dir, tatb_scores)
    out = report_dir / "ta_export.json"
    with open(out, "w") as f:
        json.dump(bundle, f, indent=2)
    return out
