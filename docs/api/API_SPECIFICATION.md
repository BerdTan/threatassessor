# ThreatAssessor API Specification for Downstream Applications

**Version:** 1.3.0  
**Last Updated:** 2026-05-23  
**Base URL:** `http://localhost:8000` (development) / `https://api.threatassessor.example.com` (production)

---

## Table of Contents

1. [Authentication](#authentication)
2. [Core Analysis APIs](#core-analysis-apis)
3. [Reports & Artifacts APIs](#reports--artifacts-apis)
4. [Reference Data APIs](#reference-data-apis)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Webhooks (Future)](#webhooks-future)

---

## Authentication

**Method:** API Key via header

```http
TM-API-KEY: your-secret-api-key-here
```

**Obtaining API Key:**
- Development: Set in `.env` file: `API_KEY=<your-key>`
- Production: Contact admin for provisioned key

**Security:**
- API keys are bearer tokens (treat as passwords)
- Use HTTPS in production
- Rotate keys quarterly

---

## Core Analysis APIs

### 1. Analyze Architecture (Streaming)

**Endpoint:** `POST /api/v1/analyze-stream`

**Description:** Run complete threat analysis with real-time SSE progress updates.

**Request:**
```http
POST /api/v1/analyze-stream
Content-Type: multipart/form-data
TM-API-KEY: your-key

architecture_file: <file.mmd>
include_validation: true
```

**Response:** Server-Sent Events (SSE) stream

**Event Types:**

1. **progress** - Stage progress updates
```json
{
  "stage": "parsing|mitre|rapids|ai_ml|validation|reports|complete",
  "progress": 45,
  "message": "[RAPIDS] 45% - Analyzing 6 threat categories...",
  "eta_seconds": 12,
  "patterns_active": ["rapids", "ai_ml_arc"]
}
```

2. **patterns_detected** - Threat patterns applied
```json
{
  "patterns": [
    {
      "pattern_id": "rapids",
      "name": "RAPIDS Threat Assessment",
      "category": "threat_modeling"
    },
    {
      "pattern_id": "ai_ml_arc",
      "name": "AI/ML (ARC + ATLAS)",
      "category": "ai_ml"
    }
  ]
}
```

3. **threat_scores** - Threat category scores
```json
{
  "scores_by_pattern": {
    "rapids": {
      "ransomware": {"risk": 65, "defensibility": 45},
      "application_vulns": {"risk": 72, "defensibility": 38},
      "phishing": {"risk": 55, "defensibility": 60},
      "insider_threat": {"risk": 48, "defensibility": 52},
      "dos": {"risk": 42, "defensibility": 68},
      "supply_chain": {"risk": 38, "defensibility": 55}
    }
  }
}
```

4. **attack_path** - Individual attack path discovered
```json
{
  "id": "AP-01",
  "entry": "Users",
  "target": "UserDB",
  "path": ["Users", "MobileApp", "APIGateway", "AuthService", "UserDB"],
  "techniques": ["T1566", "T1078", "T1190", "T1110", "T1213"],
  "per_node_techniques": {
    "Users": ["T1566", "T1078"],
    "APIGateway": ["T1190"],
    "AuthService": ["T1110"],
    "UserDB": ["T1213"]
  },
  "criticality_tier": "HIGH",
  "severity_score": 0.85,
  "hop_count": 5
}
```

5. **complete** - Final analysis result
```json
{
  "result": {
    "success": true,
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "execution_time_ms": 28734,
    "data": {
      "architecture_name": "web_app",
      "confidence": 0.995,
      "analysis": {
        "controls_present": ["waf", "mfa", "encryption"],
        "controls_missing": ["logging", "backup"],
        "expected_attack_paths": [...],
        "expected_risk_score": 77,
        "expected_defensibility": 54,
        "rapids_assessment": {...},
        "control_recommendations": [...]
      },
      "report_paths": {
        "ground_truth": "report/web_app/ground_truth.json",
        "executive": "report/web_app/01_executive_summary.md",
        "technical": "report/web_app/02_technical_report.md",
        "action_plan": "report/web_app/03_action_plan.md",
        "before_diagram": "report/web_app/before.mmd",
        "after_diagram": "report/web_app/after.mmd"
      }
    }
  }
}
```

6. **error** - Error occurred
```json
{
  "error_message": "Analysis failed",
  "detail": "Invalid Mermaid syntax at line 15"
}
```

**Client Example (JavaScript):**
```javascript
const eventSource = new EventSource('/api/v1/analyze-stream', {
  headers: { 'TM-API-KEY': 'your-key' }
});

eventSource.addEventListener('progress', (e) => {
  const data = JSON.parse(e.data);
  updateProgressBar(data.progress);
  updateStatusMessage(data.message);
});

eventSource.addEventListener('complete', (e) => {
  const result = JSON.parse(e.data).result;
  processAnalysisResult(result);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  console.error('SSE error:', e);
  eventSource.close();
});
```

**Client Example (Python):**
```python
import requests
import json

response = requests.post(
    'http://localhost:8000/api/v1/analyze-stream',
    headers={'TM-API-KEY': 'your-key'},
    files={'architecture_file': open('arch.mmd', 'rb')},
    data={'include_validation': 'true'},
    stream=True
)

for line in response.iter_lines():
    if line.startswith(b'event: '):
        event_type = line.decode()[7:]
    elif line.startswith(b'data: '):
        data = json.loads(line[6:])
        print(f"{event_type}: {data}")
```

---

### 2. Analyze Architecture (Non-Streaming)

**Endpoint:** `POST /api/v1/analyze`

**Description:** Run complete analysis and wait for full result (no progress updates).

**Request:**
```http
POST /api/v1/analyze
Content-Type: multipart/form-data
TM-API-KEY: your-key

architecture_file: <file.mmd>
include_validation: true
```

**Response (200 OK):**
```json
{
  "success": true,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "execution_time_ms": 28734,
  "data": {
    "architecture_name": "web_app",
    "confidence": 0.995,
    "analysis": {
      "controls_present": ["waf", "mfa", "encryption"],
      "controls_missing": ["logging", "backup"],
      "expected_attack_paths": [
        {
          "id": "AP-01",
          "entry": "Users",
          "target": "UserDB",
          "path": ["Users", "MobileApp", "APIGateway", "AuthService", "UserDB"],
          "techniques": ["T1566", "T1078", "T1190", "T1110", "T1213"],
          "per_node_techniques": {
            "Users": ["T1566", "T1078"],
            "APIGateway": ["T1190"],
            "AuthService": ["T1110"],
            "UserDB": ["T1213"]
          },
          "criticality_tier": "HIGH",
          "severity_score": 0.85,
          "hop_count": 5
        }
      ],
      "expected_risk_score": 77,
      "expected_defensibility": 54,
      "rapids_assessment": {
        "ransomware": {"risk": 65, "defensibility": 45},
        "application_vulns": {"risk": 72, "defensibility": 38},
        "phishing": {"risk": 55, "defensibility": 60},
        "insider_threat": {"risk": 48, "defensibility": 52},
        "dos": {"risk": 42, "defensibility": 68},
        "supply_chain": {"risk": 38, "defensibility": 55}
      },
      "control_recommendations": [
        {
          "control": "Multi-Factor Authentication (MFA)",
          "priority": "critical",
          "score": 95,
          "rationale": "Prevents credential-based attacks",
          "techniques": ["T1078", "T1110"],
          "mitigations": ["M1032", "M1036"],
          "attack_paths": [0, 1, 2],
          "control_type": "PREVENTION",
          "layer": "identity",
          "placement": "At Authentication Service hop"
        }
      ]
    },
    "report_paths": {
      "ground_truth": "report/web_app/ground_truth.json",
      "executive": "report/web_app/01_executive_summary.md",
      "technical": "report/web_app/02_technical_report.md",
      "action_plan": "report/web_app/03_action_plan.md",
      "before_diagram": "report/web_app/before.mmd",
      "after_diagram": "report/web_app/after.mmd"
    }
  }
}
```

**Timeout:** 120 seconds (2 minutes)

**Use Case:** Batch processing, CI/CD pipelines, scheduled scans

---

## Reports & Artifacts APIs

### 3. List All Architectures

**Endpoint:** `GET /api/v1/reports`

**Description:** Get list of all analyzed architectures.

**Response (200 OK):**
```json
{
  "architectures": [
    {
      "name": "web_app",
      "report_count": 16,
      "files": [
        "01_executive_summary.md",
        "02_technical_report.md",
        "03_action_plan.md",
        "before.mmd",
        "after.mmd",
        "ground_truth.json"
      ]
    },
    {
      "name": "mobile_app",
      "report_count": 16,
      "files": [...]
    }
  ],
  "total": 2
}
```

---

### 4. List Reports for Architecture

**Endpoint:** `GET /api/v1/reports/{architecture_name}`

**Description:** Get all report files for specific architecture.

**Response (200 OK):**
```json
{
  "architecture": "web_app",
  "reports": [
    {
      "filename": "ground_truth.json",
      "type": "json",
      "size": 336607,
      "url": "/api/v1/reports/web_app/files/ground_truth.json"
    },
    {
      "filename": "01_executive_summary.md",
      "type": "markdown",
      "size": 3566,
      "url": "/api/v1/reports/web_app/files/01_executive_summary.md"
    },
    {
      "filename": "before.mmd",
      "type": "mermaid",
      "size": 1517,
      "url": "/api/v1/reports/web_app/files/before.mmd"
    },
    {
      "filename": "after.mmd",
      "type": "mermaid",
      "size": 6701,
      "url": "/api/v1/reports/web_app/files/after.mmd"
    }
  ],
  "count": 16
}
```

---

### 5. Get Report File

**Endpoint:** `GET /api/v1/reports/{architecture_name}/files/{filename}`

**Description:** Download specific report file.

**Response:**
- **200 OK:** File contents
- **Content-Type:**
  - `application/json` for `.json` files
  - `text/markdown` for `.md` files
  - `text/plain` for `.mmd` and `.txt` files

**Examples:**

```bash
# Get ground truth JSON
curl -H "TM-API-KEY: your-key" \
  http://localhost:8000/api/v1/reports/web_app/files/ground_truth.json

# Get executive summary markdown
curl -H "TM-API-KEY: your-key" \
  http://localhost:8000/api/v1/reports/web_app/files/01_executive_summary.md

# Get before diagram
curl -H "TM-API-KEY: your-key" \
  http://localhost:8000/api/v1/reports/web_app/files/before.mmd

# Get after diagram
curl -H "TM-API-KEY: your-key" \
  http://localhost:8000/api/v1/reports/web_app/files/after.mmd
```

---

### 6. Get Report Summary

**Endpoint:** `GET /api/v1/reports/{architecture_name}/summary`

**Description:** Get quick summary without downloading files.

**Response (200 OK):**
```json
{
  "architecture": "web_app",
  "has_ground_truth": true,
  "markdown_reports": [
    "01_executive_summary.md",
    "02_technical_report.md",
    "03_action_plan.md",
    "08_improvement_summary.md",
    "README.md"
  ],
  "json_files": [
    "ground_truth.json",
    "04_architect_critique.json",
    "05_tester_critique.json",
    "06_red_team_critique.json",
    "07_orchestrator_report.json"
  ],
  "other_files": [
    "before.mmd",
    "after.mmd",
    "08a_quick_wins.mmd",
    "08b_recommended_target.mmd",
    "08c_maximum_security.mmd"
  ],
  "total_files": 16
}
```

---

### 7. Download ZIP Archive

**Endpoint:** `GET /api/v1/reports/{architecture_name}/download`

**Description:** Download report files as a ZIP archive. Two pack options control which files are included.

**Query Parameters:**
- `pack` (optional, default `full`): `stakeholder` or `full`

**Pack contents:**

| Pack | Files included |
|------|---------------|
| `stakeholder` | `01_executive_summary.md`, `03_action_plan.md`, `08_improvement_summary.md`, `before.mmd`, `after.mmd` |
| `full` | All files except `ground_truth.json`, `07_moe_orchestrator.json`, `07_orchestrator_report.json`, `README.md` |

**Example:**
```bash
# Stakeholder pack
curl -H "TM-API-KEY: your-key" \
  "http://localhost:8000/api/v1/reports/web_app/download?pack=stakeholder" \
  -o web_app_stakeholder.zip

# Full pack
curl -H "TM-API-KEY: your-key" \
  "http://localhost:8000/api/v1/reports/web_app/download?pack=full" \
  -o web_app_full.zip
```

**Response:**
- **200 OK:** ZIP stream
- **Content-Type:** `application/zip`
- **Content-Disposition:** `attachment; filename="web_app_stakeholder.zip"`

---

## Reference Data APIs

### 8. Get MITRE Technique Names

**Endpoint:** `GET /api/v1/techniques`

**Description:** Resolve technique IDs to human-readable names.

**Query Parameters:**
- `technique_ids` (required): Comma-separated technique IDs (max 100)

**Example Request:**
```http
GET /api/v1/techniques?technique_ids=T1566,T1078,T1190,T1110,T1213
TM-API-KEY: your-key
```

**Response (200 OK):**
```json
{
  "techniques": {
    "T1566": "Phishing",
    "T1078": "Valid Accounts",
    "T1190": "Exploit Public-Facing Application",
    "T1110": "Brute Force",
    "T1213": "Data from Information Repositories"
  }
}
```

**Use Case:** Display technique names in UI without hardcoding or maintaining local cache.

---

### 9. Get MITRE Mitigation Names

**Endpoint:** `GET /api/v1/mitigations`

**Description:** Resolve mitigation IDs to human-readable names.

**Query Parameters:**
- `mitigation_ids` (required): Comma-separated mitigation IDs (max 100)

**Example Request:**
```http
GET /api/v1/mitigations?mitigation_ids=M1042,M1026,M1037
TM-API-KEY: your-key
```

**Response (200 OK):**
```json
{
  "mitigations": {
    "M1042": "Disable or Remove Feature or Program",
    "M1026": "Privileged Account Management",
    "M1037": "Filter Network Traffic"
  }
}
```

---

### 10. Get Technique → Mitigation Mappings

**Endpoint:** `GET /api/v1/technique-mitigations`

**Description:** Return which MITRE mitigation IDs apply to each given technique. Used to show mitigations inline per technique in the UI.

**Query Parameters:**
- `technique_ids` (required): Comma-separated technique IDs (max 50)

**Example Request:**
```http
GET /api/v1/technique-mitigations?technique_ids=T1566,T1078
TM-API-KEY: your-key
```

**Response (200 OK):**
```json
{
  "mappings": {
    "T1566": ["M1047", "M1031", "M1054", "M1021", "M1049", "M1017"],
    "T1078": ["M1027", "M1018", "M1026", "M1032", "M1013", "M1017", "M1015", "M1036"]
  }
}
```

**Use Case:** Pair with `/mitigations` to display `M1042 · Disable or Remove Feature or Program` alongside each technique in attack path and control views.

---

### 11. Health Check

**Endpoint:** `GET /api/v1/health`

**Description:** Check API health status.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.3.0",
  "timestamp": "2026-05-23T10:30:00Z",
  "services": {
    "deterministic_engine": "operational",
    "service_layer": "operational",
    "mitre_cache": "ready"
  }
}
```

**Authentication:** Not required

---

## Error Handling

All errors follow RFC 7807 (Problem Details for HTTP APIs) format:

**Error Response Structure:**
```json
{
  "type": "https://api.threatassessor.example.com/errors/bad-request",
  "title": "Invalid file format",
  "status": 400,
  "detail": "File must have .mmd extension, got: .txt",
  "instance": "/api/v1/analyze",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Common HTTP Status Codes:**

| Status | Meaning | Example |
|--------|---------|---------|
| 200 | Success | Analysis completed |
| 400 | Bad Request | Invalid file format, missing parameters |
| 401 | Unauthorized | Missing or invalid API key |
| 404 | Not Found | Architecture or file not found |
| 413 | Payload Too Large | File exceeds 10MB limit |
| 422 | Unprocessable Entity | Invalid Mermaid syntax |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Analysis engine failure |
| 503 | Service Unavailable | MITRE cache not loaded |

---

## Rate Limiting

**Limits:**
- **10 requests/minute** for `/analyze` and `/analyze-stream`
- **60 requests/minute** for `/reports/*` endpoints
- **Unlimited** for `/health`

**Headers (Included in Response):**
```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1705834800
Retry-After: 43
```

**Rate Limit Exceeded (429):**
```json
{
  "type": "https://api.threatassessor.example.com/errors/rate-limit",
  "title": "Rate limit exceeded",
  "status": 429,
  "detail": "You have exceeded the rate limit of 10 requests per minute",
  "instance": "/api/v1/analyze",
  "retry_after": 43
}
```

---

## Webhooks (Future)

**Status:** 🚧 **Planned for v1.4**

**Purpose:** Notify downstream apps when analysis completes (for long-running analyses).

**Planned Endpoint:** `POST /api/v1/webhooks`

**Webhook Payload (on analysis complete):**
```json
{
  "event": "analysis.completed",
  "timestamp": "2026-05-23T10:30:00Z",
  "architecture_name": "web_app",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "analysis_url": "/api/v1/reports/web_app",
  "report_paths": {
    "ground_truth": "report/web_app/ground_truth.json",
    "executive": "report/web_app/01_executive_summary.md"
  }
}
```

---

## Complete Integration Example

**Scenario:** Downstream app analyzes architecture and displays results

```python
import requests
import json
import time

class ThreatAssessorClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {'TM-API-KEY': api_key}
    
    def analyze_architecture(self, file_path):
        """Submit architecture for analysis."""
        with open(file_path, 'rb') as f:
            files = {'architecture_file': f}
            response = requests.post(
                f"{self.base_url}/api/v1/analyze",
                headers=self.headers,
                files=files,
                data={'include_validation': 'true'},
                timeout=120
            )
        response.raise_for_status()
        return response.json()
    
    def get_report_files(self, arch_name):
        """Get list of all report files."""
        response = requests.get(
            f"{self.base_url}/api/v1/reports/{arch_name}",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def download_report(self, arch_name, filename):
        """Download specific report file."""
        response = requests.get(
            f"{self.base_url}/api/v1/reports/{arch_name}/files/{filename}",
            headers=self.headers
        )
        response.raise_for_status()
        
        if filename.endswith('.json'):
            return response.json()
        else:
            return response.text
    
    def get_technique_names(self, technique_ids):
        """Resolve technique IDs to names."""
        ids_str = ','.join(technique_ids)
        response = requests.get(
            f"{self.base_url}/api/v1/techniques",
            headers=self.headers,
            params={'technique_ids': ids_str}
        )
        response.raise_for_status()
        return response.json()['techniques']


# Usage
client = ThreatAssessorClient(
    base_url='http://localhost:8000',
    api_key='your-api-key-here'
)

# Analyze architecture
print("Analyzing architecture...")
result = client.analyze_architecture('my_architecture.mmd')
arch_name = result['data']['architecture_name']
print(f"Analysis complete: {arch_name}")

# Get all reports
print(f"\nFetching reports for {arch_name}...")
reports = client.get_report_files(arch_name)
print(f"Found {reports['count']} report files")

# Download ground truth
print("\nDownloading ground truth...")
ground_truth = client.download_report(arch_name, 'ground_truth.json')
attack_paths = ground_truth['expected_attack_paths']
print(f"Found {len(attack_paths)} attack paths")

# Download before/after diagrams
print("\nDownloading diagrams...")
before_mmd = client.download_report(arch_name, 'before.mmd')
after_mmd = client.download_report(arch_name, 'after.mmd')
print(f"Before diagram: {len(before_mmd)} chars")
print(f"After diagram: {len(after_mmd)} chars")

# Get technique names
techniques = [t for path in attack_paths for t in path['techniques']]
unique_techniques = list(set(techniques))
technique_names = client.get_technique_names(unique_techniques)
print(f"\nTechniques used: {len(unique_techniques)}")
for tid, name in technique_names.items():
    print(f"  {tid}: {name}")
```

---

## Summary

**Available Now:**
- ✅ Analysis APIs (streaming and non-streaming)
- ✅ Report listing and download
- ✅ MITRE technique lookup
- ✅ Health check

**Coming Soon:**
- 🚧 ZIP download endpoint
- 🚧 Webhooks for async notifications
- 🚧 Batch analysis endpoint
- 🚧 Analysis status polling (for long-running jobs)

**Contact:** For API support or feature requests, see [GitHub Issues](https://github.com/yourusername/threatassessor/issues)
