# Stage 2: API Layer Implementation

**Goal:** Transform ThreatAssessor into API-ready service with 4 agent teams  
**Status:** 🚧 In Progress  
**Time:** 12h estimated (broken into 6 phases)  
**Confidence Target:** Maintain 94.5% ±1%

---

## Architecture Design

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Server                      │
│                   (Thread-safe Router)                  │
└────────────┬────────────────────────────────────────────┘
             │
    ┌────────┴────────┐
    │  Service Layer  │ (Request Isolation)
    └────────┬────────┘
             │
    ┌────────┴─────────────────────────────────────┐
    │                                               │
┌───▼──────────┐  ┌─────────────┐  ┌──────────────┐
│ Team 1       │  │ Team 2      │  │ Team 3       │
│ Deterministic│  │ Critic      │  │ Orchestration│
│ Engine       │  │ Engine (MoE)│  │ Engine       │
└───┬──────────┘  └─────┬───────┘  └──────┬───────┘
    │                   │                  │
    │                   │                  │
┌───▼──────────┐  ┌─────▼───────┐  ┌──────▼───────┐
│ PatternRegistry│ │ 3 Critics   │ │ Consensus    │
│ RAPIDS+ATLAS  │  │ Sequential  │ │ Synthesis    │
│ Cloud+ICS     │  │ Validation  │ │ Report Gen   │
└───────────────┘  └─────────────┘  └──────────────┘
```

**Team 4 (Parsing):** Embedded in Team 1 (Mermaid parser)

---

## Implementation Plan

### Phase 2A: Service Layer Foundation (2h)
**Goal:** Request isolation + thread safety

**Files to create:**
```
chatbot/services/
├── __init__.py              # Service exports
├── base_service.py          # Base service with context isolation
├── threat_analysis_service.py  # Team 1 wrapper
└── validation_service.py    # Team 2+3 wrapper
```

**Key features:**
- Request context isolation (no shared state)
- Thread-safe MITRE cache (singleton with RLock)
- Error handling with structured responses

**Validation:**
- Unit test: concurrent requests
- Smoke test: 3 parallel analyses

### Phase 2B: FastAPI Router (2h)
**Goal:** Core endpoints for all 4 teams

**Files to create:**
```
chatbot/api/
├── __init__.py
├── app.py                   # FastAPI app factory
├── routes/
│   ├── __init__.py
│   ├── analysis.py          # Team 1 endpoint
│   ├── critique.py          # Team 2 endpoint
│   ├── orchestration.py     # Team 3 endpoint
│   └── health.py            # Health check
└── models/
    ├── __init__.py
    ├── requests.py          # Request schemas
    └── responses.py         # Response schemas
```

**Endpoints:**
```
POST /api/v1/analyze           # Team 1: Deterministic analysis
POST /api/v1/critique          # Team 2: MoE validation
POST /api/v1/orchestrate       # Team 3: Full pipeline
GET  /api/v1/health            # Health check
GET  /api/v1/patterns          # List available patterns
```

**Validation:**
- Integration test: All endpoints
- Smoke test: End-to-end request

### Phase 2C: Pattern Registry API (1.5h)
**Goal:** Dynamic pattern registration (Team 1)

**Features:**
- List available patterns (RAPIDS, ATLAS, Cloud, ICS)
- Register custom patterns
- Query pattern metadata

**New endpoints:**
```
GET  /api/v1/patterns                    # List all
POST /api/v1/patterns/register           # Add custom
GET  /api/v1/patterns/{pattern_id}       # Get details
```

**Validation:**
- Test custom pattern registration
- Verify RAPIDS+ATLAS defaults

### Phase 2D: Error Handling + Logging (1.5h)
**Goal:** Production-ready observability

**Features:**
- Structured logging (JSON format)
- Request tracing (correlation IDs)
- Error standardization (RFC 7807)
- Performance metrics

**Files to create:**
```
chatbot/api/
├── middleware/
│   ├── __init__.py
│   ├── logging.py           # Request logging
│   ├── error_handler.py     # Global error handler
│   └── metrics.py           # Performance tracking
```

**Validation:**
- Test error responses (400, 404, 500)
- Verify correlation IDs

### Phase 2E: Documentation + Examples (2h)
**Goal:** Developer-ready API docs

**Create:**
- OpenAPI/Swagger docs (auto-generated)
- `examples/api_usage.py` - Python client
- `examples/api_curl.sh` - cURL examples
- API README with quickstart

**Validation:**
- Run all examples
- Verify Swagger UI works

### Phase 2F: Integration + Confidence Test (3h)
**Goal:** Validate Stage 2 maintains quality

**Tests:**
1. Run full MoE pipeline via API
2. Compare API output vs CLI output (must match)
3. Measure confidence on 3 architectures
4. Load test (10 concurrent requests)

**Validation criteria:**
- ✅ Confidence: 94.5% ±1%
- ✅ API response time: <5s (deterministic), <30s (full MoE)
- ✅ No race conditions under load
- ✅ Output matches CLI exactly

---

## Rollback Strategy

**Checkpoints:**
- Git tag: `stage2-start` (after Stage 1)
- Commit after each phase (2A-2F)
- If confidence drops >1%: Revert to last phase

**Max rollback window:** 3h per phase

---

## Success Criteria

✅ All 4 agent teams accessible via API  
✅ Thread-safe concurrent execution  
✅ Confidence maintained: 94.5% ±1%  
✅ Documentation complete  
✅ Example code working  
✅ CLI still functional (backward compat)

---

**Next:** Phase 2A - Service Layer Foundation
