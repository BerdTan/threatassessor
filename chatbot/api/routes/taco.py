"""
TACO agent REST endpoints.

POST /api/v1/taco/run       — SSE stream; emits hop events as they complete
POST /api/v1/taco/run-sync  — blocking JSON response (MCP tool / non-SSE callers)
GET  /api/v1/taco/schema    — publish HopChain JSON Schema for external consumers
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from chatbot.api.dependencies import verify_api_key

router = APIRouter(prefix="/api/v1/taco", tags=["taco"])


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class TACORunRequest(BaseModel):
    query: str
    arch_name: Optional[str] = None
    mmd_content: Optional[str] = None
    sim_mode: bool = False   # True → always walk Brain → Harness regardless of confidence


# ---------------------------------------------------------------------------
# SSE helper (mirrors mcp_sim.py pattern)
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# SSE generator — calls hops individually so events can be yielded between them
# ---------------------------------------------------------------------------

async def _taco_stream(req: TACORunRequest) -> AsyncGenerator[str, None]:
    from chatbot.modules.taco_agent import HopChain, HopRecord, TACOAgent, TACOContext  # noqa: PLC0415

    chain_id = str(uuid.uuid4())
    agent = TACOAgent()
    ctx = TACOContext(query=req.query, arch_name=req.arch_name, arch_mmd=req.mmd_content)

    yield _sse("taco_start", {
        "chain_id": chain_id,
        "query": req.query,
        "arch_name": req.arch_name,
        "threshold": agent.threshold,
        "sim_mode": req.sim_mode,
    })
    await asyncio.sleep(0.05)

    hops: list[HopRecord] = []

    try:
        # ── Hop 1: TABrain ──────────────────────────────────────────────────
        brain_mini = agent.minis["brain"]
        yield _sse("hop_start", {
            "hop_type": brain_mini.hop_type,
            "component": brain_mini.component,
            "is_deterministic": brain_mini.is_deterministic,
            "step": 0,
        })
        brain_hop: HopRecord = await asyncio.to_thread(agent._run_mini, "brain", ctx)
        hops.append(brain_hop)
        hop_dict = brain_hop.model_dump()
        hop_dict["step"] = 0
        yield _sse("hop_complete", hop_dict)
        await asyncio.sleep(0.05)

        # ── Routing decision ────────────────────────────────────────────────
        should_escalate = (req.sim_mode and req.mmd_content) or (
            brain_hop.confidence is not None
            and brain_hop.confidence < agent.threshold
            and req.mmd_content
        )

        # ── Hop 2: TAHarness (if escalating) ────────────────────────────────
        if should_escalate:
            harness_mini = agent.minis["harness"]
            yield _sse("hop_start", {
                "hop_type": harness_mini.hop_type,
                "component": harness_mini.component,
                "is_deterministic": harness_mini.is_deterministic,
                "step": 1,
            })
            harness_hop: HopRecord = await asyncio.to_thread(agent._run_mini, "harness", ctx)
            harness_hop.routed = True
            hops.append(harness_hop)
            hop_dict = harness_hop.model_dump()
            hop_dict["step"] = 1
            yield _sse("hop_complete", hop_dict)
            await asyncio.sleep(0.05)

        # ── Build and emit chain ─────────────────────────────────────────────
        chain = HopChain(
            chain_id=chain_id,
            query=req.query,
            arch_name=req.arch_name,
            hops=hops,
            final_confidence=hops[-1].confidence or 0.0,
            final_response=hops[-1].metadata,
            total_duration_ms=sum(h.duration_ms for h in hops),
            routed_to_harness=bool(should_escalate),
            routed_to_critics=False,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        yield _sse("taco_complete", chain.model_dump())

    except Exception as exc:
        yield _sse("taco_error", {"message": str(exc), "chain_id": chain_id})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/run", dependencies=[Depends(verify_api_key)])
async def taco_run(req: TACORunRequest) -> StreamingResponse:
    """SSE stream — emits hop events as they complete, then taco_complete."""
    return StreamingResponse(
        _taco_stream(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/run-sync", dependencies=[Depends(verify_api_key)])
async def taco_run_sync(req: TACORunRequest) -> JSONResponse:
    """Blocking JSON response — returns full HopChain. For MCP tools and non-SSE callers."""
    from chatbot.modules.taco_agent import TACOAgent  # noqa: PLC0415

    agent = TACOAgent()
    try:
        chain = await asyncio.to_thread(
            agent.run, req.query, req.arch_name, req.mmd_content
        )
        return JSONResponse(content=chain.model_dump())
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/schema")
async def taco_schema() -> JSONResponse:
    """Publish HopChain JSON Schema — for external consumers and spec-driven integrations."""
    from chatbot.modules.taco_agent import HopChain  # noqa: PLC0415
    return JSONResponse(content=HopChain.model_json_schema())
