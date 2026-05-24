"""
Reports API Routes

Endpoints for accessing generated analysis reports.
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import FileResponse, JSONResponse
from typing import List, Dict
from chatbot.modules.mitre import MitreHelper, get_mitre_helper as _get_mitre_singleton

router = APIRouter(prefix="/api/v1", tags=["reports"])

def get_mitre_helper() -> MitreHelper:
    """Return the shared MITRE singleton."""
    return _get_mitre_singleton()


def get_report_dir() -> Path:
    """Get the base reports directory."""
    # Assuming reports are in project_root/report/
    report_dir = Path(__file__).parent.parent.parent.parent / "report"
    return report_dir


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
                architectures.append({
                    "name": arch_dir.name,
                    "report_count": len(files),
                    "files": sorted(files)
                })

    # Sort by name
    architectures.sort(key=lambda x: x['name'])

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

    result = {}
    for tid in ids:
        tech = mitre.find_technique(tid)
        if tech:
            result[tid] = tech.get('name', 'Unknown')
        else:
            result[tid] = f"Unknown ({tid})"

    return {"techniques": result}
