"""
Benchmark routes — serve bench run index and HTML reports.

GET /api/v1/bench/runs          — list bench_results/<run_id>/ directories
GET /api/v1/bench/report/{run_id} — serve bench_report.html for a run

No auth required: these endpoints serve locally-generated files and are only
reachable from the local dashboard (same trust boundary as /dashboard itself).
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bench", tags=["bench"])

# bench_results/ sits at the repo root (same level as chatbot/)
_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BENCH_DIR = _ROOT / "bench_results"


def _run_meta(run_dir: Path) -> dict:
    summary = run_dir / "bench_summary.json"
    meta: dict = {"run_id": run_dir.name, "has_report": (run_dir / "bench_report.html").exists()}
    if summary.exists():
        try:
            data = json.loads(summary.read_text())
            run_id = data.get("run_id", run_dir.name)
            try:
                from datetime import datetime
                meta["ts"] = datetime.strptime(run_id, "%Y%m%d_%H%M%S").isoformat()
            except ValueError:
                meta["ts"] = run_id
            meta["models"] = data.get("models", [])
            meta["archs"]  = data.get("archs", [])
            meta["arch_count"] = len(meta["archs"])
            # derive winner and completeness from depth scores
            results = data.get("results", {})
            model_scores: dict = {}
            any_nonzero = False
            for arch_data in results.values():
                for m, mdata in arch_data.items():
                    depth = mdata.get("depth", {})
                    vals = [v for v in depth.values() if v is not None]
                    if any(v > 0 for v in vals):
                        any_nonzero = True
                    avg = sum(vals) / len(vals) if vals else 0
                    model_scores[m] = model_scores.get(m, 0) + avg
            meta["is_complete"] = any_nonzero
            if model_scores:
                meta["winner"] = max(model_scores, key=model_scores.get)
                meta["avg_depth"] = round(
                    sum(model_scores.values()) / len(model_scores) / max(meta["arch_count"], 1), 1
                )
        except Exception:
            pass
    else:
        meta["is_complete"] = False
    return meta


@router.get("/runs")
async def list_bench_runs():
    if not BENCH_DIR.exists():
        return JSONResponse({"runs": []})
    runs = sorted(
        [d for d in BENCH_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return JSONResponse({"runs": [_run_meta(r) for r in runs]})


@router.get("/report/{run_id}", response_class=HTMLResponse)
async def get_bench_report(run_id: str):
    # guard against path traversal
    if ".." in run_id or "/" in run_id:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    report = BENCH_DIR / run_id / "bench_report.html"
    if not report.exists():
        raise HTTPException(status_code=404, detail=f"Report not found for run {run_id}")
    return HTMLResponse(content=report.read_text(), status_code=200)
