"""
TA Brain REST routes — Stages 2 + 3: TACO query surface + feedback write-back.

POST /api/v1/brain/query    — infer | gaps | patterns
POST /api/v1/brain/feedback — record confirmed/wrong/partial feedback on a prediction
GET  /api/v1/brain/status   — brain health + corpus/pattern/interaction counts
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chatbot.api.dependencies import verify_api_key
from chatbot.modules.ta_brain_query import BRAIN_PATH, INSTANCES_PATH, INTERACTIONS_PATH, query_brain
from chatbot.modules.ta_brain_feedback import record_feedback, get_feedback_summary
from chatbot.modules.ta_brain_confidence import save_confidence_decay
from chatbot.modules.ta_brain_gaps import enrich_brain_gaps, compute_gap_demand_weights
from chatbot.modules.ta_brain_benchmarks import save_calibration, FRAMEWORK_FLOORS
from chatbot.modules.ta_brain_taco_processor import run_taco_processor, load_processor_state
from chatbot.modules.ta_brain_mmd_generator import (
    generate_synthetic_mmds,
    list_synthetic_queue,
    update_synthetic_status,
    get_generation_summary,
)

router = APIRouter(prefix="/api/v1/brain", tags=["brain"])


class BrainGenerateRequest(BaseModel):
    gap_ids: list = []
    max_per_run: int = 3


class BrainQueryRequest(BaseModel):
    mode: str = "infer"
    arch_name: str = ""
    topology_signature: str = ""
    arch_type: str = ""
    arch_type_filter: str = ""


@router.post("/query", dependencies=[Depends(verify_api_key)])
async def brain_query(req: BrainQueryRequest):
    result = query_brain(
        mode=req.mode,
        arch_name=req.arch_name,
        topology_signature=req.topology_signature,
        arch_type=req.arch_type,
        caller_type="rest",
        arch_type_filter=req.arch_type_filter,
    )
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return JSONResponse(content=result)


class BrainFeedbackRequest(BaseModel):
    topology_signature: str = ""
    arch_name: str = ""       # resolved to topology_sig + arch_type if provided
    arch_type: str = ""
    mode: str = "infer"
    feedback: str             # "confirmed" | "wrong" | "partial"
    reference_ts: str = ""    # optional: links to the original query ts


@router.post("/feedback", dependencies=[Depends(verify_api_key)])
async def brain_feedback(req: BrainFeedbackRequest):
    # Resolve topology_sig + arch_type from arch_name if given
    topology_sig = req.topology_signature
    arch_type = req.arch_type

    if req.arch_name and (not topology_sig or not arch_type):
        from chatbot.modules.ta_brain_query import _find_instance
        inst = _find_instance(req.arch_name)
        if inst:
            topology_sig = topology_sig or inst["topology_signature"]
            arch_type = arch_type or inst["arch_type"]
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"Architecture '{req.arch_name}' not found in instance layer"},
            )

    result = record_feedback(
        topology_sig=topology_sig,
        arch_type=arch_type,
        mode=req.mode,
        feedback=req.feedback,
        reference_ts=req.reference_ts,
        caller_type="rest",
    )
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    return JSONResponse(content=result)


@router.get("/feedback/summary", dependencies=[Depends(verify_api_key)])
async def brain_feedback_summary():
    return JSONResponse(content=get_feedback_summary())


@router.post("/process", dependencies=[Depends(verify_api_key)])
async def brain_process():
    """Run TACO processor — full coordinated pass: decay + boost + gaps + calibration priority."""
    try:
        summary = run_taco_processor()
        return JSONResponse(content=summary)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/process/state", dependencies=[Depends(verify_api_key)])
async def brain_process_state():
    """Return TACO processor state (last run, total interactions processed)."""
    return JSONResponse(content=load_processor_state())


@router.post("/calibrate", dependencies=[Depends(verify_api_key)])
async def brain_calibrate():
    """Run benchmark calibration (Brier + framework floors). Updates ta_brain.json + ta_brain_benchmarks.json."""
    try:
        summary = save_calibration()
        return JSONResponse(content=summary)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/benchmarks", dependencies=[Depends(verify_api_key)])
async def brain_benchmarks():
    """Return current ta_brain_benchmarks.json (Brier scores, framework results, divergences)."""
    from chatbot.modules.ta_brain_benchmarks import BENCHMARKS_PATH  # noqa: PLC0415
    if not BENCHMARKS_PATH.exists():
        return JSONResponse(status_code=404, content={"error": "Benchmarks not calibrated yet. POST /api/v1/brain/calibrate"})
    try:
        return JSONResponse(content=json.loads(BENCHMARKS_PATH.read_text()))
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/benchmarks/frameworks", dependencies=[Depends(verify_api_key)])
async def brain_benchmark_frameworks():
    """Return framework floor definitions (OWASP/NIST/CIS/ATLAS per arch_type)."""
    return JSONResponse(content=FRAMEWORK_FLOORS)


@router.post("/enrich-gaps", dependencies=[Depends(verify_api_key)])
async def brain_enrich_gaps():
    """Re-run demand-weighted gap detection from the live interaction log."""
    try:
        summary = enrich_brain_gaps()
        return JSONResponse(content=summary)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/gaps/demand", dependencies=[Depends(verify_api_key)])
async def brain_gap_demand():
    """Return per-arch_type demand weights from the interaction log."""
    return JSONResponse(content=compute_gap_demand_weights())


@router.post("/decay", dependencies=[Depends(verify_api_key)])
async def brain_decay():
    """Run confidence decay pass — reads feedback log, updates ta_brain.json patterns."""
    try:
        summary = save_confidence_decay()
        return JSONResponse(content=summary)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/generate-mmds", dependencies=[Depends(verify_api_key)])
async def brain_generate_mmds(req: BrainGenerateRequest):
    """Generate synthetic MMDs from meta-layer gaps. Stages results for human approval."""
    import asyncio
    try:
        staged = await asyncio.to_thread(
            generate_synthetic_mmds,
            gap_ids=req.gap_ids or None,
            max_per_run=req.max_per_run,
        )
        return JSONResponse(content={"staged": staged, "count": len(staged)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/synthetic-queue", dependencies=[Depends(verify_api_key)])
async def brain_synthetic_queue():
    """Return staged synthetic MMD queue with summary stats."""
    queue = list_synthetic_queue()
    summary = get_generation_summary()
    return JSONResponse(content={"queue": queue, "summary": summary})


@router.post("/synthetic-queue/{gen_id}/approve", dependencies=[Depends(verify_api_key)])
async def brain_approve_synthetic(gen_id: str):
    """Mark a staged MMD as approved — ready for harness submission."""
    try:
        meta = update_synthetic_status(gen_id, "approved")
        return JSONResponse(content=meta)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/synthetic-queue/{gen_id}/reject", dependencies=[Depends(verify_api_key)])
async def brain_reject_synthetic(gen_id: str):
    """Mark a staged MMD as rejected."""
    try:
        meta = update_synthetic_status(gen_id, "rejected")
        return JSONResponse(content=meta)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/status", dependencies=[Depends(verify_api_key)])
async def brain_status():
    status: dict = {
        "brain_built": BRAIN_PATH.exists(),
        "instances_count": 0,
        "interactions_count": 0,
        "pattern_version": None,
        "patterns": 0,
        "gaps": 0,
    }
    if INSTANCES_PATH.exists():
        status["instances_count"] = sum(
            1 for line in INSTANCES_PATH.read_text().splitlines() if line.strip()
        )
    if INTERACTIONS_PATH.exists():
        status["interactions_count"] = sum(
            1 for line in INTERACTIONS_PATH.read_text().splitlines() if line.strip()
        )
    if BRAIN_PATH.exists():
        try:
            brain = json.loads(BRAIN_PATH.read_text())
            status["pattern_version"] = brain.get("pattern_version")
            status["patterns"] = len(brain.get("patterns", []))
            status["gaps"] = len(brain.get("gaps", []))
        except Exception:
            pass
    return JSONResponse(content=status)
