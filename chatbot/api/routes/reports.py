"""
Reports API Routes

Endpoints for accessing generated analysis reports.
"""

import datetime
import io
import json
import re
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


_SM_RE = re.compile(r'^(.+?)_sm(\d+)$')


def resolve_arch_dir(architecture_name: str) -> Path:
    """Resolve an architecture name to its report directory.

    Handles both flat names (aivss_test_arch → report/aivss_test_arch/)
    and SM worktree names (aivss_test_arch_sm1 → report/aivss_test_arch/sm1/).
    Falls back to the flat path so callers get a consistent Path (may not exist).
    """
    base = get_report_dir()
    flat = base / architecture_name
    if flat.exists():
        return flat
    m = _SM_RE.match(architecture_name)
    if m:
        subfolder = base / m.group(1) / f"sm{m.group(2)}"
        if subfolder.exists():
            return subfolder
    return flat


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
                # Count SM reruns (subdirs named sm\d+)
                sm_runs = sorted(
                    int(p.name[2:]) for p in arch_dir.iterdir()
                    if p.is_dir() and p.name.startswith("sm") and p.name[2:].isdigit()
                )
                architectures.append({
                    "name": arch_dir.name,
                    "report_count": len(files),
                    "files": sorted(files),
                    "analysed_at": int(arch_dir.stat().st_mtime),
                    "ssp_profile": ssp_profile,
                    "has_scrum_master": (arch_dir / "08_scrum_master.json").exists(),
                    "sm_run_count": len(sm_runs),
                    "sm_runs": sm_runs,
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
    report_dir = resolve_arch_dir(architecture_name)

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


@router.post("/reports/{architecture_name}/rerun-with-sm")
async def rerun_with_sm(
    architecture_name: str,
    _: str = Depends(verify_api_key),
):
    """Create an SM worktree rerun: copies 08b_recommended_target.mmd into
    a new sm{N}/ subfolder, runs api_only analysis, then writes run_diff.json
    comparing the result against the original base arch ground_truth.json.

    Returns the new SM run number and basic delta metrics.
    """
    import asyncio
    import queue
    import time as _time

    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    base_dir = get_report_dir() / architecture_name
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail=f"Architecture '{architecture_name}' not found")

    sm_mmd = base_dir / "08b_recommended_target.mmd"
    if not sm_mmd.exists():
        raise HTTPException(status_code=404,
            detail="08b_recommended_target.mmd not found — run Expert Review with ScrumMaster first")

    # Determine next SM run index
    existing = sorted(
        int(p.name[2:]) for p in base_dir.iterdir()
        if p.is_dir() and p.name.startswith("sm") and p.name[2:].isdigit()
    )
    n = (existing[-1] + 1) if existing else 1
    sm_dir = base_dir / f"sm{n}"
    sm_dir.mkdir(parents=True, exist_ok=True)

    # Clean the annotation-style MMD into an analysis-ready one.
    # The recommended MMD has NEW_* nodes with MITRE/RAPIDS metadata in
    # labels — clean_recommended_mmd() strips the metadata, renames nodes
    # to readable IDs, and removes comment/style lines so the analysis
    # engine sees a proper architecture graph, not an annotation file.
    annotation_text = sm_mmd.read_text(encoding="utf-8")
    try:
        from chatbot.modules.mmd_cleaner import clean_recommended_mmd
        clean_text = clean_recommended_mmd(annotation_text)
    except Exception:
        clean_text = annotation_text  # fallback: use as-is

    # Preserve the original annotation as a template for the architect
    (sm_dir / "recommended_template.mmd").write_text(annotation_text, encoding="utf-8")
    # Write the clean version as before.mmd (what the engine analyses)
    (sm_dir / "before.mmd").write_text(clean_text, encoding="utf-8")

    # Write the clean MMD to a temp file for the harness
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False,
                                     encoding="utf-8") as tmp:
        tmp.write(clean_text)
        tmp_path = tmp.name

    # arch_sm_name is used as the architecture_name kwarg passed to the harness.
    # generate_report_package appends this name onto output_dir (the parent of
    # sm_dir), so it must be just "sm{N}" so files land in sm_dir/ not
    # sm_dir/{architecture_name}_sm{N}/.
    arch_sm_name = f"sm{n}"

    # Read SSP profile from base arch ground_truth if available
    ssp_profile = "low_risk_cloud"
    base_gt_path = base_dir / "ground_truth.json"
    if base_gt_path.exists():
        try:
            _gt = json.loads(base_gt_path.read_text(encoding="utf-8"))
            ssp_profile = _gt.get("ssp_profile") or _gt.get("metadata", {}).get("ssp_profile") or ssp_profile
        except Exception:
            pass

    try:
        from chatbot.modules.harness import ThreatAssessorHarness, ScenarioConfig

        q: queue.SimpleQueue = queue.SimpleQueue()

        def _cb(stage: str, pct: int, msg: str) -> None:
            q.put((stage, pct, msg))

        harness = ThreatAssessorHarness(
            scenario=ScenarioConfig.API_ONLY,
            progress_callback=_cb,
        )

        loop = asyncio.get_event_loop()
        ctx = await loop.run_in_executor(
            None,
            lambda: harness.run(
                architecture_path=tmp_path,
                report_dir=str(sm_dir),
                ssp_profile=ssp_profile,
                enable_ssp=True,
                include_validation=True,
                architecture_name=arch_sm_name,
            )
        )

        import os
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if ctx.stage_outputs.get("analysis") == "error":
            raise HTTPException(status_code=500,
                detail=ctx.errors[0] if ctx.errors else "Analysis failed")

        # Clean any NEW_* annotation nodes from MMDs generated by the harness
        # (after.mmd, after_bh.mmd, 08a/b/c_*.mmd).  recommended_template.mmd
        # is intentionally kept annotated as the architect's reference.
        try:
            from chatbot.modules.mmd_cleaner import clean_recommended_mmd
            _KEEP_ANNOTATED = {"recommended_template.mmd"}
            for mmd_path in sm_dir.glob("*.mmd"):
                if mmd_path.name in _KEEP_ANNOTATED:
                    continue
                raw = mmd_path.read_text(encoding="utf-8")
                if "NEW_" in raw:
                    mmd_path.write_text(clean_recommended_mmd(raw), encoding="utf-8")
        except Exception:
            pass  # non-fatal — diagrams may have parse errors but analysis is intact

        # Write run_diff.json — compare sm{N}/ground_truth vs base ground_truth
        diff = _compute_sm_diff(base_dir, sm_dir, n, architecture_name)
        (sm_dir / "run_diff.json").write_text(
            json.dumps(diff, indent=2), encoding="utf-8"
        )

        return {
            "status": "ok",
            "architecture": architecture_name,
            "n": n,
            "sm_dir": f"{architecture_name}/sm{n}",
            "diff": diff,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SM rerun failed: {e}")


def _compute_sm_diff(base_dir: Path, sm_dir: Path, n: int, arch_name: str) -> dict:
    """Compare sm{N}/ground_truth.json against base arch ground_truth.json.
    Always diffs against the original base — never against a previous SM run.
    """
    base_gt_path = base_dir / "ground_truth.json"
    sm_gt_path   = sm_dir   / "ground_truth.json"

    if not base_gt_path.exists() or not sm_gt_path.exists():
        return {"error": "ground_truth.json missing in base or SM run"}

    base_gt = json.loads(base_gt_path.read_text(encoding="utf-8"))
    sm_gt   = json.loads(sm_gt_path.read_text(encoding="utf-8"))

    base_controls  = set(c.lower().strip() for c in (base_gt.get("controls_missing") or []))
    sm_controls    = set(c.lower().strip() for c in (sm_gt.get("controls_missing")   or []))
    base_techs     = set(base_gt.get("techniques") or [])
    sm_techs       = set(sm_gt.get("techniques")   or [])

    controls_resolved = sorted(base_controls - sm_controls)
    controls_new      = sorted(sm_controls - base_controls)
    techniques_closed = sorted(base_techs - sm_techs)
    techniques_new    = sorted(sm_techs - base_techs)

    base_conf = float(base_gt.get("confidence") or 0)
    sm_conf   = float(sm_gt.get("confidence")   or 0)

    return {
        "base_arch":          arch_name,
        "sm_n":               n,
        "base_confidence":    round(base_conf, 4),
        "sm_confidence":      round(sm_conf, 4),
        "confidence_delta":   round(sm_conf - base_conf, 4),
        "controls_resolved":  controls_resolved,
        "controls_new":       controls_new,
        "techniques_closed":  techniques_closed,
        "techniques_new":     techniques_new,
        "controls_resolved_count":  len(controls_resolved),
        "techniques_closed_count":  len(techniques_closed),
    }


@router.get("/reports/{architecture_name}/sm")
async def list_sm_reruns(architecture_name: str):
    """List all SM reruns for an architecture with diff metrics."""
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    base_dir = get_report_dir() / architecture_name
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail=f"Architecture '{architecture_name}' not found")

    runs = []
    for p in sorted(base_dir.iterdir()):
        if not (p.is_dir() and p.name.startswith("sm") and p.name[2:].isdigit()):
            continue
        n = int(p.name[2:])
        entry: Dict = {"n": n, "dir": f"{architecture_name}/sm{n}"}

        diff_path = p / "run_diff.json"
        if diff_path.exists():
            try:
                entry.update(json.loads(diff_path.read_text(encoding="utf-8")))
            except Exception:
                pass

        gt_path = p / "ground_truth.json"
        if gt_path.exists():
            try:
                gt = json.loads(gt_path.read_text(encoding="utf-8"))
                entry.setdefault("sm_confidence", gt.get("confidence"))
            except Exception:
                pass

        # Run timestamp from harness_perf.json
        perf_path = p / "harness_perf.json"
        if perf_path.exists():
            try:
                perf = json.loads(perf_path.read_text(encoding="utf-8"))
                entry["run_ts"] = perf.get("run_ts", "")
            except Exception:
                pass

        runs.append(entry)

    return {"architecture": architecture_name, "sm_runs": runs}


@router.get("/reports/{architecture_name}/sm/{n}/files/{filename}")
async def get_sm_file(architecture_name: str, n: int, filename: str):
    """Serve a file from an SM worktree subfolder."""
    safe_arch = Path(architecture_name).name
    safe_file = Path(filename).name
    if safe_arch != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")
    if safe_file != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = get_report_dir() / architecture_name / f"sm{n}" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404,
            detail=f"File '{filename}' not found in sm{n} for '{architecture_name}'")

    media_type = "application/json" if filename.endswith(".json") else \
                 "text/markdown"    if filename.endswith(".md")   else "text/plain"
    return FileResponse(path=file_path, media_type=media_type,
                        filename=filename, headers={"Cache-Control": "no-cache"})


@router.get("/reports/{architecture_name}/sm/{n}/diff")
async def get_sm_diff(architecture_name: str, n: int):
    """Return run_diff.json for a specific SM run."""
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    diff_path = get_report_dir() / architecture_name / f"sm{n}" / "run_diff.json"
    if not diff_path.exists():
        raise HTTPException(status_code=404, detail=f"run_diff.json not found for sm{n}")

    return json.loads(diff_path.read_text(encoding="utf-8"))


@router.delete("/reports/{architecture_name}/sm/{n}")
async def delete_sm_run(
    architecture_name: str,
    n: int,
    _: str = Depends(verify_api_key),
):
    """Delete an SM worktree subfolder."""
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    sm_dir = get_report_dir() / architecture_name / f"sm{n}"
    if not sm_dir.exists():
        raise HTTPException(status_code=404, detail=f"sm{n} not found for '{architecture_name}'")

    import shutil as _shutil
    _shutil.rmtree(sm_dir)
    return {"status": "ok", "deleted": f"{architecture_name}/sm{n}"}


@router.post("/reports/{architecture_name}/sm/{n}/rerun")
async def rerun_sm_analysis(
    architecture_name: str,
    n: int,
    _: str = Depends(verify_api_key),
):
    """Re-run api_only analysis on an existing SM run's before.mmd.

    Refreshes ground_truth.json, governance_signals.json, and run_diff.json
    without creating a new SM subfolder. Useful after manually editing before.mmd.
    """
    import asyncio, queue as _queue
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    base_dir = get_report_dir() / architecture_name
    sm_dir   = base_dir / f"sm{n}"
    mmd_path = sm_dir / "before.mmd"

    if not sm_dir.exists():
        raise HTTPException(status_code=404, detail=f"sm{n} not found")
    if not mmd_path.exists():
        raise HTTPException(status_code=404, detail="before.mmd not found in sm subfolder")

    import tempfile, os
    clean_text = mmd_path.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile(suffix=".mmd", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(clean_text)
        tmp_path = tmp.name

    ssp_profile = "low_risk_cloud"
    base_gt = base_dir / "ground_truth.json"
    if base_gt.exists():
        try:
            _gt = json.loads(base_gt.read_text(encoding="utf-8"))
            ssp_profile = _gt.get("ssp_profile") or _gt.get("metadata", {}).get("ssp_profile") or ssp_profile
        except Exception:
            pass

    try:
        from chatbot.modules.harness import ThreatAssessorHarness, ScenarioConfig
        q: _queue.SimpleQueue = _queue.SimpleQueue()
        harness = ThreatAssessorHarness(
            scenario=ScenarioConfig.API_ONLY,
            progress_callback=lambda s, p, m: q.put((s, p, m)),
        )
        loop = asyncio.get_event_loop()
        ctx = await loop.run_in_executor(
            None,
            lambda: harness.run(
                architecture_path=tmp_path,
                report_dir=str(sm_dir),
                ssp_profile=ssp_profile,
                enable_ssp=True,
                include_validation=True,
                architecture_name=f"sm{n}",
            )
        )
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if ctx.stage_outputs.get("analysis") == "error":
            raise HTTPException(status_code=500,
                detail=ctx.errors[0] if ctx.errors else "Analysis failed")

        # Clean generated MMDs
        try:
            from chatbot.modules.mmd_cleaner import clean_recommended_mmd as _clean
            _KEEP = {"recommended_template.mmd", "before.mmd"}
            for p in sm_dir.glob("*.mmd"):
                if p.name not in _KEEP and "NEW_" in p.read_text(encoding="utf-8"):
                    p.write_text(_clean(p.read_text(encoding="utf-8")), encoding="utf-8")
        except Exception:
            pass

        diff = _compute_sm_diff(base_dir, sm_dir, n, architecture_name)
        (sm_dir / "run_diff.json").write_text(json.dumps(diff, indent=2), encoding="utf-8")

        return {"status": "ok", "n": n, "diff": diff}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SM rerun failed: {e}")


@router.post("/reports/{architecture_name}/add-to-adr")
async def add_sm_action_to_adr(
    architecture_name: str,
    payload: dict,
    _: str = Depends(verify_api_key),
):
    """Append a ScrumMaster action item as a new SM-ADR entry in 10_adr_report.md.

    Body: {
        "action": str, "rationale": str, "priority": str, "first_step": str,
        "source_techniques": list[str],  # e.g. ["T1078", "T1213"] — for diff-based verification
        "source_controls":   list[str],  # e.g. ["micro-segmentation"] — matched against controls_missing
    }
    """
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    report_dir = get_report_dir() / architecture_name
    adr_path = report_dir / "10_adr_report.md"

    action     = str(payload.get("action",    "")).strip()
    rationale  = str(payload.get("rationale", "")).strip()
    priority   = str(payload.get("priority",  "high")).strip()
    first_step = str(payload.get("first_step","")).strip()
    source_techniques = [str(t).strip() for t in (payload.get("source_techniques") or []) if t]
    source_controls   = [str(c).strip() for c in (payload.get("source_controls")   or []) if c]

    if not action:
        raise HTTPException(status_code=400, detail="action is required")

    existing = ""
    if adr_path.exists():
        existing = adr_path.read_text(encoding="utf-8")

    existing_indices = [int(m) for m in re.findall(r"SM-ADR-(\d+)", existing)]
    next_idx = (max(existing_indices) + 1) if existing_indices else 1
    entry_id = f"SM-ADR-{next_idx:02d}"

    import datetime
    tech_line = (f"**Source techniques:** {', '.join(source_techniques)}  \n"
                 if source_techniques else "")
    ctrl_line = (f"**Source controls:** {', '.join(source_controls)}  \n"
                 if source_controls else "")

    entry = (
        f"\n\n## {entry_id} [{priority.upper()}] — {action}\n\n"
        f"**Status:** OPEN — added via ScrumMaster action plan  \n"
        f"**Added:** {datetime.date.today().isoformat()}  \n"
        f"**Source:** ScrumMaster harmony synthesis  \n"
        + tech_line
        + ctrl_line
        + "\n"
        + (f"**Context:** {rationale}\n\n" if rationale else "")
        + (f"**First step:** {first_step}\n\n" if first_step else "")
        + "_→ Run SM rerun (✨ Re-run with SM) to verify this control is resolved._\n\n---\n"
    )

    with open(adr_path, "a", encoding="utf-8") as f:
        f.write(entry)

    return {"status": "ok", "entry_id": entry_id, "architecture": architecture_name}


@router.post("/reports/{architecture_name}/add-all-to-adr")
async def add_all_sm_actions_to_adr(
    architecture_name: str,
    _: str = Depends(verify_api_key),
):
    """Batch-append all non-antipattern ScrumMaster actions to 10_adr_report.md.

    Reads 08_scrum_master.json, skips items where is_antipattern is True,
    skips duplicates (action text already present in ADR), and appends the
    rest as SM-ADR-XX entries in a single atomic write.

    Returns:
        {"status":"ok","added":N,"skipped_antipattern":M,"skipped_duplicate":K,"entry_ids":[...]}
    """
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    report_dir = get_report_dir() / architecture_name
    sm_path  = report_dir / "08_scrum_master.json"
    adr_path = report_dir / "10_adr_report.md"

    if not sm_path.exists():
        raise HTTPException(status_code=404, detail="08_scrum_master.json not found — run Expert Review first")

    sm_data = json.loads(sm_path.read_text(encoding="utf-8"))
    action_plan = sm_data.get("action_plan") or []

    existing = adr_path.read_text(encoding="utf-8") if adr_path.exists() else ""
    existing_indices = [int(m) for m in re.findall(r"SM-ADR-(\d+)", existing)]
    next_idx = (max(existing_indices) + 1) if existing_indices else 1

    import datetime
    today = datetime.date.today().isoformat()

    batch_buffer = ""
    entry_ids: list[str] = []
    skipped_antipattern = 0
    skipped_duplicate = 0

    for item in action_plan:
        if item.get("is_antipattern") is True:
            skipped_antipattern += 1
            continue
        action = str(item.get("action", "")).strip()
        if not action:
            continue
        if action[:60].lower() in existing.lower():
            skipped_duplicate += 1
            continue

        rationale  = str(item.get("rationale",  "")).strip()
        priority   = str(item.get("priority",   "high")).strip()
        first_step = str(item.get("first_step", "")).strip()
        source_techniques = [str(t).strip() for t in (item.get("source_techniques") or []) if t]
        source_controls   = [str(c).strip() for c in (item.get("source_controls")   or []) if c]

        entry_id = f"SM-ADR-{next_idx:02d}"
        tech_line = (f"**Source techniques:** {', '.join(source_techniques)}  \n" if source_techniques else "")
        ctrl_line = (f"**Source controls:** {', '.join(source_controls)}  \n"     if source_controls   else "")

        batch_buffer += (
            f"\n\n## {entry_id} [{priority.upper()}] — {action}\n\n"
            f"**Status:** OPEN — added via ScrumMaster action plan  \n"
            f"**Added:** {today}  \n"
            f"**Source:** ScrumMaster harmony synthesis  \n"
            + tech_line + ctrl_line + "\n"
            + (f"**Context:** {rationale}\n\n" if rationale else "")
            + (f"**First step:** {first_step}\n\n" if first_step else "")
            + "_→ Run SM rerun (✨ Re-run with SM) to verify this control is resolved._\n\n---\n"
        )
        entry_ids.append(entry_id)
        existing += batch_buffer  # keep running text updated for dedup check on subsequent items
        next_idx += 1

    if batch_buffer:
        with open(adr_path, "a", encoding="utf-8") as f:
            f.write(batch_buffer)

    return {
        "status": "ok",
        "added": len(entry_ids),
        "skipped_antipattern": skipped_antipattern,
        "skipped_duplicate": skipped_duplicate,
        "entry_ids": entry_ids,
        "architecture": architecture_name,
    }


@router.post("/reports/{architecture_name}/rescore-aivss")
async def rescore_aivss(
    architecture_name: str,
    _: str = Depends(verify_api_key),
):
    """Re-run AIVSS scoring for an existing report on demand.

    Reads governance_signals.json and ground_truth.json from disk,
    loads moe_result and scrum_master_result if available, runs the
    full three-flow AIVSS scorer, and saves the updated
    governance_signals.json in-place.  Works whether or not MoE has
    been run — governance dims are preserved, only the aivss section
    is replaced.

    Returns the new aivss scores dict.
    """
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    report_dir = resolve_arch_dir(architecture_name)
    if not report_dir.exists():
        raise HTTPException(status_code=404, detail=f"Architecture '{architecture_name}' not found")

    gt_path  = report_dir / "ground_truth.json"
    sig_path = report_dir / "governance_signals.json"

    if not gt_path.exists():
        raise HTTPException(status_code=404, detail="ground_truth.json not found — run analysis first")

    try:
        ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read ground_truth.json: {e}")

    import time as _time
    _timings: Dict[str, float] = {}

    # ── Step 1: Build governance signals ────────────────────────────────────
    _t = _time.perf_counter()
    gov_signals: Dict = {}
    if sig_path.exists():
        try:
            saved = json.loads(sig_path.read_text(encoding="utf-8"))
            saved.pop("aivss", None)
            if any(k in saved for k in ("exploitation", "leakage", "manipulation", "identity", "sovereignty")):
                gov_signals = saved
        except Exception:
            pass

    if not gov_signals:
        mmd_path = report_dir / "before.mmd"
        if mmd_path.exists():
            try:
                from chatbot.harness.governance import InhouseGovernanceAdapter
                mmd_text = mmd_path.read_text(encoding="utf-8")
                adapter = InhouseGovernanceAdapter()
                input_sig  = adapter.check_input(mmd_text, str(mmd_path))
                artifact_sig = adapter.check_artifact(ground_truth)
                merged = input_sig.merge(artifact_sig)
                merged.architecture_name = architecture_name
                gov_signals = merged.to_dict()
            except Exception:
                gov_signals = {}
    _timings["governance"] = round(_time.perf_counter() - _t, 3)

    # ── Step 2: Read saved MoE JSON + derive manipulation signals (no LLM) ──
    # Never call run_moe_pipeline here — that re-runs all LLM critics (~75s).
    # compute_manipulation_signals only needs final_confidence, base_confidence,
    # synthesis_quality, expert_validations — all present in the saved JSON.
    _t = _time.perf_counter()
    moe_dict = None
    moe_path = report_dir / "07_moe_orchestrator.json"
    if moe_path.exists():
        try:
            moe_dict = json.loads(moe_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if moe_dict is not None:
        try:
            from chatbot.harness.governance import compute_manipulation_signals

            # Wrap the raw dict so compute_manipulation_signals can use getattr.
            # The saved JSON stores confidence as a nested dict; flatten to flat attrs.
            class _MoEProxy:
                def __init__(self, d: dict):
                    self._d = d
                    _conf = d.get("confidence", {})
                    self.final_confidence = _conf.get("final") if isinstance(_conf, dict) else d.get("final_confidence")
                    self.base_confidence  = _conf.get("base")  if isinstance(_conf, dict) else d.get("base_confidence")
                    self.synthesis_quality  = d.get("synthesis_quality")
                    self.expert_validations = d.get("expert_validations", {})
                def __getattr__(self, k):
                    return self._d.get(k)

            manip = compute_manipulation_signals(_MoEProxy(moe_dict))
            existing_manip = gov_signals.get("manipulation", {})
            swing = manip.get("confidence_swing", 0.0)
            div   = manip.get("critic_divergence_score", 0)
            existing_manip.update({
                "confidence_swing_detected": swing > 10,
                "divergence_detected":       div > 20,
                "confidence_swing":          swing,
                "critic_divergence_score":   div,
                "synthesis_quality":         manip.get("synthesis_quality", "UNKNOWN"),
                "severity":                  manip.get("severity", "LOW"),
                "arc_categories":            manip.get("arc_categories", []),
                "atlas_tactics":             manip.get("atlas_tactics", []),
                "kill_chain_stage":          manip.get("kill_chain_stage", "llm_layer"),
            })
            gov_signals["manipulation"] = existing_manip
        except Exception:
            pass
    _timings["manipulation"] = round(_time.perf_counter() - _t, 3)

    # ── Step 3: Load SM result if available (JSON read only) ─────────────────
    sm_result = None
    sm_path = report_dir / "08_scrum_master.json"
    if sm_path.exists():
        try:
            sm_data = json.loads(sm_path.read_text(encoding="utf-8"))
            class _SMResult:
                def __init__(self, d):
                    self.retrigger_count = d.get("retrigger_count", 0)
            sm_result = _SMResult(sm_data)
        except Exception:
            pass

    # ── Step 4: Score ────────────────────────────────────────────────────────
    try:
        from chatbot.modules.harness_aivss import AIVSSFlowScorer
        from chatbot.config.settings import get_settings
        _settings = get_settings()

        _t = _time.perf_counter()
        scorer = AIVSSFlowScorer(industry=_settings.governance.industry)
        aivss = scorer.compute(gov_signals, ground_truth, None, sm_result)
        _timings["aivss"] = round(_time.perf_counter() - _t, 3)

        # ── Step 5: Save ─────────────────────────────────────────────────────
        _t = _time.perf_counter()
        gov_signals["aivss"] = aivss.to_dict()
        sig_path.write_text(json.dumps(gov_signals, indent=2), encoding="utf-8")
        _timings["save"] = round(_time.perf_counter() - _t, 4)

        # Write harness_perf.json so the Harness tab stage timeline populates
        import datetime as _dt
        _perf = {
            "run_id":          f"{architecture_name}_rescore_{_dt.datetime.utcnow().strftime('%Y%m%dT%H%M%S')}",
            "run_ts":          _dt.datetime.utcnow().isoformat() + "Z",
            "scenario":        "rescore_aivss",
            "pipeline_wall_s": round(sum(_timings.values()), 3),
            "stages": {
                "quality":      {"wall_s": _timings.get("governance", 0.0),   "status": "ok", "model": None},
                "manipulation": {"wall_s": _timings.get("manipulation", 0.0), "status": "ok", "model": None},
                "aivss":        {"wall_s": _timings.get("aivss", 0.0),        "status": "ok", "model": None},
                "save":         {"wall_s": _timings.get("save", 0.0),         "status": "ok", "model": None},
            },
        }
        try:
            (report_dir / "harness_perf.json").write_text(
                json.dumps(_perf, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

        return {
            "status": "ok",
            "architecture": architecture_name,
            "aivss": aivss.to_dict(),
            "timings": _timings,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AIVSS scoring failed: {e}")


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

    file_path = resolve_arch_dir(architecture_name) / filename

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
    report_dir = resolve_arch_dir(architecture_name)

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
    report_dir = resolve_arch_dir(architecture_name)

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


# ---------------------------------------------------------------------------
# Helpers for /insights/all
# ---------------------------------------------------------------------------

def _base_arch_name(name: str) -> str:
    """Strip trailing _N rerun suffixes: '00_serviceentry_2_1_1' → '00_serviceentry'."""
    parts = name.split('_')
    i = len(parts)
    while i > 1 and parts[i - 1].isdigit():
        i -= 1
    return '_'.join(parts[:i])


_SSP_DOMAIN: Dict[str, str] = {
    'low_risk_cloud':               'Cloud',
    'medium_risk_cloud':            'Cloud',
    'high_risk_cloud_cii':          'Cloud',
    'low_risk_onprem':              'On-Premises',
    'generative_ai':                'Agentic/AI',
    'digital_services_others':      'Digital Services',
    'digital_services_high_impact': 'Digital Services',
    'sandbox':                      'General',
}

_KEYWORD_DOMAIN: List[tuple] = [
    (['hybrid'],                                                     'Hybrid Cloud'),
    (['iot', '_ot_', '_ot', 'cps', 'scada', 'plc'],                 'IoT/OT/CPS'),
    (['agentic', 'llm', '_ai_', '_ai'],                              'Agentic/AI'),
    (['azure', 'aws', 'gcp', 'serverless', 'lambda', 'cloud'],      'Cloud'),
    (['dmz', 'legacy', 'flat_network', 'enterprise', 'on_prem'],    'On-Premises'),
    (['digital', 'service', 'web_app', 'api_gw', 'mobile',
      'zero_trust'],                                                  'Digital Services'),
]


def _classify_domain(ssp_profile: str, arch_name: str) -> str:
    if ssp_profile and ssp_profile in _SSP_DOMAIN:
        return _SSP_DOMAIN[ssp_profile]
    name_lower = arch_name.lower()
    for keywords, domain in _KEYWORD_DOMAIN:
        if any(kw in name_lower for kw in keywords):
            return domain
    return 'General'


# ---------------------------------------------------------------------------
# /insights/all — full trending dataset for all architectures
# ---------------------------------------------------------------------------

@router.get("/insights/all")
async def get_all_insights_trending():
    """
    Return all architectures with flattened trending metrics in one call.
    Used by Insights tab: Single Arch trend, Multi-Arch comparison, Domain view.
    No auth required — read-only reporting data.
    """
    report_base = get_report_dir()
    if not report_base.exists():
        return {"architectures": []}

    _DIM_KEYS = {
        'D1': 'exploitation',
        'D2': 'manipulation',
        'D3': 'leakage',
        'D4': 'identity',
        'D5': 'sovereignty',
    }

    results = []
    for arch_dir in report_base.iterdir():
        if not arch_dir.is_dir() or arch_dir.name.startswith('.'):
            continue
        gt_path = arch_dir / "ground_truth.json"
        if not gt_path.exists():
            continue

        entry: Dict = {
            "name":            arch_dir.name,
            "base_name":       _base_arch_name(arch_dir.name),
            "analysed_at":     datetime.datetime.utcfromtimestamp(
                                   arch_dir.stat().st_mtime
                               ).isoformat() + 'Z',
            "domain":          'General',
            "ssp_profile":     None,
            "risk_score":      None,
            "defensibility":   None,
            "confidence":      None,
            "controls_missing": [],
            "techniques":      [],
            "aivss_overall":   None,
            "aivss_severity":  None,
            "governance_dims": {},
        }

        try:
            gt = json.loads(gt_path.read_text())
            entry["risk_score"]      = gt.get("expected_risk_score")
            entry["defensibility"]   = gt.get("expected_defensibility")
            entry["controls_missing"] = gt.get("controls_missing") or []
            # confidence: scalar float preferred, fall back to breakdown dict
            conf = gt.get("confidence")
            if isinstance(conf, dict):
                conf = conf.get("final")
            if conf is not None:
                entry["confidence"] = round(float(conf) * 100, 1) if conf <= 1.0 else round(float(conf), 1)
            # flatten all techniques across paths, deduplicated
            all_techs: set = set()
            for p in gt.get("expected_attack_paths", []):
                all_techs.update(p.get("techniques", []))
            entry["techniques"] = sorted(all_techs)
            # domain classification
            meta = gt.get("metadata", {})
            ssp = meta.get("ssp_profile") or gt.get("ssp_profile")
            entry["ssp_profile"] = ssp
            entry["domain"] = _classify_domain(ssp or '', arch_dir.name)
        except Exception:
            pass

        gov_path = arch_dir / "governance_signals.json"
        if gov_path.exists():
            try:
                gov = json.loads(gov_path.read_text())
                aivss_overall = (gov.get("aivss") or {}).get("overall") or {}
                if aivss_overall.get("composite") is not None:
                    entry["aivss_overall"]  = round(float(aivss_overall["composite"]), 2)
                    entry["aivss_severity"] = aivss_overall.get("severity")
                for dk, gk in _DIM_KEYS.items():
                    dim = gov.get(gk) or {}
                    sev = dim.get("severity")
                    if sev:
                        entry["governance_dims"][dk] = sev
            except Exception:
                pass

        results.append(entry)

    results.sort(key=lambda x: x["analysed_at"] or "", reverse=True)
    return {"architectures": results}


@router.get("/tatb-corpus")
async def get_tatb_corpus():
    """
    Return TATB rubric scores for all architectures plus corpus averages.

    Response shape:
      {
        "architectures": [{ "name", "overall", "threat", "ttp", "risk", "plan" }, ...],
        "avg":           { "overall", "threat", "ttp", "risk", "plan" }
      }

    Scoring is computed server-side using the same logic as /tatb-score CLI.
    MITRE alignment requires API server to be running on localhost:8000 (self-call).
    No auth required — read-only diagnostic data.
    """
    import sys as _sys
    import urllib.request as _urllib_req

    report_base = get_report_dir()
    if not report_base.exists():
        return {"architectures": [], "avg": {}}

    # Import scoring functions from the skill script
    import importlib.util as _ilu
    _skill_path = Path(__file__).parent.parent.parent.parent / ".claude/skills/tatb-score/scripts/tatb-score.py"
    if not _skill_path.exists():
        raise HTTPException(status_code=500, detail="tatb-score skill not found")

    _spec = _ilu.spec_from_file_location("tatb_score_skill", _skill_path)
    _mod  = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)

    arch_dirs = sorted(
        [d for d in report_base.iterdir() if d.is_dir() and (d / "ground_truth.json").exists()],
        key=lambda d: d.name,
    )

    # Fetch MITRE data once for all techniques across corpus
    all_tech_ids: set = set()
    gt_cache: dict = {}
    for ad in arch_dirs:
        try:
            gt = json.loads((ad / "ground_truth.json").read_text())
            gt_cache[ad.name] = gt
            for ap in gt.get("expected_attack_paths", []):
                all_tech_ids.update(ap.get("techniques", []))
        except Exception:
            pass

    mitre_mits, mit_names = _mod.fetch_mitre(list(all_tech_ids))

    arch_scores = []
    for ad in arch_dirs:
        gt = gt_cache.get(ad.name)
        if not gt:
            continue
        try:
            def _load(name, _ad=ad):
                p = _ad / name
                return json.loads(p.read_text()) if p.exists() else None

            gov = _load("governance_signals.json")
            moe = _load("07_moe_orchestrator.json")
            sm  = _load("08_scrum_master.json")

            t_s = _mod.score_threat(gt)
            ttp = _mod.score_ttp(gt, moe, mitre_mits, mit_names)
            r_s = _mod.score_risk(gt, gov)
            p_s = _mod.score_plan(gt, sm)
            valid = [s["score"] for s in [t_s, ttp, r_s, p_s]
                     if isinstance(s, dict) and s.get("score") is not None]
            overall = round(sum(valid) / len(valid)) if valid else None

            arch_scores.append({
                "name":    ad.name,
                "overall": overall,
                "threat":  t_s.get("score"),
                "ttp":     ttp.get("score"),
                "risk":    r_s.get("score"),
                "plan":    p_s.get("score"),
            })
        except Exception:
            pass

    def _avg(key):
        vals = [a[key] for a in arch_scores if a.get(key) is not None]
        return round(sum(vals) / len(vals)) if vals else None

    avg = {
        "overall": _avg("overall"),
        "threat":  _avg("threat"),
        "ttp":     _avg("ttp"),
        "risk":    _avg("risk"),
        "plan":    _avg("plan"),
        "count":   len(arch_scores),
    }

    arch_scores.sort(key=lambda a: a.get("overall") or 0, reverse=True)
    return {"architectures": arch_scores, "avg": avg}


@router.post("/reports/{architecture_name}/generate-ciso-brief")
async def generate_ciso_brief(
    architecture_name: str,
    llm: bool = Query(False, description="Include LLM narrative (slower)"),
    _: str = Depends(verify_api_key),
):
    """Generate or regenerate the CISO brief for an architecture.

    Runs the ciso-brief BUILD + LOOK + RELEASE pipeline:
    - Reads ground_truth.json, 07_moe_orchestrator.json, 08_scrum_master.json
    - Computes metrics, selects KNOWN findings (multi-critic first)
    - Optionally generates LLM narrative (llm=true query param)
    - Loads previous snapshot for trend delta
    - Writes ciso_brief_latest.json + ciso_brief_<date>.md

    Returns the snapshot JSON so the UI can render immediately.
    """
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=400, detail="Invalid architecture_name")

    report_dir = resolve_arch_dir(architecture_name)
    if not report_dir.exists():
        raise HTTPException(status_code=404, detail=f"Architecture '{architecture_name}' not found")

    gt_path  = report_dir / "ground_truth.json"
    moe_path = report_dir / "07_moe_orchestrator.json"
    sm_path  = report_dir / "08_scrum_master.json"

    if not gt_path.exists():
        raise HTTPException(status_code=404, detail="ground_truth.json not found — run analysis first")

    def _load(p: Path) -> dict:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    gt  = _load(gt_path)
    moe = _load(moe_path)
    sm  = _load(sm_path)

    import re as _re
    import datetime as _dt

    # ── Build metrics ────────────────────────────────────────────────────────
    risk    = gt.get("expected_risk_score", 0)
    defence = gt.get("expected_defensibility", 0)
    n_paths = len(gt.get("expected_attack_paths", []))
    n_tech  = len({t for ap in gt.get("expected_attack_paths", [])
                   for t in ap.get("techniques", [])})

    conf_data = moe.get("confidence") or {}
    conf      = conf_data.get("final") or 0

    io   = moe.get("improvement_options", {})
    cr   = moe.get("consensus_recommendations", {})
    sev_rank = {"CRITICAL": 2, "HIGH": 1}

    # KNOWN findings, multi-critic first
    def _critic_count(source: str) -> int:
        return len(source.split("+"))

    # Build description→recommendation lookup from expert_validations gaps.
    # consensus_recommendations items have no recommendation field.
    # Index by 30-char prefix — multi-node KNOWN descriptions diverge from
    # single-node gap descriptions after ~30 chars so 60 was too long.
    ev = moe.get("expert_validations", {})
    _gap_recs: dict[str, str] = {}
    for _v in ev.values():
        for _g in (_v.get("gaps") or []):
            _desc = (_g.get("description") or "")
            _rec  = (_g.get("recommendation") or "").strip()
            if _desc and _rec:
                # 20-char prefix: KNOWN multi-node descriptions diverge from single-node
                # gap descriptions at ~20 chars ("WebUI pivot allows T119" vs "WebUI pivot (AP-1/")
                for _n in (20, 15, 10, 8):
                    _k = _desc[:_n].lower().strip()
                    if _k and _k not in _gap_recs:
                        _gap_recs[_k] = _rec

    # Also index tier item control names — some gaps have empty recommendations
    # but the improvement_options tier items carry the control as "MFA enforcement at..."
    import re as _re2
    for _tier in io.values():
        for _item in (_tier.get("items") or []):
            _it = str(_item)
            if _it.startswith("[SM]"):
                continue
            _dash = _it.find(" — ")  # em-dash separator
            if _dash < 0:
                _dash = _it.find(" - ")
            _ctrl = _it[:_dash].strip() if _dash > -1 else _it[:60].strip()
            # Strip "at Node" suffix from control name
            _at = _ctrl.lower().find(" at ")
            if _at > -1:
                _ctrl = _ctrl[:_at].strip()
            # Index by first 20 chars of the control name as a supplemental lookup
            _ck = _ctrl[:20].lower().strip()
            if _ck and _ck not in _gap_recs:
                _gap_recs[_ck] = f"Deploy {_ctrl}."

    def _find_rec(desc: str, cr_rec: str) -> str:
        if cr_rec:
            return cr_rec
        for _n in (20, 15, 10, 8):
            k = desc[:_n].lower().strip()
            if k in _gap_recs:
                return _gap_recs[k]
        # Last resort: extract control name from description patterns like
        # "No X (ControlName) deployed" or "X on Node has no ControlName"
        _m1 = _re2.search(r"\bNo\s+\w+\s+(?:controls?\s+)?\(([^)]+)\)\s+deploy", desc, _re2.I)
        if _m1:
            return f"Deploy {_m1.group(1).strip()} — no controls currently in place."
        _m2 = _re2.search(r"No\s+([\w\s/]+?)\s+(?:deployed|present|found|exists)", desc, _re2.I)
        if _m2:
            ctrl = _m2.group(1).strip()
            if len(ctrl) < 40:
                return f"Deploy {ctrl}."
        return ""

    candidates = []
    for sev_key in ("critical", "high"):
        for r in cr.get(sev_key, []):
            if r.get("confidence_label") != "KNOWN":
                continue
            source = r.get("source", "")
            desc   = r.get("description", "")
            rec    = _find_rec(desc, r.get("recommendation", ""))
            candidates.append({
                "description":    desc,
                "recommendation": rec,
                "severity":       r.get("severity", sev_key.upper()),
                "source":         source,
                "critic_count":   _critic_count(source),
                "sev_rank":       sev_rank.get(r.get("severity", "").upper(), 0),
            })
    candidates.sort(key=lambda x: (-x["critic_count"], -x["sev_rank"]))
    top_findings = candidates[:5]

    known_crit   = [r for r in cr.get("critical", []) if r.get("confidence_label") == "KNOWN"]
    known_high   = [r for r in cr.get("critical", []) + cr.get("high", [])
                    if r.get("confidence_label") == "KNOWN"]
    unsure_count = len(cr.get("review", []))
    redesign     = sm.get("redesign_signal", False)

    # ── LLM narrative (optional) ─────────────────────────────────────────────
    verdict_txt = ""
    action_txt  = ""
    if llm and moe:
        try:
            from agentic.llm_client import LLMClient
            client = LLMClient()
            top_desc = "; ".join(f["description"][:80] for f in top_findings[:2])
            qw  = io.get("quick_wins",  {})
            rec = io.get("recommended", {})
            crit_actions = [
                a.get("action", "")[:80]
                for a in sm.get("action_plan", [])
                if a.get("priority") == "critical" and not a.get("is_antipattern")
            ][:2]
            prompt = (
                f"You are a security advisor writing a CISO brief for {architecture_name}.\n\n"
                f"Facts: risk={risk}/100, defensibility={defence}/100, confidence={conf:.1f}%, "
                f"paths={n_paths}, redesign={redesign}\n"
                f"Top findings: {top_desc}\n"
                f"Quick Win: {qw.get('cost','?')} / {qw.get('effort','?')} → {qw.get('risk_reduction','?')}\n"
                f"Recommended: {rec.get('cost','?')} / {rec.get('effort','?')} → {rec.get('risk_reduction','?')}\n"
                f"Critical actions: {'; '.join(crit_actions)}\n\n"
                "Write exactly two sentences separated by a newline:\n"
                "1. Current posture + biggest structural risk + concrete consequence. Board language.\n"
                "2. Single most important first step — what, where, expected outcome. No semicolons."
            )
            resp = client.generate(prompt, max_tokens=200, temperature=0.2)
            lines = [_re.sub(r"^(VERDICT|ACTION)\s*:\s*", "", l.strip(), flags=_re.I)
                     for l in (resp.content or "").strip().splitlines() if l.strip()]
            verdict_txt = lines[0] if lines else ""
            action_txt  = lines[1] if len(lines) > 1 else ""
        except Exception as e:
            verdict_txt = f"[LLM error: {e}]"

    # ── Trend delta ──────────────────────────────────────────────────────────
    snap_path = report_dir / "ciso_brief_latest.json"
    delta: dict = {}
    if snap_path.exists():
        try:
            prev = json.loads(snap_path.read_text(encoding="utf-8"))
            delta = {
                "prev_date":        prev.get("date", "?"),
                "confidence_delta": round(conf - prev.get("confidence", conf), 1),
                "risk_delta":       risk - prev.get("risk", risk),
                "known_crit_delta": len(known_crit) - prev.get("known_critical", len(known_crit)),
                "unsure_delta":     unsure_count - prev.get("unsure_count", unsure_count),
            }
            prev_descs = {f["description"][:60] for f in prev.get("top_findings", [])}
            curr_descs = {f["description"][:60] for f in top_findings}
            delta["closed_findings"] = list(prev_descs - curr_descs)
            delta["new_findings"]    = list(curr_descs - prev_descs)
        except Exception:
            pass

    # ── Write snapshot ───────────────────────────────────────────────────────
    today = _dt.date.today().isoformat()
    snap = {
        "arch":           architecture_name,
        "date":           today,
        "confidence":     conf,
        "risk":           risk,
        "defensibility":  defence,
        "n_paths":        n_paths,
        "n_tech":         n_tech,
        "known_critical": len(known_crit),
        "known_high":     len(known_high),
        "unsure_count":   unsure_count,
        "redesign":       redesign,
        "top_findings":   [
            {"description": f["description"][:200], "source": f["source"],
             "severity": f["severity"], "critic_count": f["critic_count"],
             "recommendation": f["recommendation"][:300]}
            for f in top_findings
        ],
        "tiers": {
            k: {
                "cost":              v.get("cost"),
                "effort":            v.get("effort"),
                "risk_reduction":    v.get("risk_reduction"),
                "practical_verdict": v.get("practical_verdict"),
                "rationale":         v.get("rationale", ""),
                "items":             v.get("items", []),
            }
            for k, v in {
                "quick_wins":  io.get("quick_wins",  {}),
                "recommended": io.get("recommended", {}),
                "maximum":     io.get("maximum",     {}),
            }.items() if v
        },
        "verdict": verdict_txt,
        "action":  action_txt,
        "delta":   delta,
    }

    snap_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")

    # ── Write dated MD ───────────────────────────────────────────────────────
    def _interp(pct):
        if pct >= 90: return "STRONG"
        if pct >= 80: return "GOOD"
        if pct >= 70: return "ADEQUATE"
        if pct >= 60: return "NEEDS REVIEW"
        return "ACTION REQUIRED"

    md_lines = [
        f"# CISO Brief — {architecture_name}",
        f"**Date:** {today}   **Confidence:** {conf:.1f}% ({_interp(conf)})"
        + ("   ⚠ REDESIGN SIGNAL" if redesign else ""),
        "",
        "## Risk at a Glance",
        "",
        "| Metric | Value | Status |",
        "|--------|-------|--------|",
        f"| Confidence | {conf:.1f}% | {_interp(conf)} |",
        f"| Attack risk | {risk}/100 | {'HIGH EXPOSURE' if risk >= 70 else 'MEDIUM' if risk >= 40 else 'MANAGED'} |",
        f"| Defensibility | {defence}/100 | {'STRONG' if defence >= 70 else 'PARTIAL' if defence >= 40 else 'WEAK'} |",
        f"| Attack paths | {n_paths} | {len(known_crit)} critical confirmed |",
        "",
    ]
    if delta:
        md_lines += [
            f"## Trend vs {delta.get('prev_date','?')}",
            "",
            "| Metric | Change |",
            "|--------|--------|",
            f"| Confidence | {'+' if delta.get('confidence_delta',0)>=0 else ''}{delta.get('confidence_delta',0):.1f}pp |",
            f"| Risk score | {delta.get('risk_delta',0):+d} |",
            f"| Critical findings | {delta.get('known_crit_delta',0):+d} |",
            "",
        ]
    md_lines += ["## Top Findings (KNOWN confirmed only)", ""]
    for i, f in enumerate(top_findings, 1):
        critics = " + ".join(f["source"].replace("_"," ").title().split("+"))
        desc_m = _re.match(r"^(.{20,}?[.!?])(?:\s|$)", f["description"])
        desc_s = desc_m.group(1) if desc_m else f["description"][:120]
        md_lines += [f"### {i}. {f['severity']} — [{critics}]", desc_s, ""]
    md_lines += ["## Investment Options", "",
                 "| Tier | Cost | Effort | Risk after |",
                 "|------|------|--------|------------|"]
    for key, label in (("quick_wins","Quick Win"),("recommended","Recommended"),("maximum","Maximum")):
        t = snap["tiers"].get(key, {})
        if t:
            rr = t.get("risk_reduction","—")
            nums = _re.findall(r"[\d.]+", rr)
            try:
                rr_s = f"{int(float(nums[0]))} → {int(float(nums[1]))} (−{round((float(nums[0])-float(nums[1]))/float(nums[0])*100)}%)"
            except Exception:
                rr_s = rr[:40]
            md_lines.append(f"| {label} | {t.get('cost','—')} | {t.get('effort','—')} | {rr_s} |")
    md_lines.append("")
    if verdict_txt:
        md_lines += ["## Assessment", "", verdict_txt, ""]
    if action_txt:
        md_lines += ["## Recommended First Action", "", action_txt, ""]
    md_lines += ["---", f"*Generated by /ciso-brief · {today}*"]

    md_path = report_dir / f"ciso_brief_{today}.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "architecture": architecture_name,
        "date": today,
        "snapshot": snap,
        "md_file": f"ciso_brief_{today}.md",
    }
