"""
SSE Streaming Routes

Server-Sent Events endpoints for real-time analysis progress.
"""

import tempfile
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator

from chatbot.services import ThreatAnalysisService
from chatbot.api.dependencies import verify_api_key
from chatbot.api.streaming import SSEStream, ProgressTracker


router = APIRouter(prefix="/api/v1", tags=["streaming"])


async def analyze_with_progress(
    architecture_path: str,
    include_validation: bool = True
) -> AsyncGenerator[str, None]:
    """
    Run analysis with SSE progress updates.

    Args:
        architecture_path: Path to architecture file
        include_validation: Run 6-check validation

    Yields:
        SSE formatted progress events
    """
    tracker = ProgressTracker(has_ai_ml=False)  # Will update after detection

    try:
        # Stage 1: Parsing (0-10%)
        yield await SSEStream.send_progress(
            stage="parsing",
            progress=tracker.get_progress("parsing", 0.0),
            message="Parsing architecture diagram...",
            eta_seconds=tracker.get_eta(5)
        )

        await asyncio.sleep(0.1)  # Allow event to be sent

        # Start analysis
        service = ThreatAnalysisService()

        # Stage 2: MITRE Cache (10-20%)
        yield await SSEStream.send_progress(
            stage="mitre",
            progress=tracker.get_progress("mitre", 0.0),
            message="Loading MITRE ATT&CK cache (44MB)...",
            eta_seconds=tracker.get_eta(15)
        )

        await asyncio.sleep(0.1)

        # Run analysis in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: service.safe_execute(
                architecture_path=architecture_path,
                include_validation=include_validation
            )
        )

        if not result.success:
            yield await SSEStream.send_error(
                error_message="Analysis failed",
                detail=result.error
            )
            return

        # Extract pattern information
        patterns_applied = result.data.get("patterns_applied", [])
        has_ai_ml = any(p.get("pattern_id") == "ai_ml_arc" for p in patterns_applied)

        # Update tracker if AI/ML detected
        if has_ai_ml:
            tracker.has_ai_ml = True

        # Stage 3: Pattern Detection
        if patterns_applied:
            yield await SSEStream.send_patterns_detected(patterns_applied)
            await asyncio.sleep(0.1)

        # Stage 4: RAPIDS Analysis (20-60%)
        yield await SSEStream.send_progress(
            stage="rapids",
            progress=tracker.get_progress("rapids", 0.5),
            message="Running RAPIDS threat assessment (6 categories)...",
            eta_seconds=tracker.get_eta(40),
            patterns_active=["rapids"]
        )

        await asyncio.sleep(0.1)

        # Send threat scores
        analysis = result.data.get("analysis", {})
        threats = analysis.get("threats", {})

        if threats:
            # Group by pattern
            scores_by_pattern = {"rapids": threats}

            # If AI/ML detected, extract AI/ML specific scores
            if has_ai_ml:
                ai_risks = analysis.get("ai_ml_risks", {})
                if ai_risks:
                    scores_by_pattern["ai_ml"] = ai_risks

            yield await SSEStream.send_threat_scores(scores_by_pattern)
            await asyncio.sleep(0.1)

        # Stage 5: AI/ML Analysis (60-80%) - only if applicable
        if has_ai_ml:
            yield await SSEStream.send_progress(
                stage="ai_ml",
                progress=tracker.get_progress("ai_ml", 0.5),
                message="Analyzing AI/ML risks (ATLAS + ARC Framework)...",
                eta_seconds=tracker.get_eta(70),
                patterns_active=["rapids", "ai_ml_arc"]
            )
            await asyncio.sleep(0.1)

        # Stage 6: Attack Paths
        attack_paths = analysis.get("attack_paths", [])
        for path in attack_paths[:3]:  # Send first 3 paths progressively
            yield await SSEStream.send_attack_path(path)
            await asyncio.sleep(0.1)

        # Stage 7: Validation (80-100%)
        if include_validation:
            yield await SSEStream.send_progress(
                stage="validation",
                progress=tracker.get_progress("validation", 0.5),
                message="Running completeness validation (6 checks)...",
                eta_seconds=tracker.get_eta(90),
                patterns_active=["rapids"] + (["ai_ml_arc"] if has_ai_ml else [])
            )
            await asyncio.sleep(0.1)

        # Stage 8: Complete (100%)
        yield await SSEStream.send_progress(
            stage="complete",
            progress=100,
            message="Analysis complete!",
            eta_seconds=0
        )

        await asyncio.sleep(0.1)

        # Send final result
        yield await SSEStream.send_complete(result.to_dict())

    except Exception as e:
        yield await SSEStream.send_error(
            error_message="Internal server error",
            detail=str(e)
        )


@router.post("/analyze-stream")
async def analyze_architecture_stream(
    architecture_file: UploadFile = File(
        ...,
        description="Mermaid diagram file (.mmd format, max 10MB)"
    ),
    include_validation: bool = True,
    api_key: str = Depends(verify_api_key)
):
    """
    Analyze architecture with real-time SSE progress updates.

    **SSE Events:**
    - `progress`: Stage updates with percentage and ETA
    - `patterns_detected`: Threat patterns applied (RAPIDS, AI/ML, etc.)
    - `threat_scores`: Threat scores grouped by pattern
    - `attack_path`: Attack path discovery (streamed as found)
    - `complete`: Final analysis result
    - `error`: Error occurred

    **Progress Stages:**
    1. Parsing (0-10%)
    2. MITRE Cache Loading (10-20%)
    3. RAPIDS Analysis (20-60%)
    4. AI/ML Analysis (60-80%, if detected)
    5. Validation (80-100%)

    **Example Client (JavaScript):**
    ```javascript
    const eventSource = new EventSource('/api/v1/analyze-stream');

    eventSource.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data);
      updateProgressBar(data.progress);
      updateStatusMessage(data.message);
    });

    eventSource.addEventListener('complete', (e) => {
      const result = JSON.parse(e.data);
      displayResults(result);
      eventSource.close();
    });
    ```

    **Example Client (Python):**
    ```python
    import requests

    response = requests.post(
        'http://localhost:8000/api/v1/analyze-stream',
        headers={'TM-API-KEY': 'your-key'},
        files={'architecture_file': open('arch.mmd', 'rb')},
        stream=True
    )

    for line in response.iter_lines():
        if line.startswith(b'data: '):
            data = json.loads(line[6:])
            print(f"Progress: {data['progress']}% - {data['message']}")
    ```
    """
    # Validate file extension
    if not architecture_file.filename.endswith('.mmd'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have .mmd extension"
        )

    # Validate file size (10MB limit)
    content = await architecture_file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size {len(content)} bytes exceeds 10MB limit"
        )

    # Save to temp file
    with tempfile.NamedTemporaryFile(
        mode='wb',
        suffix='.mmd',
        delete=False
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        return StreamingResponse(
            analyze_with_progress(tmp_path, include_validation),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "Connection": "keep-alive"
            }
        )
    finally:
        # Cleanup happens after stream completes
        # Note: Can't delete here as stream is still running
        pass
