# API Endpoints Audit

**Last Updated:** 2026-05-23  
**Purpose:** Document all active API endpoints and identify unnecessary ones

---

## Active Endpoints (Team 1 - Deterministic Engine)

### **Core Analysis**

| Endpoint | Method | Purpose | Status | Keep? |
|----------|--------|---------|--------|-------|
| `/health` | GET | Health check | ✅ Active | ✅ YES |
| `/api/v1/analyze-stream` | POST | SSE streaming analysis | ✅ Active | ✅ YES |

### **Reports & Artifacts**

| Endpoint | Method | Purpose | Status | Keep? |
|----------|--------|---------|--------|-------|
| `/api/v1/reports` | GET | List all architectures | ✅ Active | ✅ YES |
| `/api/v1/reports/{arch}` | GET | List reports for arch | ✅ Active | ✅ YES |
| `/api/v1/reports/{arch}/files/{file}` | GET | Download specific file | ✅ Active | ✅ YES |
| `/api/v1/reports/{arch}/summary` | GET | Quick summary | ✅ Active | ✅ YES |

### **Reference Data**

| Endpoint | Method | Purpose | Status | Keep? |
|----------|--------|---------|--------|-------|
| `/api/v1/techniques` | GET | MITRE technique names | ✅ Active | ✅ YES |

### **Dashboard**

| Endpoint | Method | Purpose | Status | Keep? |
|----------|--------|---------|--------|-------|
| `/` | GET | Redirect to dashboard | ✅ Active | ✅ YES |
| `/dashboard` | GET | Serve dashboard UI | ✅ Active | ✅ YES |

---

## Removed Endpoints

| Endpoint | Removed | Reason |
|----------|---------|--------|
| `/api/v1/config` | 2026-05-23 | Security risk - exposed masked API key |
| `/api/v1/techniques` (duplicate) | 2026-05-23 | Duplicate in app.py (already in reports router) |

---

## Future Endpoints (Not Yet Implemented)

### **Team 2 & 3 - MoE Validation** (Stage 2 Phase 2C)

| Endpoint | Method | Purpose | ETA |
|----------|--------|---------|-----|
| `/api/v1/validate` | POST | MoE validation critics | TBD |
| `/api/v1/orchestrate` | POST | Full pipeline (analyze + validate) | TBD |

### **Batch & Async** (Future)

| Endpoint | Method | Purpose | ETA |
|----------|--------|---------|-----|
| `/api/v1/reports/{arch}/download` | GET | ZIP download | TBD |
| `/api/v1/webhooks` | POST | Webhook registration | TBD |
| `/api/v1/jobs` | GET | List background jobs | TBD |
| `/api/v1/jobs/{id}` | GET | Job status polling | TBD |

---

## File Types Supported

### **Reports API** (`/api/v1/reports/{arch}/files/{file}`)

| Extension | Type | Content-Type | Purpose |
|-----------|------|--------------|---------|
| `.json` | json | `application/json` | Ground truth, critiques |
| `.md` | markdown | `text/markdown` | Executive, technical, action plan |
| `.mmd` | mermaid | `text/plain` | **before.mmd**, **after.mmd** diagrams |
| `.txt` | text | `text/plain` | Other text files |

**Updated:** Added `.mmd` → `mermaid` type detection (2026-05-23)

---

## Generated Artifacts (Team 1)

**Location:** `report/{architecture_name}/`

### **Always Generated:**

1. `ground_truth.json` - Complete analysis data (JSON)
2. `01_executive_summary.md` - Executive summary (Markdown)
3. `02_technical_report.md` - Technical details (Markdown)
4. `03_action_plan.md` - Control recommendations (Markdown)
5. **`before.mmd`** - Original architecture diagram (Mermaid)
6. **`after.mmd`** - Architecture with controls (Mermaid)

### **Optional (MoE Validation - Team 2 & 3):**

7. `04_architect_critique.json` - Architect critic (JSON)
8. `05_tester_critique.json` - Tester critic (JSON)
9. `06_red_team_critique.json` - Red team critic (JSON)
10. `07_orchestrator_report.json` - Orchestrator synthesis (JSON)
11. `08_improvement_summary.md` - Improvement summary (Markdown)
12. `08a_quick_wins.mmd` - Quick wins diagram (Mermaid)
13. `08b_recommended_target.mmd` - Recommended target diagram (Mermaid)
14. `08c_maximum_security.mmd` - Maximum security diagram (Mermaid)
15. `README.md` - Report navigation (Markdown)

**Total:** 6 files (Team 1) or 15 files (Team 1+2+3)

---

## API Usage by Dashboard

### **Dashboard Tab → API Calls**

| Tab | API Endpoints Used |
|-----|-------------------|
| **Overview** | `/api/v1/analyze-stream` (SSE) |
| **Patterns** | `/api/v1/analyze-stream` (SSE) |
| **Attacks** | `/api/v1/analyze-stream` (SSE) |
| **Controls** | `/api/v1/analyze-stream` (SSE) |
| **Visualise** | `/api/v1/reports/{arch}/files/before.mmd` (future) |
| **Visualise** | `/api/v1/reports/{arch}/files/after.mmd` (future) |
| **MITRE** | `/api/v1/techniques?technique_ids=...` |
| **AI/ML** | `/api/v1/analyze-stream` (SSE) |
| **Reports** | `/api/v1/reports/{arch}` |
| **Reports** | `/api/v1/reports/{arch}/files/{file}` |
| **Raw Data** | `/api/v1/reports/{arch}/summary` |

**Note:** Visualise tab currently uses stored content from upload, should fetch from `/api/v1/reports/{arch}/files/before.mmd` and `after.mmd`

---

## Security Audit

### **Authentication**

| Endpoint | Auth Required? | Method |
|----------|----------------|--------|
| `/health` | ❌ No | Public |
| `/dashboard` | ❌ No | Public (localhost) |
| `/api/v1/analyze-stream` | ✅ Yes | `TM-API-KEY` header |
| `/api/v1/reports/*` | ❌ No | Public (read-only) |
| `/api/v1/techniques` | ❌ No | Public (read-only) |

**Security Issues:**

1. ⚠️ **Reports API is public** - Anyone can read generated reports
   - **Risk:** Low (localhost only)
   - **Fix:** Add authentication in production
   
2. ⚠️ **Dashboard is public** - Anyone can access dashboard
   - **Risk:** Low (localhost only)
   - **Fix:** Add reverse proxy with basic auth in production

3. ⚠️ **API key in localStorage** - Visible in browser DevTools
   - **Risk:** Medium (XSS vulnerability)
   - **Fix:** Use HTTP-only cookies or proper session management

### **Rate Limiting**

| Endpoint | Limit | Status |
|----------|-------|--------|
| `/api/v1/analyze-stream` | None | ⚠️ TODO |
| `/api/v1/reports/*` | None | ⚠️ TODO |

**Recommendation:** Add rate limiting (10 req/min for analysis, 60 req/min for reports)

---

## Unnecessary Endpoints (Removed)

### **1. `/api/v1/config` - REMOVED**

**What it did:**
```json
{
  "api_key_configured": true,
  "hint": "05e5...22d2",
  "key_length": 64
}
```

**Why removed:**
- Exposed masked API key (security risk)
- Even partial key exposure is dangerous
- Not needed for functionality

**Alternative:**
- Users get key from `.env` file directly
- No server-side key hint needed

### **2. `/api/v1/techniques` (in app.py) - REMOVED**

**What happened:**
- Duplicate endpoint in two places
- `app.py` had direct endpoint
- `routes/reports.py` had router endpoint

**Fix:**
- Removed from `app.py`
- Kept in `routes/reports.py` (proper routing)

---

## API Specification Files

### **Main Documentation:**

1. **`docs/API_SPECIFICATION.md`** - Complete API spec for downstream apps
2. **`docs/API_AUDIT.md`** - This file (endpoint audit)
3. **`chatbot/api/app.py`** - FastAPI OpenAPI auto-generation

### **OpenAPI Documentation:**

**Available at:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## Recommendations

### **Immediate (Team 1):**

1. ✅ **DONE:** Remove duplicate `/api/v1/techniques`
2. ✅ **DONE:** Remove `/api/v1/config` security risk
3. ✅ **DONE:** Add `.mmd` type detection for before/after diagrams
4. ⚠️ **TODO:** Update dashboard Visualise tab to fetch from `/api/v1/reports/{arch}/files/before.mmd`

### **Near-Term:**

1. Add rate limiting middleware
2. Add CORS configuration for production
3. Add request/response logging
4. Add metrics endpoint (Prometheus)

### **Production:**

1. Add authentication to Reports API
2. Add reverse proxy (nginx) with basic auth
3. Move API key from localStorage to HTTP-only cookies
4. Add HTTPS/TLS
5. Add API versioning strategy

---

## Summary

**Active Endpoints:** 9  
**Removed Endpoints:** 2  
**Future Endpoints:** 6  

**Team 1 API Complete:** ✅ All endpoints working  
**Security Issues:** ⚠️ 2 addressed, rate limiting pending  
**Documentation:** ✅ Complete  

**Next Steps:**
1. Update Visualise tab to use Reports API for diagrams
2. Add rate limiting
3. Production deployment guide
