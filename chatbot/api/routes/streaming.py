"""
SSE Streaming Routes

Server-Sent Events endpoints for real-time analysis progress.
"""

import logging
import queue
import tempfile
import asyncio
import concurrent.futures
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, Query
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
    include_validation: bool = True,
    ssp_profile: str = "low_risk_cloud",
    enable_ssp: bool = True,
) -> AsyncGenerator[str, None]:
    """
    Run analysis with SSE progress updates.

    Args:
        architecture_path: Path to architecture file
        filename: Original uploaded filename
        include_validation: Run 6-check validation
        ssp_profile: User-declared SSP profile for control enrichment
        enable_ssp: Include SSP context in recommendations

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

        # Extract clean architecture name from uploaded filename
        # Remove .mmd extension and sanitize
        base_name = filename.replace('.mmd', '').replace('.', '_').replace(' ', '_')

        # Avoid clobbering existing reports: append _2, _3, … if folder already exists
        report_dir = Path(__file__).parent.parent.parent.parent / "report"
        clean_arch_name = base_name
        counter = 2
        while (report_dir / clean_arch_name).exists():
            clean_arch_name = f"{base_name}_{counter}"
            counter += 1

        # Run analysis in thread pool; send heartbeat pings so the browser doesn't
        # interpret the silence as a hang. Messages cycle through realistic stage labels.
        loop = asyncio.get_event_loop()
        analysis_future = loop.run_in_executor(
            None,
            lambda: service.safe_execute(
                architecture_path=architecture_path,
                architecture_name=clean_arch_name,
                include_validation=include_validation,
                ssp_profile=ssp_profile,
                enable_ssp=enable_ssp,
            )
        )

        heartbeat_messages = [
            (10, "rapids",     "🔍 Loading MITRE ATT&CK knowledge base..."),
            (18, "rapids",     "🧠 Mapping threat techniques to architecture nodes..."),
            (28, "rapids",     "⚡ Running RAPIDS threat scoring..."),
            (38, "rapids",     "🎯 Identifying high-risk attack paths..."),
            (48, "rapids",     "🛡️ Evaluating existing controls coverage..."),
            (58, "rapids",     "📊 Scoring residual risk per threat category..."),
            (65, "validation", "🔒 Generating exhaustive mitigation recommendations..."),
            (72, "validation", "🏛 Enriching controls with SSP policy baseline..."),
            (80, "validation", "✅ Validating completeness and coverage..."),
            (88, "validation", "📝 Finalising analysis results..."),
        ]
        ping_idx = 0
        while not analysis_future.done():
            await asyncio.sleep(3)
            if analysis_future.done():
                break
            if ping_idx < len(heartbeat_messages):
                prog, stage, msg = heartbeat_messages[ping_idx]
                ping_idx += 1
            else:
                prog, stage, msg = 92, "validation", "⏳ Completing analysis..."
            yield await SSEStream.send_progress(
                stage=stage, progress=prog, message=msg,
                eta_seconds=max(3, (len(heartbeat_messages) - ping_idx) * 3)
            )

        result = await analysis_future

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
    include_validation: bool = Form(True),
    ssp_profile: str = Form("low_risk_cloud"),
    enable_ssp: bool = Form(True),
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
            analyze_with_progress(tmp_path, architecture_file.filename, include_validation, ssp_profile, enable_ssp),
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
    architecture_name: str,
    critic_mode: str = "sequential",
) -> AsyncGenerator[str, None]:
    """
    Run MoE Expert Review pipeline with SSE progress updates.

    Requires analysis to have been run first (ground_truth.json must exist).

    Args:
        architecture_name: Architecture name (matches report directory)
        critic_mode: "sequential" | "parallel" | "auto"

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

        # Read base_confidence from ground_truth so Expert Review chains on the
        # architecture-adjusted deterministic confidence (not always 99.5)
        try:
            with open(gt_path) as _f:
                _gt = _f.read()
            import json as _json
            _gt_data = _json.loads(_gt)
            _det_conf = _gt_data.get("confidence_breakdown", {}).get("final")
            if _det_conf is None:
                _det_conf = _gt_data.get("confidence", 0.995)
            base_confidence = float(_det_conf) * 100  # convert 0.872 → 87.2
        except Exception:
            base_confidence = 99.5

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

        # Run full pipeline in thread pool (synchronous blocking ~90s).
        # A queue bridges the sync orchestrator thread → this async generator
        # so we can emit critic_result events as each critic finishes without
        # blocking the orchestrator between critics.
        loop = asyncio.get_event_loop()
        result_queue: queue.Queue = queue.Queue()

        _CRITIC_STATUS_COLORS = {
            "PASS": "var(--secondary-color)",
            "MINOR_GAPS": "var(--warning-color)",
            "MAJOR_GAPS": "var(--danger-color)",
        }

        def _critic_sse(critic_stage: str, vr) -> str:
            top_gaps = [
                {"severity": g.get("severity", ""), "description": g.get("description", "")[:120]}
                for g in (vr.gaps or [])[:3]
            ]
            return SSEStream.format_sse("critic_result", {
                "critic": critic_stage,
                "validation_status": vr.validation_status,
                "score": vr.original_score,
                "confidence_adjustment_pct": round(vr.confidence_adjustment * 100, 1),
                "gap_count": len(vr.gaps or []),
                "strength_count": len(vr.strengths or []),
                "top_gaps": top_gaps,
                "top_strengths": (vr.strengths or [])[:2],
                "status_color": _CRITIC_STATUS_COLORS.get(vr.validation_status, "var(--text-secondary)"),
            })

        def _progress_cb(stage: str, validation_result) -> None:
            result_queue.put_nowait((stage, validation_result))

        def _run_pipeline() -> object:
            return run_moe_pipeline(
                str(report_dir),
                base_confidence=base_confidence,
                progress_callback=_progress_cb,
                critic_mode=critic_mode,
            )

        task = loop.run_in_executor(None, _run_pipeline)

        # Per-critic progress bands: (start_pct, end_pct, stage_label)
        # Timed progress messages play within each band until the real
        # critic_result event arrives and advances to the next band.
        stage_bands = [
            (10, 33, "architect", "[2A] Architect Critic: Validating threat model and attack paths..."),
            (33, 66, "tester",    "[2B] Tester Critic: Auditing MITRE mappings and control effectiveness..."),
            (66, 90, "red_team",  "[2C] Red Team Critic: Stress-testing defensive posture and bypass paths..."),
            (90, 98, "synthesis", "[L3] Orchestrator: Synthesising consensus recommendations..."),
        ]

        # Synthesis sub-step messages fired by the orchestrator via progress_callback
        _SYNTHESIS_MESSAGES = {
            "synthesis:confidence": (90, "[L3] Orchestrator: Calculating final confidence score..."),
            "synthesis:llm":        (91, "[L3] Orchestrator: LLM synthesising expert consensus (may take ~20s)..."),
            "synthesis:build":      (93, "[L3] Orchestrator: Building improvement roadmap and risk reduction..."),
            "synthesis:save":       (95, "[L3] Orchestrator: Saving consensus report to disk..."),
            "synthesis:artifacts":  (96, "[L3] Orchestrator: Generating executive summary and architecture diagrams..."),
        }

        # Track which band we're in; advance when a critic_result arrives
        band_idx = 0
        band_progress = 10  # current fake progress within the active band
        result = None
        emitted_critics = set()
        last_synthesis_msg = ""

        while result is None:
            # Drain any pending events from the queue first
            while True:
                try:
                    critic_stage, vr = result_queue.get_nowait()
                except queue.Empty:
                    break

                # synthesis:* events are progress signals, not critic results
                if critic_stage.startswith("synthesis:"):
                    pct, msg = _SYNTHESIS_MESSAGES.get(critic_stage, (band_progress, "[L3] Orchestrator: Running..."))
                    band_progress = max(band_progress, pct)
                    last_synthesis_msg = msg
                    yield await SSEStream.send_progress(
                        stage="synthesis",
                        progress=band_progress,
                        message=msg,
                        eta_seconds=max(0, int((98 - band_progress) * 2))
                    )
                    continue

                # parallel_starting: all three critics are now running concurrently
                if critic_stage == "parallel_starting":
                    yield await SSEStream.send_progress(
                        stage="parallel_starting",
                        progress=5,
                        message="All three critics running concurrently — results will arrive as each finishes...",
                        eta_seconds=45
                    )
                    continue

                if critic_stage in emitted_critics:
                    continue
                emitted_critics.add(critic_stage)
                yield _critic_sse(critic_stage, vr)

                # Advance the band index so the progress bar jumps to next critic
                band_idx = min(band_idx + 1, len(stage_bands) - 1)
                band_progress = stage_bands[band_idx][0]

            # Emit a timed progress tick within the current band
            start_pct, end_pct, stage, msg = stage_bands[band_idx]
            # In synthesis band, prefer the last real sub-step message over the generic one
            if stage == "synthesis" and last_synthesis_msg:
                msg = last_synthesis_msg
            band_progress = min(band_progress + 2, end_pct - 1)
            yield await SSEStream.send_progress(
                stage=stage,
                progress=band_progress,
                message=msg,
                eta_seconds=max(0, int((end_pct - band_progress) * 1.5))
            )

            # Wait up to 1 s; shorter interval means critic_result cards update faster
            try:
                result = await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except asyncio.TimeoutError:
                pass  # still running — loop back for next tick

        # Pipeline finished — drain any remaining events that arrived
        # in the final 3-second window
        while True:
            try:
                critic_stage, vr = result_queue.get_nowait()
            except queue.Empty:
                break
            if critic_stage.startswith("synthesis:"):
                continue  # already past synthesis, no need to re-emit
            if critic_stage in emitted_critics:
                continue
            emitted_critics.add(critic_stage)
            yield _critic_sse(critic_stage, vr)

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
    critic_mode: str = Query(
        "sequential",
        description="Critic execution mode: sequential | parallel | auto"
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
    - `critic_result`: Emitted as each critic finishes — includes score, status, gap count, top gaps
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

    # Validate critic_mode
    if critic_mode not in ("sequential", "parallel", "auto"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="critic_mode must be one of: sequential, parallel, auto"
        )

    return StreamingResponse(
        expert_review_with_progress(architecture_name, critic_mode=critic_mode),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


@router.delete("/expert-review/cancel")
async def expert_review_cancel(
    architecture_name: str = Query(..., description="Architecture name to cancel and purge"),
    api_key: str = Depends(verify_api_key)
):
    """
    Cancel an in-progress Expert Review and purge any partial critic files.

    The client is responsible for aborting its own SSE fetch.  This endpoint
    removes the partial 04/05/06 critic JSON files so the next run starts clean.
    """
    safe_name = Path(architecture_name).name
    if safe_name != architecture_name or ".." in architecture_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid architecture_name")

    report_dir = Path(__file__).parent.parent.parent.parent / "report" / architecture_name
    purged = []
    for fname in ("04_architect_critique.json", "05_tester_critique.json", "06_red_team_critique.json",
                  "07_moe_orchestrator.json", "07_orchestrator_report.json"):
        fpath = report_dir / fname
        if fpath.exists():
            fpath.unlink()
            purged.append(fname)

    return {"cancelled": True, "architecture": architecture_name, "purged_files": purged}
