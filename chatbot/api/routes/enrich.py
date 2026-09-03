"""
Enrichment API — POST /api/v1/enrich

Accepts a VAPT/SAST finding + a component name and returns TA threat context
for that component from an existing analysis. Read-only, deterministic, <50ms.

Consumers: SAST scanners, VAPT tools, CI pipelines wanting to annotate their
findings with TA's threat intelligence (attack paths, MITRE techniques, controls).
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from chatbot.api.dependencies import verify_api_key
from chatbot.api.routes.reports import resolve_arch_dir

router = APIRouter(prefix="/api/v1", tags=["enrichment"])


# ── request / response models ─────────────────────────────────────────────────

class EnrichFinding(BaseModel):
    type: Literal["cve", "technique", "control_gap", "vulnerability", "other"] = "other"
    id: str                              # e.g. "CVE-2024-1234", "T1190", "MFA"
    severity: Optional[str] = None       # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    description: Optional[str] = None


class EnrichRequest(BaseModel):
    arch_name: str
    component: str                       # component label from the scanner
    finding: EnrichFinding
    include_attack_paths: bool = True
    include_controls: bool = True


class ComponentMatch(BaseModel):
    node_id: str
    node_label: str
    match_confidence: float


class EnrichedAttackPath(BaseModel):
    id: Optional[str] = None
    entry: str
    target: str
    criticality: Optional[str] = None
    techniques: List[str] = []


class EnrichResponse(BaseModel):
    arch_name: str
    component_found: bool
    matched_nodes: List[ComponentMatch]
    attack_paths_touching: List[EnrichedAttackPath]
    techniques_mapped: List[str]
    controls_recommended: List[str]
    risk_narrative: str
    ta_export_gate: Optional[str]        # "PASS" | "BLOCK" | None


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> Dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _fuzzy_match(query: str, candidates: List[str], cutoff: float = 0.55) -> List[tuple[str, float]]:
    """Return (candidate, score) pairs sorted by score descending."""
    query_lower = query.lower()
    results = []
    for c in candidates:
        seq = difflib.SequenceMatcher(None, query_lower, c.lower())
        score = seq.ratio()
        if score >= cutoff:
            results.append((c, score))
    return sorted(results, key=lambda x: x[1], reverse=True)


def _node_in_path(node_ids: set[str], ap: Dict) -> bool:
    """Check if any of the matched node ids appear in an attack path."""
    entry = ap.get("entry", "")
    target = ap.get("target", "")
    path_str = ap.get("path", "") or ""
    for nid in node_ids:
        if nid in entry or nid in target or nid in path_str:
            return True
    return False


def _techniques_from_finding(finding: EnrichFinding, attack_paths: List[Dict]) -> List[str]:
    """Collect techniques: from the finding itself (if it's a technique ID) + from attack paths."""
    techs: set[str] = set()
    if finding.type == "technique" and finding.id.upper().startswith("T"):
        techs.add(finding.id.upper())
    for ap in attack_paths:
        for t in ap.get("techniques", []):
            techs.add(t)
    return sorted(techs)


# ── endpoint ──────────────────────────────────────────────────────────────────

@router.post("/enrich", response_model=EnrichResponse)
async def enrich_finding(
    body: EnrichRequest,
    _: str = Depends(verify_api_key),
) -> EnrichResponse:
    """
    Enrich a SAST/VAPT finding with TA threat context for a specific component.

    Requires an existing analysis for arch_name (run POST /api/v1/analyze first).
    Returns matched component nodes, touching attack paths, MITRE techniques, and
    recommended controls — all from the saved report, no re-analysis.
    """
    report_dir = resolve_arch_dir(body.arch_name)
    gt_path  = report_dir / "ground_truth.json"
    gov_path = report_dir / "governance_signals.json"

    if not gt_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for '{body.arch_name}'. Run POST /api/v1/analyze first.",
        )

    gt  = _read_json(gt_path)
    gov = _read_json(gov_path)

    # 1. Collect node labels from parsed_nodes in metadata
    parsed_nodes: Dict[str, Any] = gt.get("metadata", {}).get("parsed_nodes", {})
    node_labels: List[str] = [v.get("label", k) for k, v in parsed_nodes.items()]
    node_by_label: Dict[str, str] = {v.get("label", k): k for k, v in parsed_nodes.items()}

    # 2. Fuzzy-match query component against node labels
    matches = _fuzzy_match(body.component, node_labels)
    matched_nodes = [
        ComponentMatch(
            node_id=node_by_label.get(label, label),
            node_label=label,
            match_confidence=round(score, 3),
        )
        for label, score in matches[:5]
    ]
    matched_node_ids = {m.node_id for m in matched_nodes}
    matched_node_labels = {m.node_label for m in matched_nodes}

    # 3. Filter attack paths where a matched node appears
    all_aps: List[Dict] = gt.get("expected_attack_paths", []) or gt.get("attack_paths", [])
    if body.include_attack_paths:
        touching = [
            ap for ap in all_aps
            if _node_in_path(matched_node_ids | matched_node_labels, ap)
        ]
    else:
        touching = []

    enriched_paths = [
        EnrichedAttackPath(
            id=ap.get("id"),
            entry=ap.get("entry", ""),
            target=ap.get("target", ""),
            criticality=ap.get("criticality_tier") or ap.get("criticality"),
            techniques=ap.get("techniques", [])[:10],
        )
        for ap in touching[:10]
    ]

    # 4. Techniques: from finding + from touching paths
    techniques = _techniques_from_finding(body.finding, touching)

    # 5. Controls
    controls_raw: List[Dict] = gt.get("control_recommendations", [])
    controls: List[str] = []
    if body.include_controls:
        controls = [c.get("control", "") for c in controls_raw[:10] if c.get("control")]

    # 6. Gate from governance signals
    gate: Optional[str] = None
    if gov:
        blocked = gov.get("exploitation", {}).get("blocked", False)
        gate = "BLOCK" if blocked else "PASS"

    # 7. Risk narrative (deterministic — no LLM)
    risk_level = gov.get("overall_risk_level", "UNKNOWN") if gov else "UNKNOWN"
    comp_name = matched_nodes[0].node_label if matched_nodes else body.component
    ap_count = len(touching)
    narrative = (
        f"Component '{comp_name}' appears in {ap_count} attack path(s) in the "
        f"'{body.arch_name}' architecture (overall risk: {risk_level}). "
        f"Finding {body.finding.id} ({body.finding.type}) maps to "
        f"{len(techniques)} MITRE technique(s)."
    ) if matched_nodes else (
        f"No node matching '{body.component}' found in '{body.arch_name}'. "
        f"Overall architecture risk: {risk_level}."
    )

    return EnrichResponse(
        arch_name=body.arch_name,
        component_found=bool(matched_nodes),
        matched_nodes=matched_nodes,
        attack_paths_touching=enriched_paths,
        techniques_mapped=techniques,
        controls_recommended=controls,
        risk_narrative=narrative,
        ta_export_gate=gate,
    )
