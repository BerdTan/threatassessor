"""
Reports API Routes

Endpoints for accessing generated analysis reports.
"""

import io
import json
import shutil
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from typing import List, Dict
from chatbot.api.dependencies import verify_api_key
from chatbot.modules.mitre import MitreHelper, get_mitre_helper as _get_mitre_singleton
from chatbot.modules.atlas_helper import get_atlas_helper as _get_atlas_singleton

router = APIRouter(prefix="/api/v1", tags=["reports"])

def get_mitre_helper() -> MitreHelper:
    """Return the shared MITRE singleton."""
    return _get_mitre_singleton()


def get_report_dir() -> Path:
    """Get the base reports directory (from config, relative to project root or absolute)."""
    from chatbot.config import get_settings
    cfg_dir = get_settings().system.report_dir
    p = Path(cfg_dir)
    if p.is_absolute():
        return p
    return Path(__file__).parent.parent.parent.parent / cfg_dir


@router.get("/reports")
async def list_architectures():
    """
    List all architectures that have generated reports.

    Returns:
        List of architecture names with report counts

    Example:
        ```json
        {
          "architectures": [
            {
              "name": "web_app",
              "report_count": 4,
              "files": ["01_executive_summary.md", "02_technical_report.md", ...]
            }
          ],
          "total": 5
        }
        ```
    """
    report_dir = get_report_dir()

    if not report_dir.exists():
        return {"architectures": [], "total": 0}

    architectures = []
    for arch_dir in report_dir.iterdir():
        if arch_dir.is_dir() and not arch_dir.name.startswith('.'):
            files = []
            for file in arch_dir.iterdir():
                if file.is_file() and (file.suffix in ['.md', '.json', '.txt']):
                    files.append(file.name)

            if files:  # Only include if has report files
                # Read ssp_profile from ground_truth metadata
                ssp_profile = None
                gt_path = arch_dir / "ground_truth.json"
                if gt_path.exists():
                    try:
                        gt = json.loads(gt_path.read_text())
                        ssp_profile = (gt.get("metadata") or {}).get("ssp_profile")
                    except Exception:
                        pass
                architectures.append({
                    "name": arch_dir.name,
                    "report_count": len(files),
                    "files": sorted(files),
                    "analysed_at": int(arch_dir.stat().st_mtime),
                    "ssp_profile": ssp_profile,
                })

    # Sort newest first
    architectures.sort(key=lambda x: x['analysed_at'], reverse=True)

    return {
        "architectures": architectures,
        "total": len(architectures)
    }


@router.get("/reports/{architecture_name}")
async def list_reports(architecture_name: str):
    """
    List all report files for a specific architecture.

    Args:
        architecture_name: Architecture directory name

    Returns:
        List of report files with metadata

    Example:
        ```json
        {
          "architecture": "web_app",
          "reports": [
            {
              "filename": "01_executive_summary.md",
              "type": "markdown",
              "size": 12345,
              "url": "/api/v1/reports/web_app/files/01_executive_summary.md"
            }
          ]
        }
        ```
    """
    report_dir = get_report_dir() / architecture_name

    if not report_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Architecture '{architecture_name}' not found"
        )

    reports = []
    for file in report_dir.iterdir():
        if file.is_file():
            file_type = "json" if file.suffix == ".json" else \
                       "markdown" if file.suffix == ".md" else \
                       "mermaid" if file.suffix == ".mmd" else \
                       "text"

            reports.append({
                "filename": file.name,
                "type": file_type,
                "size": file.stat().st_size,
                "url": f"/api/v1/reports/{architecture_name}/files/{file.name}"
            })

    # Sort: ground_truth.json first, then numbered reports, then others
    def sort_key(item):
        name = item['filename']
        if name == 'ground_truth.json':
            return (0, name)
        elif name.startswith('0') and name[1].isdigit():
            return (1, name)
        else:
            return (2, name)

    reports.sort(key=sort_key)

    return {
        "architecture": architecture_name,
        "reports": reports,
        "count": len(reports)
    }


@router.post("/reports/{architecture_name}/add-to-adr")
async def add_sm_action_to_adr(
    architecture_name: str,
    payload: dict,
    _: str = Depends(verify_api_key),
):
    """Append a ScrumMaster action item as a new SM-ADR entry in 10_adr_report.md.

    Body: {"action": str, "rationale": str, "priority": str, "first_step": str}
    """
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    report_dir = get_report_dir() / architecture_name
    adr_path = report_dir / "10_adr_report.md"

    action    = str(payload.get("action",    "")).strip()
    rationale = str(payload.get("rationale", "")).strip()
    priority  = str(payload.get("priority",  "high")).strip()
    first_step = str(payload.get("first_step","")).strip()

    if not action:
        raise HTTPException(status_code=400, detail="action is required")

    # Read existing ADR to find highest SM-ADR-XX index
    existing = ""
    if adr_path.exists():
        existing = adr_path.read_text(encoding="utf-8")

    import re
    existing_indices = [int(m) for m in re.findall(r"SM-ADR-(\d+)", existing)]
    next_idx = (max(existing_indices) + 1) if existing_indices else 1
    entry_id = f"SM-ADR-{next_idx:02d}"

    import datetime
    entry = (
        f"\n\n## {entry_id} [{priority.upper()}] — {action}\n\n"
        f"**Status:** OPEN — added via ScrumMaster action plan  \n"
        f"**Added:** {datetime.date.today().isoformat()}  \n"
        f"**Source:** ScrumMaster harmony synthesis\n\n"
        + (f"**Context:** {rationale}\n\n" if rationale else "")
        + (f"**First step:** {first_step}\n\n" if first_step else "")
        + "_→ Verify this control is reflected in the architecture diagram and re-run analysis to confirm coverage._\n\n---\n"
    )

    with open(adr_path, "a", encoding="utf-8") as f:
        f.write(entry)

    return {"status": "ok", "entry_id": entry_id, "architecture": architecture_name}


@router.delete("/reports/{architecture_name}")
async def delete_report(architecture_name: str, _: str = Depends(verify_api_key)):
    """
    Delete the report folder for an architecture.

    Args:
        architecture_name: Architecture directory name

    Returns:
        Confirmation message

    Raises:
        404: If architecture not found
        400: If name contains path traversal attempts
    """
    if '..' in architecture_name or '/' in architecture_name or '\\' in architecture_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid architecture name")

    report_dir = get_report_dir() / architecture_name

    if not report_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Architecture '{architecture_name}' not found")

    shutil.rmtree(report_dir)
    return {"deleted": architecture_name}


@router.get("/reports/{architecture_name}/files/{filename}")
async def get_report_file(architecture_name: str, filename: str):
    """
    Download a specific report file.

    Args:
        architecture_name: Architecture directory name
        filename: Report filename (e.g., "01_executive_summary.md")

    Returns:
        File contents (text/markdown for .md, application/json for .json)

    Raises:
        404: If architecture or file not found
        400: If filename contains path traversal attempts
    """
    # Security: prevent path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename"
        )

    file_path = get_report_dir() / architecture_name / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{filename}' not found for architecture '{architecture_name}'"
        )

    # Determine media type
    if filename.endswith('.json'):
        media_type = "application/json"
    elif filename.endswith('.md'):
        media_type = "text/markdown"
    else:
        media_type = "text/plain"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename
    )


@router.get("/reports/{architecture_name}/summary")
async def get_report_summary(architecture_name: str):
    """
    Get a quick summary of available reports for an architecture.

    Returns metadata without file contents (faster than listing all files).

    Args:
        architecture_name: Architecture directory name

    Returns:
        Summary with file counts and types
    """
    report_dir = get_report_dir() / architecture_name

    if not report_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Architecture '{architecture_name}' not found"
        )

    summary = {
        "architecture": architecture_name,
        "has_ground_truth": (report_dir / "ground_truth.json").exists(),
        "markdown_reports": [],
        "json_files": [],
        "other_files": []
    }

    for file in report_dir.iterdir():
        if file.is_file():
            if file.suffix == '.md':
                summary["markdown_reports"].append(file.name)
            elif file.suffix == '.json':
                summary["json_files"].append(file.name)
            else:
                summary["other_files"].append(file.name)

    summary["total_files"] = (
        len(summary["markdown_reports"]) +
        len(summary["json_files"]) +
        len(summary["other_files"])
    )

    return summary


@router.get("/reports/{architecture_name}/download")
async def download_reports_zip(architecture_name: str, pack: str = "full"):
    """
    Download report files as a ZIP archive.

    Args:
        architecture_name: Architecture directory name
        pack: "stakeholder" (decision-facing docs) or "full" (all non-suppressed files)

    Returns:
        ZIP file stream
    """
    report_dir = get_report_dir() / architecture_name

    if not report_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Architecture '{architecture_name}' not found"
        )

    # README is internal noise, excluded from all packs
    SUPPRESSED = {'README.md'}

    # Stakeholder pack: decision-facing markdown + diagrams only
    STAKEHOLDER = {
        '01_executive_summary.md', '03_action_plan.md', '08_improvement_summary.md',
        'before.mmd', 'after.mmd'
    }

    # JSON pack: all JSON files for raw-data tab download
    JSON_EXTS = {'.json'}

    # Reports pack: markdown + mermaid only (no JSON)
    REPORTS_EXTS = {'.md', '.mmd'}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(report_dir.iterdir()):
            if not file.is_file():
                continue
            if file.name in SUPPRESSED:
                continue
            if pack == 'stakeholder' and file.name not in STAKEHOLDER:
                continue
            if pack == 'json' and file.suffix not in JSON_EXTS:
                continue
            if pack == 'reports' and file.suffix not in REPORTS_EXTS:
                continue
            zf.write(file, arcname=file.name)

    buf.seek(0)
    filename = f"{architecture_name}_{pack}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/reports/{architecture_name}/briefing")
async def get_briefing(architecture_name: str, fmt: str = "md"):
    """
    Export a self-contained two-page briefing for offline sharing.

    Distils the full analysis into a single Markdown document covering:
    - Architecture snapshot (type, primary actor, trust boundaries at risk)
    - Risk waterfall (before → after controls)
    - Top-3 critical findings with confidence labels
    - Expert consensus strip (critic name, status, key gap)
    - Improvement tiers (quick win / recommended / maximum)
    - Blindspots and supply chain / BCP flags
    - Action checklist

    Args:
        architecture_name: Architecture directory name
        fmt: "md" (default) for Markdown plain text

    Returns:
        text/markdown attachment
    """
    import datetime
    report_dir = get_report_dir() / architecture_name

    if not report_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Architecture '{architecture_name}' not found"
        )

    # Load ground truth
    gt_path = report_dir / "ground_truth.json"
    if not gt_path.exists():
        raise HTTPException(status_code=404, detail="ground_truth.json not found — run analysis first")
    with open(gt_path) as f:
        gt = json.load(f)

    # Load MoE orchestrator output (optional — expert review may not have run)
    moe = None
    moe_path = report_dir / "07_moe_orchestrator.json"
    if moe_path.exists():
        with open(moe_path) as f:
            moe = json.load(f)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _s(v, fallback="—"):
        return str(v).strip() if v else fallback

    def _pct(v):
        try:
            return f"{float(v):.0f}%"
        except Exception:
            return "—"

    def _tier_row(t, label):
        if not t:
            return ""
        items = t.get("items", [])
        effort = _s(t.get("effort"), "not estimated")
        cost   = _s(t.get("cost"), "not estimated")
        resid  = _s(t.get("residual"), "not stated")
        lines  = [f"### {label}", f"- **Effort:** {effort}  |  **Cost:** {cost}"]
        for it in items[:5]:
            lines.append(f"- {it}")
        lines.append(f"- *Residual:* {resid}")
        return "\n".join(lines)

    def _conf_badge(label):
        return "✅ KNOWN" if label == "KNOWN" else "⚠ UNSURE"

    # ── ground truth fields ───────────────────────────────────────────────────
    tm      = gt.get("threat_model", {})
    rrs     = tm.get("residual_risk_summary", {})
    aps     = gt.get("expected_attack_paths", [])
    arch    = gt.get("architecture", architecture_name)

    arch_type      = _s(tm.get("architecture_type"))
    primary_actor  = _s(tm.get("primary_threat_actor"))
    weakness       = _s(tm.get("architecture_weakness"))
    boundaries     = ", ".join(tm.get("trust_boundaries_at_risk", [])) or "—"
    risk_before    = _s(rrs.get("overall_before"))
    risk_after     = _s(rrs.get("overall_after_controls"))
    risk_reduction = _s(rrs.get("risk_reduction_pct"))

    # Top 3 critical APs
    tier_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    top_aps = sorted(aps, key=lambda a: tier_order.get(a.get("criticality_tier",""), 0), reverse=True)[:3]
    ap_lines = []
    for ap in top_aps:
        rs  = ap.get("risk_scenario", {})
        tid = ap.get("adr_id") or (ap.get("adr_ids") or [""])[0] or ""
        ap_lines.append(
            f"| {ap.get('id','?')} | {ap.get('criticality_tier','?')} "
            f"| {_s(rs.get('threat_actor'))} → {_s(rs.get('targeted_asset'))} "
            f"| {_s(rs.get('impact'))} | {tid or '—'} |"
        )

    # ── MoE expert consensus (if available) ──────────────────────────────────
    expert_section = ""
    improvement_section = ""
    blindspot_section = ""

    if moe:
        ev      = moe.get("expert_validations", {})
        adj     = moe.get("confidence", {}).get("adjustments", {})
        cons    = moe.get("consensus_recommendations", {})
        tiers   = moe.get("improvement_options", {})
        bspots  = cons.get("blindspots", [])
        crits   = cons.get("critical", [])
        highs   = cons.get("high", [])
        reviews = cons.get("review", [])

        CRITIC_LABELS = {
            "architect":   "🏛️  Architecture Review (2A)",
            "tester":      "🔬  Coverage Audit (2B)",
            "red_team":    "🎯  Exploit Analysis (2C)",
            "purple_team": "🟣  Purple Team (2D)",
            "blackhat":    "⚔️  Blackhat Cross-Path (2E)",
        }
        STATUS_EMOJI = {"PASS": "✅", "MINOR_GAPS": "⚠️", "MAJOR_GAPS": "🔴", "FAIL": "❌"}

        expert_rows = []
        for key, lbl in CRITIC_LABELS.items():
            v = ev.get(key)
            if not v:
                continue
            status_str = v.get("validation_status", "?")
            emoji = STATUS_EMOJI.get(status_str, "•")
            adj_pct = round((adj.get(key, 0)) * 100, 1)
            adj_str = (f"+{adj_pct}%" if adj_pct > 0 else f"{adj_pct}%") if adj_pct != 0 else "±0%"
            top_gap = (v.get("gaps") or [{}])[0].get("description", "No gaps identified")
            expert_rows.append(f"| {lbl} | {emoji} {status_str} | {adj_str} | {top_gap[:120]}{'…' if len(top_gap) > 120 else ''} |")

        if expert_rows:
            expert_section = (
                "## Expert Consensus\n\n"
                "| Critic | Status | Δ Conf | Top finding |\n"
                "|--------|--------|--------|-------------|\n"
                + "\n".join(expert_rows)
            )

        # Critical / high / review findings
        findings_lines = []
        for f in (crits + highs)[:6]:
            badge = _conf_badge(f.get("confidence_label", "UNSURE"))
            findings_lines.append(f"- **[{f.get('severity','?')}]** {badge}  \n  {f.get('description','')}")
        if reviews:
            findings_lines.append(f"\n*For Review ({len(reviews)} single-critic findings — verify before acting):*")
            for f in reviews[:3]:
                findings_lines.append(f"- {f.get('description','')}")

        if findings_lines:
            expert_section += "\n\n## Key Findings\n\n" + "\n".join(findings_lines)

        # Improvement tiers
        tier_parts = [
            _tier_row(tiers.get("quick_win"),   "⚡ Quick Win"),
            _tier_row(tiers.get("recommended"), "⭐ Recommended"),
            _tier_row(tiers.get("maximum"),     "🔒 Maximum"),
        ]
        tier_parts = [t for t in tier_parts if t]
        if tier_parts:
            improvement_section = "## Improvement Tiers\n\n" + "\n\n".join(tier_parts)

        # Blindspots
        if bspots:
            bs_lines = []
            for b in bspots:
                bs_lines.append(f"- **{b.get('description','')}**  \n  *Why missed:* {b.get('why_missed','')}  \n  *Action:* {b.get('recommendation','')}")
            blindspot_section = "## Structural Blindspots\n\n" + "\n".join(bs_lines)

    # ── action checklist from top APs ────────────────────────────────────────
    adrs = gt.get("architecture_decision_records", [])
    checklist_lines = []
    for ap in top_aps:
        adr_id = ap.get("adr_id") or (ap.get("adr_ids") or [""])[0] or ""
        adr = next((a for a in adrs if a.get("adr_id") == adr_id), None)
        if adr:
            hops = adr.get("hops", [])
            for hop in hops:
                for ctrl in (hop.get("controls") or [])[:2]:
                    pri = ctrl.get("priority", "")
                    if pri in ("critical", "high"):
                        checklist_lines.append(
                            f"- [ ] **{ctrl['control'].upper()}** ({ap.get('id','?')}, {pri}) — {ctrl.get('dir_category','')}"
                        )
    if not checklist_lines:
        checklist_lines = ["- [ ] Run full expert review (MoE) for prioritised action list"]

    # ── assemble document ─────────────────────────────────────────────────────
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# ThreatAssessor Briefing — {arch}",
        f"*Generated: {now}  |  Confidential — internal use*",
        "",
        "---",
        "",
        "## Architecture Snapshot",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Architecture | {arch} |",
        f"| Type | {arch_type} |",
        f"| Primary Threat Actor | {primary_actor} |",
        f"| Biggest Weakness | {weakness} |",
        f"| Trust Boundaries at Risk | {boundaries} |",
        f"| Risk Before Controls | {risk_before} |",
        f"| Risk After Controls | {risk_after} |",
        f"| Estimated Reduction | {risk_reduction}% |" if risk_reduction != "—" else f"| Estimated Reduction | — |",
        "",
        "---",
        "",
        "## Top Attack Paths",
        "",
        "| ID | Tier | Actor → Target | Impact | ADR |",
        "|----|------|----------------|--------|-----|",
        *ap_lines,
        "",
        "---",
        "",
    ]

    if expert_section:
        lines += [expert_section, "", "---", ""]
    if improvement_section:
        lines += [improvement_section, "", "---", ""]
    if blindspot_section:
        lines += [blindspot_section, "", "---", ""]

    lines += [
        "## Action Checklist",
        "",
        *checklist_lines,
        "",
        "---",
        "",
        f"*Full interactive report: run ThreatAssessor dashboard and load architecture `{arch}`.*",
        f"*Expert Review not run yet — start the dashboard and click Run Expert Review for full consensus.*" if not moe else "",
    ]

    doc = "\n".join(l for l in lines)

    filename = f"{architecture_name}_briefing.md"
    return StreamingResponse(
        io.BytesIO(doc.encode()),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/mitigations")
async def get_mitigation_names(mitigation_ids: str = Query(..., description="Comma-separated mitigation IDs (e.g., M1042,M1026,M1037)")):
    """
    Get MITRE ATT&CK mitigation names for given IDs.

    Args:
        mitigation_ids: Comma-separated mitigation IDs

    Returns:
        Dictionary mapping mitigation IDs to names
    """
    mitre = get_mitre_helper()

    ids = [mid.strip() for mid in mitigation_ids.split(',') if mid.strip()]

    if not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No mitigation IDs provided"
        )

    if len(ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many mitigation IDs (max 100)"
        )

    atlas = _get_atlas_singleton()
    result = {}
    for mid in ids:
        if mid.upper().startswith('AML.'):
            mit = atlas.get_mitigation_by_id(mid)
            result[mid] = mit.get('name', f"Unknown ({mid})") if mit else f"Unknown ({mid})"
        else:
            mit = mitre.find_mitigation(mid)
            result[mid] = mit.get('name', 'Unknown') if mit else f"Unknown ({mid})"

    return {"mitigations": result}


@router.get("/technique-mitigations")
async def get_technique_mitigations(technique_ids: str = Query(..., description="Comma-separated technique IDs")):
    """
    Return which MITRE mitigation IDs apply to each given technique ID.

    Returns:
        mappings: { techniqueId: [mitigationId, ...] }
    """
    mitre = get_mitre_helper()
    ids = [tid.strip() for tid in technique_ids.split(',') if tid.strip()]

    if not ids or len(ids) > 50:
        raise HTTPException(status_code=400, detail="Provide 1-50 technique IDs")

    atlas = _get_atlas_singleton()
    mappings = {}
    for tid in ids:
        if tid.upper().startswith('AML.'):
            mits = atlas.get_mitigations_for_technique(tid)
            mappings[tid] = [m.get('id') for m in mits if m.get('id')]
        else:
            mits = mitre.get_technique_mitigations(tid)
            mappings[tid] = [m.get('mitigation_id') for m in mits if m.get('mitigation_id')]

    return {"mappings": mappings}


@router.get("/techniques")
async def get_technique_names(technique_ids: str = Query(..., description="Comma-separated technique IDs (e.g., T1566,T1078,T1059)")):
    """
    Get MITRE ATT&CK technique names for given IDs.

    This reduces API calls and keeps users on dashboard instead of clicking to MITRE site.

    Args:
        technique_ids: Comma-separated technique IDs

    Returns:
        Dictionary mapping technique IDs to names

    Example:
        GET /api/v1/techniques?technique_ids=T1566,T1078,T1059

        Response:
        ```json
        {
          "techniques": {
            "T1566": "Phishing",
            "T1078": "Valid Accounts",
            "T1059": "Command and Scripting Interpreter"
          }
        }
        ```
    """
    mitre = get_mitre_helper()

    ids = [tid.strip() for tid in technique_ids.split(',') if tid.strip()]

    if not ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No technique IDs provided"
        )

    if len(ids) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many technique IDs (max 100)"
        )

    atlas = _get_atlas_singleton()
    result = {}
    for tid in ids:
        if tid.upper().startswith('AML.'):
            name = atlas.get_technique_name(tid)
            result[tid] = name if name != tid else f"Unknown ({tid})"
        else:
            tech = mitre.find_technique(tid)
            result[tid] = tech.get('name', 'Unknown') if tech else f"Unknown ({tid})"

    return {"techniques": result}


@router.get("/insights")
async def get_insights(archs: str = Query(default="", description="Comma-separated architecture names. Empty = current (most recent)")):
    """
    Merged Insights endpoint — returns governance signals (with AIVSS) + ground truth summary
    for one or more architectures.

    Used by the Insights tab (Section A: Input Safety, Section B: Design Patterns).

    Args:
        archs: Comma-separated architecture names. If empty, returns the most recently modified.

    Returns:
        Dict with `architectures` list, each entry containing governance_signals + ground_truth summary.
    """
    report_base = get_report_dir()
    arch_names = [a.strip() for a in archs.split(',') if a.strip()] if archs else []

    if not arch_names:
        # Pick the most recently modified report directory
        try:
            dirs = sorted(
                [d for d in report_base.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            )
            if dirs:
                arch_names = [dirs[0].name]
        except Exception:
            pass

    if not arch_names:
        return {"architectures": []}

    results = []
    for name in arch_names[:10]:  # cap at 10
        safe = Path(name).name
        if safe != name or ".." in name:
            continue
        arch_dir = report_base / safe
        if not arch_dir.is_dir():
            continue

        entry: Dict = {"name": safe}

        gov_path = arch_dir / "governance_signals.json"
        if gov_path.exists():
            try:
                entry["governance_signals"] = json.loads(gov_path.read_text())
            except Exception:
                entry["governance_signals"] = None

        gt_path = arch_dir / "ground_truth.json"
        if gt_path.exists():
            try:
                gt = json.loads(gt_path.read_text())
                # Return lightweight summary only (full GT can be large)
                entry["ground_truth_summary"] = {
                    "architecture_name": gt.get("architecture_name", safe),
                    "expected_risk_score": gt.get("expected_risk_score"),
                    "expected_defensibility": gt.get("expected_defensibility"),
                    "attack_path_count": len(gt.get("expected_attack_paths", [])),
                    "technique_count": sum(
                        len(p.get("techniques", []))
                        for p in gt.get("expected_attack_paths", [])
                    ),
                    "top_threats": [
                        {
                            "id": p.get("id"),
                            "title": p.get("title"),
                            "criticality_tier": p.get("criticality_tier"),
                            "aivss_score": p.get("aivss_score"),
                            "aivss_severity": p.get("aivss_severity"),
                        }
                        for p in (gt.get("expected_attack_paths", []))[:5]
                    ],
                }
            except Exception:
                entry["ground_truth_summary"] = None

        results.append(entry)

    return {"architectures": results}
