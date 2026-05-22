# Next Steps: Stage 2 Phase 2B - FastAPI Router

**Date:** 2026-05-22  
**Status:** ✅ Ready to Start  
**Estimated Time:** 2 hours

---

## 📍 You Are Here

**Tactical Guide:** This document covers **Phase 2B implementation** (2 hours)  
**Strategic Context:** See [PRODUCT_ROADMAP.html](specs/PRODUCT_ROADMAP.html) for full Stage 2 vision  
**Current Status:** See [STATUS_AND_PLAN.md](../STATUS_AND_PLAN.md) for overall project progress

---

## Quick Context: Where We Are

✅ **Completed:**
- Phase 3D: Mixture of Experts (MoE) validation system
- Bug Fix Phase: Database coverage + validator fixes
- Hardening Phase: Gap-filling controls with purple visual distinction
- Service Layer (Phase 2A): Thread-safe foundation + wrappers

✅ **Current State:**
- Deterministic engine: 99.5% confidence
- MoE validation: 93-96% final confidence
- Service layer: 6/6 tests passing
- Database coverage: 100%
- AI/ML patterns: Working (ATLAS + ARC)

🎯 **Next:** Build FastAPI REST API on top of service layer

---

## Phase 2B: FastAPI Router (2h)

### Goal
Create REST API endpoints for the 4 agent teams using existing service layer.

### Prerequisites (All Met ✅)
- [x] Service layer complete (`chatbot/services/`)
- [x] Thread-safe by design
- [x] Request isolation working
- [x] Error handling tested
- [x] MitreCache singleton working

### Files to Create

#### 1. FastAPI Application Factory
**File:** `chatbot/api/app.py`
```python
from fastapi import FastAPI
from chatbot.api.routes import analysis, critique, orchestration, health

def create_app() -> FastAPI:
    app = FastAPI(
        title="ThreatAssessor API",
        version="1.3-dev",
        description="Architecture threat analysis with MITRE ATT&CK + AI/ML"
    )
    
    # Register routes
    app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])
    app.include_router(critique.router, prefix="/api/v1", tags=["critique"])
    app.include_router(orchestration.router, prefix="/api/v1", tags=["orchestration"])
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    
    return app
```

**Time:** 15 min

#### 2. Analysis Route (Team 1: Deterministic Engine)
**File:** `chatbot/api/routes/analysis.py`
```python
from fastapi import APIRouter, HTTPException
from chatbot.services import ThreatAnalysisService
from chatbot.api.models.requests import AnalysisRequest
from chatbot.api.models.responses import AnalysisResponse

router = APIRouter()

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_architecture(request: AnalysisRequest):
    """
    Analyze architecture diagram with deterministic engine.
    
    Returns: Attack paths + control recommendations + RAPIDS assessment
    """
    service = ThreatAnalysisService()
    result = service.safe_execute(
        architecture_path=request.architecture_path,
        include_validation=request.include_validation
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return AnalysisResponse(**result.data)
```

**Time:** 20 min

#### 3. Critique Route (Team 2: MoE Critics)
**File:** `chatbot/api/routes/critique.py`
```python
from fastapi import APIRouter, HTTPException
from chatbot.services import ValidationService
from chatbot.api.models.requests import CritiqueRequest
from chatbot.api.models.responses import CritiqueResponse

router = APIRouter()

@router.post("/critique", response_model=CritiqueResponse)
async def critique_analysis(request: CritiqueRequest):
    """
    Run MoE validation critics on existing analysis.
    
    Returns: Architect + Tester + Red Team critiques
    """
    service = ValidationService()
    result = service.safe_execute(
        report_dir=request.report_dir,
        critics=request.critics or ["architect", "tester", "red_team"]
    )
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return CritiqueResponse(**result.data)
```

**Time:** 20 min

#### 4. Orchestration Route (Team 3: MoE Orchestrator)
**File:** `chatbot/api/routes/orchestration.py`
```python
from fastapi import APIRouter, HTTPException
from chatbot.modules.agents import run_moe_pipeline
from chatbot.api.models.requests import OrchestrationRequest
from chatbot.api.models.responses import OrchestrationResponse

router = APIRouter()

@router.post("/orchestrate", response_model=OrchestrationResponse)
async def orchestrate_full_pipeline(request: OrchestrationRequest):
    """
    Run complete MoE pipeline: deterministic + critics + consensus.
    
    Returns: Unified assessment with final confidence
    """
    try:
        result = run_moe_pipeline(request.report_dir)
        return OrchestrationResponse(
            success=True,
            final_confidence=result.final_confidence,
            consensus=result.consensus,
            critiques=result.critiques
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Time:** 20 min

#### 5. Health Check Route
**File:** `chatbot/api/routes/health.py`
```python
from fastapi import APIRouter
from chatbot.api.models.responses import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """System health check."""
    return HealthResponse(
        status="healthy",
        version="1.3-dev",
        services={
            "deterministic_engine": "operational",
            "moe_validation": "operational",
            "service_layer": "operational"
        }
    )
```

**Time:** 10 min

#### 6. Request Models (Pydantic Schemas)
**File:** `chatbot/api/models/requests.py`
```python
from pydantic import BaseModel, Field
from typing import Optional, List

class AnalysisRequest(BaseModel):
    architecture_path: str = Field(..., description="Path to architecture diagram (.mmd)")
    include_validation: bool = Field(default=True, description="Run completeness validation")

class CritiqueRequest(BaseModel):
    report_dir: str = Field(..., description="Path to report directory")
    critics: Optional[List[str]] = Field(None, description="Critics to run (default: all)")

class OrchestrationRequest(BaseModel):
    report_dir: str = Field(..., description="Path to report directory")
```

**Time:** 15 min

#### 7. Response Models (Pydantic Schemas)
**File:** `chatbot/api/models/responses.py`
```python
from pydantic import BaseModel
from typing import Dict, List, Any, Optional

class AnalysisResponse(BaseModel):
    success: bool
    confidence: float
    attack_paths: List[Dict]
    control_recommendations: List[Dict]
    rapids_assessment: Dict

class CritiqueResponse(BaseModel):
    success: bool
    critiques: Dict[str, Any]
    issues_found: List[str]

class OrchestrationResponse(BaseModel):
    success: bool
    final_confidence: float
    consensus: Dict
    critiques: Dict

class HealthResponse(BaseModel):
    status: str
    version: str
    services: Dict[str, str]
```

**Time:** 20 min

---

## Implementation Checklist

### Setup (10 min)
- [ ] Create directory structure:
  ```bash
  mkdir -p chatbot/api/routes
  mkdir -p chatbot/api/models
  touch chatbot/api/__init__.py
  touch chatbot/api/routes/__init__.py
  touch chatbot/api/models/__init__.py
  ```
- [ ] Install FastAPI dependencies (if not already):
  ```bash
  pip install fastapi uvicorn pydantic
  ```

### Implementation (90 min)
- [ ] Create `chatbot/api/app.py` (15 min)
- [ ] Create `chatbot/api/routes/analysis.py` (20 min)
- [ ] Create `chatbot/api/routes/critique.py` (20 min)
- [ ] Create `chatbot/api/routes/orchestration.py` (20 min)
- [ ] Create `chatbot/api/routes/health.py` (10 min)
- [ ] Create `chatbot/api/models/requests.py` (15 min)
- [ ] Create `chatbot/api/models/responses.py` (20 min)

### Testing (20 min)
- [ ] Test health endpoint:
  ```bash
  uvicorn chatbot.api.app:create_app --reload
  curl http://localhost:8000/api/v1/health
  ```
- [ ] Test analysis endpoint (POST with JSON)
- [ ] Test error handling (invalid paths)

---

## Success Criteria

✅ **API Running:**
- FastAPI starts without errors
- Health endpoint returns 200
- All routes registered

✅ **Analysis Endpoint:**
- Accepts architecture path
- Returns analysis response
- Service layer integration working

✅ **Critique Endpoint:**
- Accepts report directory
- Runs MoE critics
- Returns critiques

✅ **Orchestration Endpoint:**
- Runs full pipeline
- Returns final confidence
- Consensus synthesis working

✅ **Documentation:**
- OpenAPI docs auto-generated at `/docs`
- Request/response schemas visible
- Example requests provided

---

## After Phase 2B: Next Phases

See [PRODUCT_ROADMAP.html](specs/PRODUCT_ROADMAP.html#stage-2-phases) for complete Stage 2 roadmap:

- **Phase 2C:** API Testing (2h) - Endpoint tests, concurrent requests, error scenarios
- **Phase 2D:** Docker Compose (2h) - Containerization, volume mounts, deployment testing
- **Phase 2E:** API Documentation (2h) - OpenAPI descriptions, example requests, user guide
- **Phase 2F:** Integration Testing (2h) - End-to-end workflows, load testing, benchmarks

**Total Stage 2 Remaining:** 8 hours (4 phases × 2h after Phase 2B)

---

## Reference Documentation

**Service Layer (Already Complete):**
- `chatbot/services/base_service.py` - ServiceContext, ServiceResult, MitreCache
- `chatbot/services/threat_analysis_service.py` - Team 1 wrapper
- `chatbot/services/validation_service.py` - Team 2+3 wrapper

**Tests (6/6 passing):**
- `tests/test_services_concurrent.py` - Thread safety validation

**Phase Documentation:**
- `docs/completed/bugfix_phase/PHASE_BUGFIX_HARDENING_COMPLETE.md` - Latest completed phase
- `docs/phases/phase3d/` - MoE architecture details
- `STATUS_AND_PLAN.md` - Current project status

---

## Quick Start Command (When Ready)

```bash
# Start FastAPI development server
uvicorn chatbot.api.app:create_app --reload --host 0.0.0.0 --port 8000

# Test health endpoint
curl http://localhost:8000/api/v1/health

# View auto-generated API docs
open http://localhost:8000/docs
```

---

**Status:** 🎯 Ready to start Phase 2B  
**Prerequisites:** ✅ All met  
**Expected Duration:** 2 hours  
**Next Document:** This file will be updated with Phase 2C details after 2B completion
