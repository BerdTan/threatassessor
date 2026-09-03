"""
MCPClient — typed Python wrapper for all 17 ThreatAssessor MCP tools.

Calls the ThreatAssessor REST API directly (same endpoints as the MCP server
job_client.py), so no running MCP subprocess is required. Suitable for use
in any Python agent, CI script, or Lambda function.

Usage:
    from mcp_connector import MCPClient

    client = MCPClient(base_url="http://localhost:8000", api_key="your-key")

    # Screen a diagram before analysis
    result = client.governance_check("graph LR\\n  A --> B")
    print(result["fired_rules"])  # ["DETECT-017"] if URL found

    # Run a full assessment
    bundle = client.export_assessment("my_arch")
    if bundle["gate"]["result"] == "BLOCK":
        raise SystemExit(f"Gate blocked: {bundle['gate']['blocking_signals']}")
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Union

import requests

from mcp_connector.models import TAExportBundle, ComponentContext


class MCPClient:
    """Typed REST client for all 13 ThreatAssessor MCP tools.

    Args:
        base_url: Base URL of the ThreatAssessor API (default: TM_API_BASE_URL env var
                  or http://localhost:8000).
        api_key:  API key (default: TM_API_KEY or API_KEY env var).
        timeout:  Request timeout in seconds (default: 60).
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: int = 60,
    ) -> None:
        self._base = (base_url or os.environ.get("TM_API_BASE_URL", "http://localhost:8000")).rstrip("/")
        self._key = api_key or os.environ.get("TM_API_KEY", "") or os.environ.get("API_KEY", "")
        self._timeout = timeout

    # ── private ──────────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._key:
            h["TM-API-KEY"] = self._key
        return h

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        r = requests.get(f"{self._base}{path}", headers=self._headers(),
                         params=params, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: Optional[Dict] = None) -> Any:
        r = requests.post(f"{self._base}{path}", headers=self._headers(),
                          json=body or {}, timeout=self._timeout)
        # governance/check returns 400 with embedded signals on CRITICAL block — not an error
        if r.status_code == 400 and path == "/api/v1/governance/check":
            return r.json().get("detail", r.json())
        r.raise_for_status()
        return r.json()

    # ── Tool 1: analyze_architecture ─────────────────────────────────────────

    def analyze_architecture(self, mmd_content: str, ssp_profile: str = "low_risk_cloud") -> Dict:
        """Submit a Mermaid diagram and return the full threat model (~30s).

        Args:
            mmd_content: Raw Mermaid diagram string (graph LR / flowchart syntax).
            ssp_profile: Risk profile — 'low_risk_cloud', 'high_risk_gov', etc.

        Returns:
            ground_truth dict with attack_paths, techniques, control_recommendations.
        """
        return self._post("/api/v1/analyze", {
            "mmd_content": mmd_content,
            "ssp_profile": ssp_profile,
        })

    # ── Tool 2+3: expert review async workflow ────────────────────────────────

    def run_expert_review(self, arch_name: str, critic_mode: str = "partial_parallel") -> Dict:
        """Queue a full MoE expert review. Returns job_id — poll with get_job_status().

        Args:
            arch_name:   Architecture that has already been analysed.
            critic_mode: 'partial_parallel' (default), 'sequential', 'parallel', 'auto'.
        """
        return self._post("/api/v1/jobs/expert-review", {
            "arch_name": arch_name,
            "critic_mode": critic_mode,
        })

    def get_job_status(self, job_id: str, wait_for_completion: bool = False) -> Dict:
        """Poll an expert review job. Returns status, progress 0-100, and result when done.

        Args:
            job_id:              UUID from run_expert_review().
            wait_for_completion: Block until status == 'completed' or 'failed'.
        """
        import time
        while True:
            result = self._get(f"/api/v1/jobs/{job_id}/status")
            if not wait_for_completion or result.get("status") in ("completed", "failed", "blocked"):
                return result
            time.sleep(3)

    # ── Tool 4: get_threat_briefing ───────────────────────────────────────────

    def get_threat_briefing(self, arch_name: str, fmt: str = "md") -> str:
        """Get a CISO-ready threat briefing for a known architecture.

        Args:
            arch_name: Architecture directory name.
            fmt:       'md' (default, markdown string) or 'json'.
        """
        url = f"{self._base}/api/v1/reports/{arch_name}/briefing"
        r = requests.get(url, headers=self._headers(), params={"fmt": fmt},
                         timeout=self._timeout)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        return r.json() if "json" in ct else r.text

    # ── Tool 5: get_ciso_brief ────────────────────────────────────────────────

    def get_ciso_brief(self, arch_name: str) -> Dict:
        """Generate a full CISO brief with investment tiers and multi-critic findings."""
        return self._post(f"/api/v1/reports/{arch_name}/generate-ciso-brief")

    # ── Tool 6: get_governance_signals ───────────────────────────────────────

    def get_governance_signals(self, arch_name: str) -> Dict:
        """Get AIVSS composite score and per-dimension governance signals."""
        return self._get("/api/v1/insights", params={"archs": arch_name})

    # ── Tool 7: get_detect_trends ─────────────────────────────────────────────

    def get_detect_trends(self, arch_name: str) -> Dict:
        """Get SOC DETECT rule firing trends across history runs.

        Returns: {architecture, total_runs, trends: [{rule_id, trend, fire_rate}]}
        Trend values: new | rising | stable | falling | cleared | never
        """
        return self._get(f"/api/v1/detect-trend/{arch_name}")

    # ── Tool 8: get_tatb_scores ───────────────────────────────────────────────

    def get_tatb_scores(self, arch_name: str = "") -> Dict:
        """Get TATB benchmark scores. Pass arch_name for single arch, empty for corpus.

        Returns: {architectures: [{name, threat, ttp, risk, plan, overall}], avg: {...}}
        """
        result = self._get("/api/v1/tatb-corpus")
        if arch_name:
            archs = result.get("architectures", [])
            row = next((a for a in archs if a.get("name") == arch_name), None)
            return row or {}
        return result

    # ── Tool 9: list_architectures ────────────────────────────────────────────

    def list_architectures(self) -> List[Dict]:
        """List all analysed architectures with metadata."""
        result = self._get("/api/v1/insights/all")
        return result if isinstance(result, list) else result.get("architectures", [])

    # ── Tool 10: lookup_mitre_technique ──────────────────────────────────────

    def lookup_mitre_technique(self, technique_ids: str) -> Dict:
        """Look up MITRE ATT&CK technique details and recommended mitigations.

        Args:
            technique_ids: Comma-separated ATT&CK IDs, e.g. 'T1190,T1078,T1059'.
        """
        techniques  = self._get("/api/v1/techniques",           params={"technique_ids": technique_ids})
        mitigations = self._get("/api/v1/technique-mitigations", params={"technique_ids": technique_ids})
        return {"techniques": techniques, "mitigations": mitigations}

    # ── Tool 11: get_mcp_access_signals ──────────────────────────────────────

    def get_mcp_access_signals(self) -> Dict:
        """Get live MCP session access pattern signals (feeds DETECT-020/021/022)."""
        return self._get("/api/v1/mcp/access-signals")

    # ── Tool 12: export_assessment ────────────────────────────────────────────

    def export_assessment(
        self,
        arch_name: str,
        save: bool = False,
        raw: bool = False,
    ) -> Union[TAExportBundle, Dict]:
        """Export unified TA assessment bundle (schema ta-export/1.0).

        Bundle sections: gate (PASS|BLOCK), assessment, tatb, governance,
        moe_consensus, detect_findings (OCSF 2004), security_findings (OCSF 2001),
        otm (OTM 0.2.0 — importable by Startlift/IriusRisk).

        Args:
            arch_name: Architecture directory name.
            save:      If True, also writes ta_export.json to the report directory.

        CI/CD gate example::

            bundle = client.export_assessment("my_arch")
            if bundle.gate.result == "BLOCK":
                raise SystemExit(1)

            # Raw dict (legacy):
            bundle = client.export_assessment("my_arch", raw=True)
            if bundle["gate"]["result"] == "BLOCK":
                raise SystemExit(1)

        Args:
            arch_name: Architecture directory name.
            save:      If True, also writes ta_export.json to the report directory.
            raw:       If True, return raw dict instead of TAExportBundle.
        """
        data = self._get(f"/api/v1/reports/{arch_name}/export",
                         params={"save": str(save).lower()})
        if raw:
            return data
        return TAExportBundle.from_dict(data)

    # ── Tool 13: governance_check ─────────────────────────────────────────────

    def governance_check(self, mmd_content: str, arch_name: str = "mcp_input") -> Dict:
        """Screen raw MMD content for injection, traversal, URLs, and evasion (~50ms, no LLM).

        Returns signals + fired DETECT rules immediately. On CRITICAL input
        (e.g. LLM control tokens), blocked=True is set in the response.

        Pre-submission screening example::

            result = client.governance_check(mmd_content)
            if result.get("blocked"):
                raise ValueError(f"Input blocked: {result['fired_rules']}")

        Args:
            mmd_content: Raw Mermaid diagram string to screen.
            arch_name:   Optional label for this check.

        Returns:
            {"arch_name", "signals", "fired_rules", "findings", "blocked"}
        """
        return self._post("/api/v1/governance/check", {
            "mmd_content": mmd_content,
            "arch_name": arch_name,
        })

    # ── Tool 17: run_taco_agent ───────────────────────────────────────────────

    def run_taco_agent(
        self,
        query: str,
        arch_name: str = "",
        force_critic: bool = False,
    ) -> Dict:
        """Run the TACO routing chain and return the full HopChain.

        Args:
            query:        Natural-language threat question.
            arch_name:    Known corpus architecture name. Empty = brain-only mode.
            force_critic: Append TACOminiCritic hop (requires critic_enabled=true).

        Returns:
            HopChain dict with hops, final_confidence, routing flags.
        """
        return self._post("/api/v1/taco/run-sync", {
            "query": query,
            "arch_name": arch_name or None,
            "force_critic": force_critic,
        })

    # ── Tool 14: query_ta_brain ───────────────────────────────────────────────

    def query_ta_brain(
        self,
        mode: str = "infer",
        arch_name: str = "",
        topology_signature: str = "",
        arch_type: str = "",
        arch_type_filter: str = "",
    ) -> Dict:
        """Query TA Brain patterns (infer | gaps | patterns).

        Args:
            mode:               "infer" | "gaps" | "patterns"
            arch_name:          Corpus arch name — resolves topology_signature + arch_type.
            topology_signature: Direct 16-char topology hash (for new archs not in corpus).
            arch_type:          Architecture type hint used with topology_signature.
            arch_type_filter:   Filter patterns by arch_type (patterns mode only).

        Returns:
            In infer mode: had_match, confidence, techniques, missing_controls,
            detect_rules, aivss_floor, evidence trace.
        """
        return self._post("/api/v1/brain/query", {
            "mode": mode,
            "arch_name": arch_name,
            "topology_signature": topology_signature,
            "arch_type": arch_type,
            "arch_type_filter": arch_type_filter,
        })

    # ── Tool 15: record_brain_feedback ───────────────────────────────────────

    def record_brain_feedback(
        self,
        feedback: str,
        arch_name: str = "",
        topology_signature: str = "",
        arch_type: str = "",
        mode: str = "infer",
        reference_ts: str = "",
    ) -> Dict:
        """Record confirmed/wrong/partial feedback on a Brain prediction.

        Args:
            feedback:           "confirmed" | "wrong" | "partial"
            arch_name:          Corpus arch name (resolves topology_sig + arch_type).
            topology_signature: Direct topology hash (if arch_name not provided).
            arch_type:          Architecture type (used with topology_signature).
            mode:               Query mode the feedback applies to (default "infer").
            reference_ts:       ISO timestamp of the original query (optional link).

        Returns:
            {"recorded", "cache_updated", "feedback", "topology_sig", "ts"}
        """
        return self._post("/api/v1/brain/feedback", {
            "feedback": feedback,
            "arch_name": arch_name,
            "topology_signature": topology_signature,
            "arch_type": arch_type,
            "mode": mode,
            "reference_ts": reference_ts,
        })

    # ── Tool 16: generate_synthetic_architectures ─────────────────────────────

    def generate_synthetic_architectures(
        self,
        gap_ids: str = "",
        max_per_run: int = 3,
    ) -> Dict:
        """Generate synthetic Mermaid diagrams from TA Brain meta-layer gaps.

        Args:
            gap_ids:     Comma-separated gap IDs (e.g. "GAP-001,GAP-003").
                         Leave empty to auto-select by priority.
            max_per_run: Maximum diagrams to generate (default: 3).

        Returns:
            {"staged": [...], "queue_summary": {...}}
        """
        parsed_ids = [g.strip() for g in gap_ids.split(",") if g.strip()] if gap_ids else []
        return self._post("/api/v1/brain/generate-mmds", {
            "gap_ids": parsed_ids,
            "max_per_run": max_per_run,
        })

    # ── Enrichment: VAPT / SAST integration ──────────────────────────────────

    def enrich_finding(
        self,
        arch_name: str,
        component: str,
        finding_type: str = "other",
        finding_id: str = "",
        severity: str = "",
        description: str = "",
        include_attack_paths: bool = True,
        include_controls: bool = True,
        raw: bool = False,
    ) -> Union[ComponentContext, Dict]:
        """Return TA threat context for a specific component from an existing analysis.

        Fast (<50ms), read-only — no re-analysis. Requires analysis to have been run
        for arch_name first (raises HTTPError 404 otherwise).

        Args:
            arch_name:            Architecture directory name.
            component:            Component label from your SAST/VAPT tool.
            finding_type:         "cve" | "technique" | "control_gap" | "vulnerability" | "other"
            finding_id:           Finding identifier (CVE-2024-XXXX, T1190, etc.)
            severity:             "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
            description:          Optional human-readable finding description.
            include_attack_paths: Include attack paths touching this component.
            include_controls:     Include recommended controls.
            raw:                  If True, return raw dict instead of ComponentContext.

        Returns:
            ComponentContext with matched nodes, attack paths, techniques, and controls.
            Call .as_markdown() for a human-readable annotation block.

        Example::

            ctx = client.enrich_finding("my_arch", "API Gateway",
                                        finding_type="technique", finding_id="T1190")
            print(ctx.as_markdown())
        """
        data = self._post("/api/v1/enrich", {
            "arch_name": arch_name,
            "component": component,
            "finding": {
                "type": finding_type,
                "id": finding_id or component,
                "severity": severity or None,
                "description": description or None,
            },
            "include_attack_paths": include_attack_paths,
            "include_controls": include_controls,
        })
        if raw:
            return data
        from mcp_connector.models import AttackPath
        return ComponentContext(
            component_label=data.get("matched_nodes", [{}])[0].get("node_label", component)
                            if data.get("matched_nodes") else component,
            attack_paths=[
                AttackPath(
                    id=ap.get("id"),
                    entry=ap.get("entry", ""),
                    target=ap.get("target", ""),
                    criticality=ap.get("criticality"),
                    techniques=ap.get("techniques", []),
                )
                for ap in data.get("attack_paths_touching", [])
            ],
            techniques=data.get("techniques_mapped", []),
            risk_level=data.get("ta_export_gate") or "UNKNOWN",
            controls_recommended=data.get("controls_recommended", []),
            match_confidence=data.get("matched_nodes", [{}])[0].get("match_confidence", 0.0)
                             if data.get("matched_nodes") else 0.0,
        )
