"""
Thin HTTP client for the ThreatAssessor REST API.

All MCP tool implementations call this module — never call requests directly
in server.py. This makes it easy to swap the transport (e.g. async httpx)
without touching tool logic.
"""

import os
import json
import time
import requests
from typing import Any, Dict, Optional

_DEFAULT_BASE_URL = "http://localhost:8000"
_DEFAULT_TIMEOUT  = 60   # seconds for sync calls; expert review uses poll loop
_POLL_INTERVAL    = 3    # seconds between job status polls
_POLL_MAX_WAIT    = 900  # 15 minutes max before giving up on a job


def _base_url() -> str:
    return os.environ.get("TM_API_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")


def _headers() -> Dict[str, str]:
    key = os.environ.get("TM_API_KEY", "") or os.environ.get("API_KEY", "")
    h = {"Content-Type": "application/json"}
    if key:
        h["TM-API-KEY"] = key
    return h


def _get(path: str, params: Optional[Dict] = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
    url = f"{_base_url()}{path}"
    r = requests.get(url, headers=_headers(), params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: Optional[Dict] = None, timeout: int = _DEFAULT_TIMEOUT) -> Any:
    url = f"{_base_url()}{path}"
    r = requests.post(url, headers=_headers(), json=body or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Tool-level API calls
# ---------------------------------------------------------------------------

def analyze_architecture(mmd_content: str, ssp_profile: str = "low_risk_cloud") -> Dict:
    """POST /api/v1/analyze — synchronous full analysis (~30s)."""
    return _post("/api/v1/analyze", {
        "mmd_content": mmd_content,
        "ssp_profile": ssp_profile,
    }, timeout=120)


def submit_expert_review(arch_name: str, critic_mode: str = "partial_parallel") -> Dict:
    """POST /api/v1/jobs/expert-review — returns {job_id, status}."""
    return _post("/api/v1/jobs/expert-review", {
        "arch_name":   arch_name,
        "critic_mode": critic_mode,
    })


def get_job_status(job_id: str) -> Dict:
    """GET /api/v1/jobs/{job_id}/status."""
    return _get(f"/api/v1/jobs/{job_id}/status")


def await_job(job_id: str, poll_interval: int = _POLL_INTERVAL) -> Dict:
    """Poll until the job completes or times out. Returns final status payload."""
    deadline = time.time() + _POLL_MAX_WAIT
    while time.time() < deadline:
        status = get_job_status(job_id)
        if status["status"] in ("completed", "failed", "blocked"):
            return status
        time.sleep(poll_interval)
    return {"job_id": job_id, "status": "timeout", "error": "Job did not complete within 15 minutes"}


def get_threat_briefing(arch_name: str, fmt: str = "md") -> Any:
    """GET /api/v1/reports/{arch}/briefing. Returns str for md, dict for json."""
    url = f"{_base_url()}/api/v1/reports/{arch_name}/briefing"
    r = requests.get(url, headers=_headers(), params={"fmt": fmt}, timeout=_DEFAULT_TIMEOUT)
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    if "json" in ct:
        return r.json()
    return r.text


def get_ciso_brief(arch_name: str) -> Dict:
    """POST /api/v1/reports/{arch}/generate-ciso-brief."""
    return _post(f"/api/v1/reports/{arch_name}/generate-ciso-brief")


def get_governance_signals(arch_name: str) -> Dict:
    """GET /api/v1/insights?archs={arch_name}."""
    return _get("/api/v1/insights", params={"archs": arch_name})


def get_detect_trends(arch_name: str) -> Dict:
    """GET /api/v1/detect-trend/{arch_name}."""
    return _get(f"/api/v1/detect-trend/{arch_name}")


def get_tatb_scores(arch_name: str = "") -> Dict:
    """GET /api/v1/tatb-corpus — optionally filter to one arch in the caller."""
    return _get("/api/v1/tatb-corpus")


def list_architectures() -> Dict:
    """GET /api/v1/insights/all."""
    return _get("/api/v1/insights/all")


def lookup_mitre_technique(technique_ids: str) -> Dict:
    """GET /api/v1/techniques + /api/v1/technique-mitigations for a comma-sep list."""
    techniques   = _get("/api/v1/techniques",            params={"technique_ids": technique_ids})
    mitigations  = _get("/api/v1/technique-mitigations", params={"technique_ids": technique_ids})
    return {"techniques": techniques, "mitigations": mitigations}
