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


def export_assessment(arch_name: str, save: bool = False) -> Dict:
    """GET /api/v1/reports/{arch}/export — unified TA bundle (ta-export/1.0)."""
    return _get(f"/api/v1/reports/{arch_name}/export", params={"save": str(save).lower()})


def governance_check(mmd_content: str, arch_name: str = "mcp_sim") -> Dict:
    """POST /api/v1/governance/check — fast governance scan, no LLM, returns fired DETECT rules."""
    return _post("/api/v1/governance/check", {"mmd_content": mmd_content, "arch_name": arch_name})


def query_ta_brain(
    mode: str = "infer",
    arch_name: str = "",
    topology_signature: str = "",
    arch_type: str = "",
    arch_type_filter: str = "",
) -> Dict:
    """POST /api/v1/brain/query — query TA Brain patterns (infer | gaps | patterns)."""
    return _post("/api/v1/brain/query", {
        "mode": mode,
        "arch_name": arch_name,
        "topology_signature": topology_signature,
        "arch_type": arch_type,
        "arch_type_filter": arch_type_filter,
    })


def record_brain_feedback(
    feedback: str,
    arch_name: str = "",
    topology_signature: str = "",
    arch_type: str = "",
    mode: str = "infer",
    reference_ts: str = "",
) -> Dict:
    """POST /api/v1/brain/feedback — record confirmed/wrong/partial on a brain prediction."""
    return _post("/api/v1/brain/feedback", {
        "feedback": feedback,
        "arch_name": arch_name,
        "topology_signature": topology_signature,
        "arch_type": arch_type,
        "mode": mode,
        "reference_ts": reference_ts,
    })


def generate_synthetic_architectures(gap_ids: list = None, max_per_run: int = 3) -> Dict:
    """POST /api/v1/brain/generate-mmds — generate synthetic MMDs from meta-layer gaps."""
    return _post("/api/v1/brain/generate-mmds", {
        "gap_ids": gap_ids or [],
        "max_per_run": max_per_run,
    }, timeout=300)
