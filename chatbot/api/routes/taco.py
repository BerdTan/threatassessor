"""
TACO agent REST endpoints.

POST /api/v1/taco/run       — SSE stream; emits hop events as they complete
POST /api/v1/taco/run-sync  — blocking JSON response (MCP tool / non-SSE callers)
GET  /api/v1/taco/schema    — publish HopChain JSON Schema for external consumers
GET  /api/v1/taco/benchmark/{arch_name} — 7-dimension TACO benchmark for one arch
GET  /api/v1/taco/benchmark             — 7-dimension benchmark over all HOLD_OUT_ARCHS

force_critic flag (Phase 4):
  Set force_critic=true in the request body to append a TACOminiCritic hop.
  Requires critic_enabled=true in settings.yaml.  Never triggered automatically.
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
    sim_mode: bool = False      # True → always walk Brain → Harness regardless of confidence
    force_critic: bool = False  # True → append TACOminiCritic hop (human-triggered only)


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
        # ── Hop 0: TABrain ──────────────────────────────────────────────────
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

        # ── Hop 1: TAWorkspace RAG (if registered) ──────────────────────────
        rag_hop: Optional[HopRecord] = None
        ran_rag = "rag" in agent.minis
        if ran_rag:
            rag_mini = agent.minis["rag"]
            yield _sse("hop_start", {
                "hop_type": rag_mini.hop_type,
                "component": rag_mini.component,
                "is_deterministic": rag_mini.is_deterministic,
                "step": 1,
            })
            rag_hop = await asyncio.to_thread(agent._run_mini, "rag", ctx)
            rag_hop.routed = True
            hops.append(rag_hop)
            hop_dict = rag_hop.model_dump()
            hop_dict["step"] = 1
            yield _sse("hop_complete", hop_dict)
            await asyncio.sleep(0.05)

        # ── Routing decision ────────────────────────────────────────────────
        brain_conf = brain_hop.confidence or 0.0
        rag_conf = (rag_hop.confidence or 0.0) if rag_hop is not None else 0.0
        best_conf = max(brain_conf, rag_conf)

        should_escalate = (req.sim_mode and req.mmd_content) or (
            best_conf < agent.threshold and req.mmd_content
        )

        # ── Hop 2: TAHarness (if escalating) ────────────────────────────────
        if should_escalate:
            harness_mini = agent.minis["harness"]
            yield _sse("hop_start", {
                "hop_type": harness_mini.hop_type,
                "component": harness_mini.component,
                "is_deterministic": harness_mini.is_deterministic,
                "step": 2,
            })
            harness_hop: HopRecord = await asyncio.to_thread(agent._run_mini, "harness", ctx)
            harness_hop.routed = True
            hops.append(harness_hop)
            hop_dict = harness_hop.model_dump()
            hop_dict["step"] = 2
            yield _sse("hop_complete", hop_dict)
            await asyncio.sleep(0.05)

        # ── Hop 3: TACritic (human-triggered only) ──────────────────────────
        ran_critic = False
        if req.force_critic and "critic" in agent.minis:
            critic_mini = agent.minis["critic"]
            step = len(hops)
            yield _sse("hop_start", {
                "hop_type": critic_mini.hop_type,
                "component": critic_mini.component,
                "is_deterministic": critic_mini.is_deterministic,
                "step": step,
            })
            critic_hop: HopRecord = await asyncio.to_thread(agent._run_mini, "critic", ctx)
            critic_hop.routed = True
            hops.append(critic_hop)
            hop_dict = critic_hop.model_dump()
            hop_dict["step"] = step
            yield _sse("hop_complete", hop_dict)
            ran_critic = True
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
            routed_to_rag=ran_rag,
            routed_to_critics=ran_critic,
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
            agent.run, req.query, req.arch_name, req.mmd_content, req.force_critic
        )
        return JSONResponse(content=chain.model_dump())
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/schema")
async def taco_schema() -> JSONResponse:
    """Publish HopChain JSON Schema — for external consumers and spec-driven integrations."""
    from chatbot.modules.taco_agent import HopChain  # noqa: PLC0415
    return JSONResponse(content=HopChain.model_json_schema())


@router.get("/benchmark/{arch_name}", dependencies=[Depends(verify_api_key)])
async def taco_benchmark_arch(arch_name: str) -> JSONResponse:
    """7-dimension TACO benchmark for one architecture (workspace / taco_brain / taco_rag)."""
    from chatbot.modules.taco_benchmark import TACOBenchmark  # noqa: PLC0415
    try:
        bm = TACOBenchmark()
        result = await asyncio.to_thread(bm.score_arch, arch_name)
        return JSONResponse(content=result.to_dict())
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/benchmark", dependencies=[Depends(verify_api_key)])
async def taco_benchmark_hold_out() -> JSONResponse:
    """7-dimension benchmark over all HOLD_OUT_ARCHS."""
    from chatbot.modules.taco_benchmark import TACOBenchmark  # noqa: PLC0415
    from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS  # noqa: PLC0415
    try:
        bm = TACOBenchmark()
        results = await asyncio.to_thread(bm.score_hold_out)
        return JSONResponse(content={
            "results": [r.to_dict() for r in results],
            "hold_out_archs": sorted(HOLD_OUT_ARCHS),
        })
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
