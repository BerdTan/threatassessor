"""
ThreatAssessor FastAPI Application

Phase 2B: MVP API Harness (PHASE 0 - 2h implementation)

Provides REST API for threat analysis services.
"""

import tempfile
import os
import threading
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from chatbot.services import ThreatAnalysisService
from chatbot.api.dependencies import verify_api_key
from chatbot.api.models.responses import AnalyzeResponse, HealthResponse, ErrorResponse

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Warmup event — set when MITRE + ATLAS singletons are ready in memory.
# The server starts immediately; warmup runs in a background thread (~0.2-0.6s).
_warmup_done = threading.Event()


def _background_warmup():
    try:
        from chatbot.modules.mitre import get_mitre_helper
        from chatbot.modules.pattern_registry import get_pattern_registry
        mitre = get_mitre_helper()
        registry = get_pattern_registry()
        logger.info(
            f"Warmup complete: {len(mitre.techniques)} MITRE techniques, "
            f"patterns={registry.list_patterns()}"
        )
    except Exception as e:
        logger.error(f"Warmup failed: {e}")
    finally:
        _warmup_done.set()


def create_app() -> FastAPI:
    """
    Create FastAPI application.

    Returns:
        Configured FastAPI app
    """
    # Kick off MITRE + ATLAS preload in a background thread so the server
    # becomes reachable instantly. The singletons are ready within ~0.2s
    # (pickle cache hit) or ~1s (first boot JSON parse).
    threading.Thread(target=_background_warmup, daemon=True, name="mitre-warmup").start()

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

    # CORS middleware — origins read from env var, falling back to localhost defaults
    _raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    _allowed_origins = (
        [o.strip() for o in _raw_origins.split(",") if o.strip()]
        if _raw_origins.strip()
        else ["http://localhost:8000", "http://localhost:3000"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["TM-API-KEY", "Content-Type"],
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
                "mitre_cache": "ready" if _warmup_done.is_set() else "loading"
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

    # Mount static files with cache control
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir), html=False), name="static")

    # Add cache control middleware for static files
    @app.middleware("http")
    async def add_cache_control_headers(request, call_next):
        """Add cache control headers to prevent stale JS/CSS."""
        response = await call_next(request)

        # Static files should not be cached during development (allow Ctrl+F5)
        if request.url.path.startswith("/static/"):
            # Allow caching but require revalidation (Ctrl+F5 will refresh)
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
            response.headers["ETag"] = f'"{hash(request.url.path)}"'

        return response

    # Custom 404 handler for static files (prevent HTML being served as JS/CSS)
    @app.exception_handler(404)
    async def custom_404_handler(request: Request, exc: StarletteHTTPException):
        """Return proper 404 response based on request type."""
        # If requesting static file, return plain text (not HTML)
        if request.url.path.startswith("/static/"):
            return PlainTextResponse(
                content=f"Static file not found: {request.url.path}",
                status_code=404
            )

        # For API requests, return JSON
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=404,
                content={
                    "type": "https://api.threatassessor.example.com/errors/not-found",
                    "title": "Not Found",
                    "status": 404,
                    "detail": f"The requested endpoint does not exist: {request.url.path}",
                    "instance": request.url.path
                }
            )

        # For dashboard requests, return HTML
        return HTMLResponse(
            content=f"<h1>404 Not Found</h1><p>Page not found: {request.url.path}</p>",
            status_code=404
        )

    # Dashboard endpoint with cache busting
    _startup_time = str(int(datetime.utcnow().timestamp()))

    @app.get("/dashboard", response_class=HTMLResponse, tags=["dashboard"])
    async def dashboard():
        """Serve the ThreatAssessor dashboard UI with cache busting."""
        index_path = static_dir / "index.html"
        if index_path.exists():
            html_content = index_path.read_text()

            # Add cache-busting version parameter to static file URLs
            # This changes on every server restart, forcing Ctrl+F5 to work
            import re
            # Replace all static file references with version parameter
            html_content = re.sub(
                r'(src|href)="(/static/[^"]+)"',
                rf'\1="\2?v={_startup_time}"',
                html_content
            )

            return HTMLResponse(
                content=html_content,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        return "<h1>Dashboard not found</h1><p>Static files may not be properly configured.</p>"

    @app.get("/", response_class=HTMLResponse, tags=["dashboard"])
    async def root():
        """Redirect root to dashboard."""
        return """
        <html>
            <head>
                <meta http-equiv="refresh" content="0; url=/dashboard">
            </head>
            <body>
                <p>Redirecting to <a href="/dashboard">dashboard</a>...</p>
            </body>
        </html>
        """

    # Include routers
    from chatbot.api.routes import streaming_router, reports_router
    app.include_router(streaming_router)
    app.include_router(reports_router)

    # Enrich OpenAPI spec: add server URL and API key security scheme
    from fastapi.openapi.utils import get_openapi

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema["servers"] = [
            {"url": "http://localhost:8000", "description": "Local development"},
        ]
        schema.setdefault("components", {})
        schema["components"]["securitySchemes"] = {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "TM-API-KEY",
            }
        }
        # Apply security to all non-health paths
        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if path not in ("/health", "/dashboard", "/") and method in ("get", "post", "put", "delete", "patch"):
                    operation.setdefault("security", [{"ApiKeyAuth": []}])
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

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
