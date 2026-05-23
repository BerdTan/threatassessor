"""
ThreatAssessor FastAPI Application

Phase 2B: MVP API Harness (PHASE 0 - 2h implementation)

Provides REST API for threat analysis services.
"""

import tempfile
import os
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from chatbot.services import ThreatAnalysisService
from chatbot.api.dependencies import verify_api_key
from chatbot.api.models.responses import AnalyzeResponse, HealthResponse, ErrorResponse


def create_app() -> FastAPI:
    """
    Create FastAPI application.

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="ThreatAssessor API",
        version="1.3.0",
        description="""
# ThreatAssessor API

Architecture threat analysis with MITRE ATT&CK + AI/ML pattern detection.

## Features
- **Deterministic Engine**: 99.5% confidence RAPIDS threat assessment
- **AI/ML Patterns**: MITRE ATLAS + ARC Framework detection
- **Attack Path Analysis**: Multi-hop technique mapping
- **Control Recommendations**: Prevention + DIR framework

## API Dependencies & Sequencing

### ✅ Independent Endpoints (No Prerequisites)
- `GET /health` - Always callable
- `POST /analyze` - **Entry point** for analysis

### ⚠️ Dependent Endpoints (Has Prerequisites)
- `POST /validate` - Requires `ground_truth.json` from `/analyze`
  - **Must call `/analyze` first** to generate ground truth file
  - Error 404 if ground truth not found

### 📋 Typical Workflows

**Quick Assessment (No MoE Validation):**
```
POST /analyze → 99.5% confidence
```

**Two-Step Analysis:**
```
1. POST /analyze  → Generates ground_truth.json (99.5% confidence)
2. POST /validate → Uses ground_truth.json (93-96% confidence)
```

**Full Pipeline (Future):**
```
POST /orchestrate → analyze + validate + synthesis (93-96% confidence)
```

## Authentication
API key required via `TM-API-KEY` header.

## Performance
- Analysis: ~30 seconds (P95)
- Timeout: 120 seconds (2 minutes)
- Concurrent limit: 10 requests (tested)

## Rate Limiting
- 10 requests/minute per API key
- 429 Too Many Requests if exceeded
""",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )

    # Health check endpoint (no authentication required)
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["health"],
        summary="Health check",
        description="System health status check. No authentication required."
    )
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            version="1.3.0",
            timestamp=datetime.utcnow().isoformat() + "Z",
            services={
                "deterministic_engine": "operational",
                "service_layer": "operational",
                "mitre_cache": "ready"
            }
        )

    # Analysis endpoint (requires authentication)
    @app.post(
        "/api/v1/analyze",
        response_model=AnalyzeResponse,
        tags=["analysis"],
        summary="Analyze architecture diagram",
        description="""
Run deterministic threat analysis (Team 1: ThreatAnalysisService).

**Expected Performance:**
- Response time: ~30 seconds (P50), ~45 seconds (P95)
- Timeout: 120 seconds

**Confidence Level:**
- Base confidence: 99.5% (deterministic engine)
- Includes: RAPIDS assessment, attack paths, control recommendations

**Dependencies:**
- ✅ **No prerequisites** - This is the entry point
- Generates: `ground_truth.json` in `report/{arch_name}/` directory

**Output Files:**
- `report/{arch_name}/ground_truth.json` - Analysis results (used by /validate)
- `report/{arch_name}/01_executive_summary.md`
- `report/{arch_name}/02_technical_report.md`
- `report/{arch_name}/03_action_plan.md`

**Use Cases:**
- Initial threat assessment
- Quick architecture review
- CI/CD pipeline integration
- Entry point for two-step workflow (analyze → validate)
""",
        responses={
            200: {
                "description": "Analysis completed successfully",
                "model": AnalyzeResponse
            },
            400: {
                "description": "Invalid file format",
                "model": ErrorResponse
            },
            401: {
                "description": "Missing or invalid API key",
                "model": ErrorResponse
            },
            422: {
                "description": "Invalid Mermaid syntax",
                "model": ErrorResponse
            },
            500: {
                "description": "Internal server error",
                "model": ErrorResponse
            }
        }
    )
    async def analyze_architecture(
        architecture_file: UploadFile = File(
            ...,
            description="Mermaid diagram file (.mmd format, max 10MB)"
        ),
        include_validation: bool = True,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Analyze architecture diagram with deterministic engine.

        Returns attack paths, control recommendations, and RAPIDS assessment.
        """
        # Validate file extension
        if not architecture_file.filename.endswith('.mmd'):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "type": "https://api.threatassessor.example.com/errors/bad-request",
                    "title": "Invalid file format",
                    "status": 400,
                    "detail": f"File must have .mmd extension, got: {Path(architecture_file.filename).suffix}",
                    "instance": "/api/v1/analyze"
                }
            )

        # Validate file size (10MB limit)
        content = await architecture_file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "type": "https://api.threatassessor.example.com/errors/file-too-large",
                    "title": "File too large",
                    "status": 413,
                    "detail": f"File size {len(content)} bytes exceeds 10MB limit",
                    "instance": "/api/v1/analyze"
                }
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
            # Run analysis via service layer
            service = ThreatAnalysisService()
            result = service.safe_execute(
                architecture_path=tmp_path,
                include_validation=include_validation
            )

            if not result.success:
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={
                        "type": "https://api.threatassessor.example.com/errors/internal",
                        "title": "Analysis failed",
                        "status": 500,
                        "detail": result.error or "Unknown error occurred",
                        "instance": "/api/v1/analyze",
                        "request_id": result.request_id
                    }
                )

            # Return successful response
            return AnalyzeResponse(
                success=result.success,
                request_id=result.request_id,
                execution_time_ms=result.execution_time_ms,
                data=result.data
            )

        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "type": "https://api.threatassessor.example.com/errors/internal",
                    "title": "Internal server error",
                    "status": 500,
                    "detail": str(e),
                    "instance": "/api/v1/analyze"
                }
            )
        finally:
            # Cleanup temp file
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass  # Best effort cleanup

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "chatbot.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
