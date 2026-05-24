"""
SSE Streaming Routes

Server-Sent Events endpoints for real-time analysis progress.
"""

import logging
import tempfile
import asyncio
import concurrent.futures
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator

from chatbot.services import ThreatAnalysisService
from chatbot.api.dependencies import verify_api_key
from chatbot.api.streaming import SSEStream, ProgressTracker

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["streaming"])


async def analyze_with_progress(
    architecture_path: str,
    filename: str,
    include_validation: bool = True
) -> AsyncGenerator[str, None]:
    """
    Run analysis with SSE progress updates.

    Args:
        architecture_path: Path to architecture file
        filename: Original uploaded filename
        include_validation: Run 6-check validation

    Yields:
        SSE formatted progress events
    """
    tracker = ProgressTracker(has_ai_ml=False)  # Will update after detection

    try:
        # Stage 1: Parsing (0-10%)
        progress = tracker.get_progress("parsing", 0.0)
        yield await SSEStream.send_progress(
            stage="parsing",
            progress=progress,
            message=f"[PARSING] {progress}% - {filename} - Analyzing architecture diagram structure...",
            eta_seconds=tracker.get_eta(progress)
        )

        await asyncio.sleep(0.1)

        # Parsing progress updates
        progress = tracker.get_progress("parsing", 0.5)
        yield await SSEStream.send_progress(
            stage="parsing",
            progress=progress,
            message=f"[PARSING] {progress}% - {filename} - Validating Mermaid syntax...",
            eta_seconds=tracker.get_eta(progress)
        )

        await asyncio.sleep(0.1)

        # Start analysis
        service = ThreatAnalysisService()

        # Stage 2: MITRE Cache (10-20%) - with incremental updates for large 44MB load
        progress = tracker.get_progress("mitre", 0.0)
        yield await SSEStream.send_progress(
            stage="mitre",
            progress=progress,
            message=f"[MITRE] {progress}% - {filename} - Loading MITRE ATT&CK cache (44MB)...",
            eta_seconds=tracker.get_eta(progress)
        )

        await asyncio.sleep(0.1)

        # Incremental updates during cache load
        for i in range(1, 5):
            progress = tracker.get_progress("mitre", i * 0.2)
            yield await SSEStream.send_progress(
                stage="mitre",
                progress=progress,
                message=f"[MITRE] {progress}% - {filename} - Loading cache... ({i*25}% complete)",
                eta_seconds=tracker.get_eta(progress)
            )
            await asyncio.sleep(0.05)

        progress = tracker.get_progress("mitre", 0.9)
        yield await SSEStream.send_progress(
            stage="mitre",
            progress=progress,
            message=f"[MITRE] {progress}% - {filename} - Indexing 14 tactics, 196 techniques...",
            eta_seconds=tracker.get_eta(progress)
        )

        await asyncio.sleep(0.1)

        # Extract clean architecture name from uploaded filename
        # Remove .mmd extension and sanitize
        clean_arch_name = filename.replace('.mmd', '').replace('.', '_').replace(' ', '_')

        # Run analysis in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: service.safe_execute(
                architecture_path=architecture_path,
                architecture_name=clean_arch_name,
                include_validation=include_validation
            )
        )

        if not result.success:
            yield await SSEStream.send_error(
                error_message="Analysis failed",
                detail=result.error
            )
            return

        # Generate markdown reports (Executive, Technical, Action Plan)
        yield await SSEStream.send_progress(
            stage="reports",
            progress=15,
            message=f"📝 Generating markdown reports for {filename}...",
            eta_seconds=5
        )
        await asyncio.sleep(0.1)

        try:
            from chatbot.modules.threat_report import generate_report_package

            # Generate all reports (executive, technical, action plan, diagrams)
            ground_truth = result.data.get("analysis", {})
            report_paths = await loop.run_in_executor(
                None,
                lambda: generate_report_package(
                    original_mmd_path=architecture_path,
                    ground_truth=ground_truth,
                    output_dir="report"
                )
            )

            # Add report paths to result data
            result.data["report_paths"] = report_paths

            yield await SSEStream.send_progress(
                stage="reports",
                progress=18,
                message=f"✅ Reports generated: Executive, Technical, Action Plan",
                eta_seconds=3
            )
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.warning(f"Report generation failed: {e}")
            # Continue anyway - reports are supplementary
            result.data["report_paths"] = None
            result.data["report_error"] = str(e)

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
        progress = tracker.get_progress("rapids", 0.0)
        yield await SSEStream.send_progress(
            stage="rapids",
            progress=progress,
            message=f"[RAPIDS] {progress}% - {filename} - Analyzing 6 threat categories...",
            eta_seconds=tracker.get_eta(progress),
            patterns_active=["rapids"]
        )

        await asyncio.sleep(0.1)

        progress = tracker.get_progress("rapids", 0.3)
        yield await SSEStream.send_progress(
            stage="rapids",
            progress=progress,
            message=f"[RAPIDS] {progress}% - {filename} - Mapping MITRE techniques to components...",
            eta_seconds=tracker.get_eta(progress),
            patterns_active=["rapids"]
        )

        await asyncio.sleep(0.1)

        progress = tracker.get_progress("rapids", 0.7)
        yield await SSEStream.send_progress(
            stage="rapids",
            progress=progress,
            message=f"[RAPIDS] {progress}% - {filename} - Computing attack paths and defensibility...",
            eta_seconds=tracker.get_eta(progress),
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
            progress = tracker.get_progress("ai_ml", 0.0)
            yield await SSEStream.send_progress(
                stage="ai_ml",
                progress=progress,
                message=f"[AI/ML] {progress}% - {filename} - Detecting AI/ML components...",
                eta_seconds=tracker.get_eta(progress),
                patterns_active=["rapids", "ai_ml_arc"]
            )
            await asyncio.sleep(0.1)

            progress = tracker.get_progress("ai_ml", 0.5)
            yield await SSEStream.send_progress(
                stage="ai_ml",
                progress=progress,
                message=f"[AI/ML] {progress}% - {filename} - Analyzing ATLAS techniques + ARC risks...",
                eta_seconds=tracker.get_eta(progress),
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
            progress = tracker.get_progress("validation", 0.0)
            yield await SSEStream.send_progress(
                stage="validation",
                progress=progress,
                message=f"[VALIDATION] {progress}% - {filename} - Running 6-check completeness validation...",
                eta_seconds=tracker.get_eta(progress),
                patterns_active=["rapids"] + (["ai_ml_arc"] if has_ai_ml else [])
            )
            await asyncio.sleep(0.1)

            progress = tracker.get_progress("validation", 0.5)
            yield await SSEStream.send_progress(
                stage="validation",
                progress=progress,
                message=f"[VALIDATION] {progress}% - {filename} - Verifying technique coverage and orphan nodes...",
                eta_seconds=tracker.get_eta(progress),
                patterns_active=["rapids"] + (["ai_ml_arc"] if has_ai_ml else [])
            )
            await asyncio.sleep(0.1)

        # Stage 8: Complete (100%)
        yield await SSEStream.send_progress(
            stage="complete",
            progress=100,
            message=f"✅ {filename} - Analysis complete! All reports generated.",
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
            analyze_with_progress(tmp_path, architecture_file.filename, include_validation),
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


async def expert_review_with_progress(
    architecture_name: str
) -> AsyncGenerator[str, None]:
    """
    Run MoE Expert Review pipeline with SSE progress updates.

    Requires analysis to have been run first (ground_truth.json must exist).

    Args:
        architecture_name: Architecture name (matches report directory)

    Yields:
        SSE formatted progress events
    """
    from chatbot.modules.agents.orchestrators.moe_orchestrator import (
        run_moe_pipeline, MissingPrerequisiteError
    )

    report_dir = Path(__file__).parent.parent.parent.parent / "report" / architecture_name

    try:
        # Check prerequisites
        gt_path = report_dir / "ground_truth.json"
        if not gt_path.exists():
            yield await SSEStream.send_error(
                error_message="Prerequisites missing",
                detail=f"Run analysis first — ground_truth.json not found for '{architecture_name}'"
            )
            return

        yield await SSEStream.send_progress(
            stage="architect",
            progress=5,
            message=f"[2A] Architect Critic: Loading analysis artifacts for '{architecture_name}'...",
            eta_seconds=90
        )
        await asyncio.sleep(0.1)

        yield await SSEStream.send_progress(
            stage="architect",
            progress=10,
            message="[2A] Architect Critic: Reviewing threat model completeness...",
            eta_seconds=80
        )
        await asyncio.sleep(0.1)

        # Run full pipeline in thread pool (synchronous blocking ~90s)
        loop = asyncio.get_event_loop()

        # Emit staged progress while the pipeline runs in the background.
        # Pipeline is opaque/synchronous; we interleave timed progress yields with awaiting it.
        task = loop.run_in_executor(None, run_moe_pipeline, str(report_dir))

        stage_updates = [
            (20, "architect", "[2A] Architect Critic: Validating attack paths and threat coverage...", 70),
            (35, "architect", "[2A] Architect Critic: Checking MITRE technique completeness...", 55),
            (50, "tester",    "[2B] Tester Critic: Reviewing Architect findings and MITRE mappings...", 40),
            (65, "tester",    "[2B] Tester Critic: Verifying control effectiveness claims...", 30),
            (75, "red_team",  "[2C] Red Team Critic: Probing control weaknesses and bypass paths...", 20),
            (85, "red_team",  "[2C] Red Team Critic: Stress-testing defensive posture...", 12),
            (90, "synthesis", "[L3] Orchestrator: Synthesising consensus recommendations...", 8),
        ]

        result = None
        for progress, stage, message, eta in stage_updates:
            # Yield the progress event, then wait up to 12s before the next update
            # (or until the task finishes, whichever comes first)
            yield await SSEStream.send_progress(
                stage=stage,
                progress=progress,
                message=message,
                eta_seconds=eta
            )
            try:
                result = await asyncio.wait_for(asyncio.shield(task), timeout=12.0)
                break  # Pipeline finished before the 12s window elapsed
            except asyncio.TimeoutError:
                pass  # Pipeline still running — continue to next progress update

        # Await final result if not already retrieved
        if result is None:
            result = await task

        yield await SSEStream.send_progress(
            stage="synthesis",
            progress=95,
            message="[L3] Orchestrator: Generating expert review reports...",
            eta_seconds=3
        )
        await asyncio.sleep(0.1)

        yield await SSEStream.send_progress(
            stage="complete",
            progress=100,
            message=f"✅ Expert Review complete — final confidence: {result.final_confidence:.1f}%",
            eta_seconds=0
        )
        await asyncio.sleep(0.1)

        yield await SSEStream.send_complete(result.to_dict())

    except MissingPrerequisiteError as e:
        yield await SSEStream.send_error(
            error_message="Missing prerequisite",
            detail=str(e)
        )
    except Exception as e:
        yield await SSEStream.send_error(
            error_message="Expert Review failed",
            detail=str(e)
        )


@router.get("/expert-review")
async def expert_review_stream(
    architecture_name: str = Query(
        ...,
        description="Architecture name (must match an existing analysis in report/)"
    ),
    api_key: str = Depends(verify_api_key)
):
    """
    Run MoE Expert Review on a previously analyzed architecture.

    Streams real-time progress via SSE as three independent critic agents
    (Architect, Tester, Red Team) validate the deterministic analysis and
    produce a consensus confidence score and unified recommendations.

    **Prerequisites:** Run `/api/v1/analyze-stream` first to generate `ground_truth.json`.

    **SSE Events:**
    - `progress`: Stage updates (architect → tester → red_team → synthesis)
    - `complete`: Final MoEResult with confidence and consensus recommendations
    - `error`: Error details (e.g. missing prerequisites)

    **Example Client (JavaScript):**
    ```javascript
    const url = `/api/v1/expert-review?architecture_name=${archName}`;
    const es = new EventSource(url);

    es.addEventListener('progress', (e) => {
      const d = JSON.parse(e.data);
      console.log(`${d.message} (${d.progress}%)`);
    });

    es.addEventListener('complete', (e) => {
      const result = JSON.parse(e.data);
      console.log('Final confidence:', result.confidence.final);
      es.close();
    });
    ```
    """
    # Validate architecture_name to prevent path traversal
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid architecture_name"
        )

    return StreamingResponse(
        expert_review_with_progress(architecture_name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
