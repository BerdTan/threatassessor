"""
Workspace Routes

CRUD endpoints for grouping architectures into named workspaces (mega-systems).
Workspaces are persisted in report/.workspaces.json — a dot-prefixed file that
existing list_architectures() already skips.

Domain field is a plain string (e.g. "financial", "healthcare") reserved as the
EventBroker Phase C hook for per-workspace SIEM/LangfuseSink routing.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from chatbot.api.dependencies import verify_api_key
from chatbot.api.models.requests import WorkspaceCreate, WorkspaceUpdate

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_report_dir() -> Path:
    from chatbot.config import get_settings
    cfg = get_settings().system.report_dir
    p = Path(cfg)
    return p if p.is_absolute() else Path(__file__).parent.parent.parent.parent / cfg


def _workspaces_path() -> Path:
    return _get_report_dir() / ".workspaces.json"


def _load() -> List[Dict]:
    p = _workspaces_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(workspaces: List[Dict]) -> None:
    p = _workspaces_path()
    p.write_text(json.dumps(workspaces, indent=2), encoding="utf-8")


def _validate_archs(names: List[str]) -> None:
    """Raise 400 if any architecture name does not exist as a report directory."""
    report_dir = _get_report_dir()
    unknown = [n for n in names if not (report_dir / n).is_dir()]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown architecture(s): {', '.join(unknown)}",
        )


def _arch_metrics(arch_name: str) -> Dict[str, Any]:
    """Return lightweight metrics for one architecture (fast path — minimal reads)."""
    report_dir = _get_report_dir()
    gt_path  = report_dir / arch_name / "ground_truth.json"
    gov_path = report_dir / arch_name / "governance_signals.json"

    metrics: Dict[str, Any] = {
        "name": arch_name,
        "risk_score": None,
        "defensibility": None,
        "confidence": None,
        "controls_missing": [],
        "techniques": [],
        "aivss_overall": None,
        "aivss_severity": None,
        "redesign_signal": False,
    }

    if gt_path.exists():
        try:
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
            metrics["risk_score"]      = gt.get("expected_risk_score")
            metrics["defensibility"]   = gt.get("expected_defensibility")
            metrics["confidence"]      = gt.get("confidence")
            metrics["controls_missing"] = (gt.get("controls_missing") or [])[:15]
            # Flatten techniques from attack paths
            techs: List[str] = []
            for ap in (gt.get("expected_attack_paths") or []):
                techs.extend(ap.get("techniques") or [])
            metrics["techniques"] = sorted(set(techs))[:20]
        except Exception:
            pass

    if gov_path.exists():
        try:
            gov = json.loads(gov_path.read_text(encoding="utf-8"))
            aivss = gov.get("aivss") or {}
            overall = aivss.get("overall") or {}
            metrics["aivss_overall"]   = overall.get("composite")
            metrics["aivss_severity"]  = overall.get("severity")
        except Exception:
            pass

    sm_path = report_dir / arch_name / "08_scrum_master.json"
    if sm_path.exists():
        try:
            sm = json.loads(sm_path.read_text(encoding="utf-8"))
            metrics["redesign_signal"] = bool(sm.get("redesign_signal"))
        except Exception:
            pass

    return metrics


def _aggregate(member_metrics: List[Dict]) -> Dict[str, Any]:
    """Compute workspace-level aggregate from per-arch metrics."""
    valid_risk  = [m["risk_score"]    for m in member_metrics if m["risk_score"]    is not None]
    valid_def   = [m["defensibility"] for m in member_metrics if m["defensibility"] is not None]
    valid_aivss = [m["aivss_overall"] for m in member_metrics if m["aivss_overall"] is not None]

    # Shared techniques = intersection across all members that have techniques
    tech_sets = [set(m["techniques"]) for m in member_metrics if m["techniques"]]
    shared_techniques = sorted(tech_sets[0].intersection(*tech_sets[1:])) if tech_sets else []

    # Common controls missing = intersection
    cm_sets = [set(m["controls_missing"]) for m in member_metrics if m["controls_missing"]]
    common_controls_missing = sorted(cm_sets[0].intersection(*cm_sets[1:])) if cm_sets else []

    redesign_count = sum(1 for m in member_metrics if m.get("redesign_signal"))

    return {
        "avg_risk_score":         round(sum(valid_risk)  / len(valid_risk),  1) if valid_risk  else None,
        "avg_defensibility":      round(sum(valid_def)   / len(valid_def),   3) if valid_def   else None,
        "avg_aivss":              round(sum(valid_aivss) / len(valid_aivss), 2) if valid_aivss else None,
        "shared_techniques":      shared_techniques[:10],
        "common_controls_missing": common_controls_missing[:10],
        "redesign_count":         redesign_count,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_workspaces() -> Dict:
    """List all workspaces with per-member metrics and aggregate heat scores.

    No auth required — read-only, no secrets exposed.
    """
    workspaces = _load()
    result = []
    for ws in workspaces:
        members_detail = [_arch_metrics(a) for a in (ws.get("architectures") or [])]
        result.append({
            **ws,
            "member_count": len(ws.get("architectures", [])),
            "member_details": members_detail,
            "aggregate": _aggregate(members_detail),
        })
    return {"workspaces": result, "total": len(result)}


@router.post("", status_code=201)
async def create_workspace(
    payload: WorkspaceCreate,
    _: str = Depends(verify_api_key),
) -> Dict:
    """Create a new workspace."""
    workspaces = _load()
    if any(w["name"] == payload.name for w in workspaces):
        raise HTTPException(status_code=409, detail=f"Workspace '{payload.name}' already exists")

    _validate_archs(payload.architectures)

    ws = {
        "name":          payload.name,
        "description":   payload.description,
        "domain":        payload.domain,
        "architectures": payload.architectures,
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }
    workspaces.append(ws)
    _save(workspaces)
    return ws


@router.put("/{workspace_name}")
async def update_workspace(
    workspace_name: str,
    payload: WorkspaceUpdate,
    _: str = Depends(verify_api_key),
) -> Dict:
    """Update description, domain, or architectures of an existing workspace."""
    workspaces = _load()
    for ws in workspaces:
        if ws["name"] == workspace_name:
            if payload.description is not None:
                ws["description"] = payload.description
            if payload.domain is not None:
                ws["domain"] = payload.domain
            if payload.architectures is not None:
                _validate_archs(payload.architectures)
                ws["architectures"] = payload.architectures
            _save(workspaces)
            return ws
    raise HTTPException(status_code=404, detail=f"Workspace '{workspace_name}' not found")


@router.delete("/{workspace_name}")
async def delete_workspace(
    workspace_name: str,
    _: str = Depends(verify_api_key),
) -> Dict:
    """Delete a workspace (does not delete the underlying architecture reports)."""
    workspaces = _load()
    remaining = [w for w in workspaces if w["name"] != workspace_name]
    if len(remaining) == len(workspaces):
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_name}' not found")
    _save(remaining)
    return {"deleted": workspace_name}
