"""
Universal artifact analysis endpoint — POST /api/v1/analyze/artifact

Accepts any architecture artifact (Terraform, CloudFormation, OpenAPI, AsyncAPI, prose),
auto-detects the format, converts to Mermaid via ArchitectureGraph, then runs the full
TA pipeline (same as POST /api/v1/analyze-stream).

SSE event stream: same shape as /analyze-stream + extra adapter_metadata field in 'complete'.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from chatbot.adapters import detect_adapter
from chatbot.adapters.base import ArchitectureGraph
from chatbot.api.dependencies import verify_api_key
from chatbot.api.routes.streaming import analyze_with_progress

router = APIRouter(prefix="/api/v1", tags=["analysis"])

_MAX_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/analyze/artifact")
async def analyze_artifact(
    request: Request,
    artifact_file: UploadFile = File(
        ...,
        description=(
            "Architecture artifact — .tf, plan.json, .yaml/.yml (CloudFormation or OpenAPI), "
            ".json (OpenAPI), .md, .txt. Auto-detected by filename + content."
        ),
    ),
    ssp_profile: str = Form("low_risk_cloud"),
    arch_name: Optional[str] = Form(
        None,
        description="Override architecture name. Defaults to the uploaded filename stem.",
    ),
    enable_ssp: bool = Form(True),
    include_validation: bool = Form(True),
    _: str = Depends(verify_api_key),
):
    """
    Analyze any architecture artifact — Terraform, CloudFormation, OpenAPI, AsyncAPI, or prose.

    Auto-detects the format from the filename and content, converts to Mermaid via an
    ArchitectureGraph, then runs the full TA pipeline (identical to POST /api/v1/analyze-stream).

    **SSE events:** same as /analyze-stream. The `complete` event's data includes an extra
    `adapter_metadata` field with `{source_format, filename, node_count, edge_count}`.

    **Supported formats:**
    - Terraform: `.tf`, `plan.json`
    - CloudFormation / CDK: `.yaml`, `.yml`, `.json` containing AWSTemplateFormatVersion
    - OpenAPI 3.x / Swagger 2.x / AsyncAPI 2.x: `.yaml`, `.yml`, `.json` with openapi/asyncapi key
    - Prose / architecture docs: `.md`, `.txt`
    """
    content = await artifact_file.read()
    filename = artifact_file.filename or "artifact"

    if len(content) > _MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size {len(content)} bytes exceeds 10MB limit",
        )

    # 1. Detect adapter and extract architecture graph
    try:
        adapter = detect_adapter(filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))

    try:
        graph: ArchitectureGraph = adapter.extract(content, filename)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse '{filename}': {exc}",
        )

    if not graph.nodes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Adapter found 0 nodes in '{filename}'. Check the file is a valid architecture artifact.",
        )

    # 2. Convert to Mermaid and write to tempfile
    mmd_text = graph.to_mmd()
    effective_name = arch_name or Path(filename).stem

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".mmd",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(mmd_text)
        tmp_path = tmp.name

    # 3. Stream analysis with adapter metadata injected into the final 'complete' event
    adapter_meta = {
        "source_format": graph.source_format,
        "filename": filename,
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        **graph.adapter_metadata,
    }

    async def _stream_with_meta():
        async for chunk in analyze_with_progress(
            tmp_path, effective_name, include_validation, ssp_profile, enable_ssp
        ):
            # Inject adapter_metadata into the 'complete' event data
            if chunk.startswith("event: complete\ndata: "):
                try:
                    data_str = chunk.split("data: ", 1)[1].strip()
                    data = json.loads(data_str)
                    data["adapter_metadata"] = adapter_meta
                    yield f"event: complete\ndata: {json.dumps(data)}\n\n"
                    continue
                except (json.JSONDecodeError, IndexError):
                    pass
            yield chunk

    return StreamingResponse(
        _stream_with_meta(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
