"""
Governance layer smoke test — single run covering all 5 dimensions.

Use this when you need a fast confidence check that the governance layer
is functional before a deploy, after a dependency upgrade, or after editing
harness_governance.py.

Run:  pytest tests/test_governance_smoke.py -v

Expected: 1 test, ~1 second, no LLM calls, no network.

Fixtures (tests/data/governance/):
  inputs/all_dims.mmd                   — D1 injection + D5 regions + D5 ZDR edge
  artifacts/all_dims_ground_truth.json  — D3 NRIC + email + credential keyword
  moe_results/all_dims_moe.json         — D2 FALLBACK + high divergence + confidence swing
  D4 (wrap_capability + ToolError)      — programmatic: one failing tool call before check_artifact
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chatbot.modules.harness_governance import (
    InhouseGovernanceAdapter,
    compute_manipulation_signals,
    save_governance_signals,
)

_FIXTURES = Path(__file__).parent / "data" / "governance"


def _read(subdir: str, name: str) -> str:
    return (_FIXTURES / subdir / name).read_text()


def _load(subdir: str, name: str) -> dict:
    return json.loads(_read(subdir, name))


def test_governance_all_dimensions_smoke(tmp_path):
    """
    One test — one adapter instance — all 5 dimensions exercised in sequence.

    Each dimension assertion includes a failure message that names the exact
    detection that regressed, so failures are self-diagnosing.
    """
    adapter = InhouseGovernanceAdapter()

    # ── D4 setup: log one successful tool call + one ToolError before checks ──
    def good_tool(x: int) -> int:
        return x * 2

    def bad_tool():
        raise RuntimeError("simulated tool failure")

    adapter.wrap_capability(good_tool, "tool", "architect")(x=3)
    with pytest.raises(RuntimeError):
        adapter.wrap_capability(bad_tool, "tool", "red_team")()

    # ── D1 + D5 input check ───────────────────────────────────────────────────
    mmd_content = _read("inputs", "all_dims.mmd")
    input_sig = adapter.check_input(mmd_content, "all_dims.mmd")

    # D1 — Exploitation: injection phrase in WAF node label
    assert len(input_sig.exploitation["injection_patterns"]) > 0, (
        "D1 FAIL: injection phrase in WAF node not detected — _RE_INJECTION may have regressed"
    )
    assert input_sig.exploitation["severity"] in ("MEDIUM", "HIGH"), (
        f"D1 FAIL: expected MEDIUM or HIGH severity, got {input_sig.exploitation['severity']!r}"
    )

    # D5 — Sovereignty: ap-southeast-1 + us-east-1 regions
    assert len(input_sig.sovereignty["inferred_regions"]) >= 2, (
        f"D5 FAIL: expected ≥2 cloud regions, got {input_sig.sovereignty['inferred_regions']!r} — "
        "_RE_REGION may have regressed"
    )
    assert input_sig.sovereignty["flagged"] is True, (
        "D5 FAIL: sovereignty.flagged should be True when regions are present"
    )

    # D5 — ZDR: AI Service (ML Model) → SendGrid edge
    assert len(input_sig.sovereignty["zdr_signals"]) > 0, (
        "D5 FAIL: ML Model → SendGrid edge not detected as ZDR signal — "
        "_RE_LLM_NODE or _RE_EXTERNAL_SERVICE or edge-stripping logic may have regressed"
    )

    # ── D3 + D4 artifact check ────────────────────────────────────────────────
    ground_truth = _load("artifacts", "all_dims_ground_truth.json")
    artifact_sig = adapter.check_artifact(ground_truth)

    # D3 — Leakage: NRIC S9876543C
    assert any("NRIC" in p for p in artifact_sig.leakage["pii_indicators"]), (
        "D3 FAIL: NRIC not detected in ground truth metadata — _RE_NRIC may have regressed"
    )

    # D3 — Leakage: email lead@example.com
    assert any("email" in p for p in artifact_sig.leakage["pii_indicators"]), (
        "D3 FAIL: email not detected in ground truth metadata — _RE_EMAIL may have regressed"
    )

    # D3 — Leakage: credential keyword db_pass
    assert len(artifact_sig.leakage["sensitive_keywords"]) > 0, (
        "D3 FAIL: credential keyword 'db_pass' not detected — _RE_CRED may have regressed"
    )
    assert artifact_sig.leakage["flagged"] is True, (
        "D3 FAIL: leakage.flagged should be True when PII + credential detected"
    )
    assert artifact_sig.leakage["severity"] == "CRITICAL", (
        f"D3 FAIL: expected CRITICAL severity (NRIC + credential present), "
        f"got {artifact_sig.leakage['severity']!r}"
    )

    # D4 — Cross-Identity: tool call logged, ToolError recorded
    assert artifact_sig.identity["critic_tool_calls"].get("architect") == 1, (
        "D4 FAIL: architect tool call not reflected in identity.critic_tool_calls — "
        "wrap_capability logging may have regressed"
    )
    assert len(artifact_sig.identity["tool_errors"]) == 1, (
        "D4 FAIL: ToolError from bad_tool not recorded in identity.tool_errors"
    )
    assert artifact_sig.identity["tool_errors"][0]["critic_name"] == "red_team", (
        "D4 FAIL: ToolError critic_name should be 'red_team'"
    )

    # ── D2 manipulation check ─────────────────────────────────────────────────
    moe_data = _load("moe_results", "all_dims_moe.json")
    manip = compute_manipulation_signals(moe_data)

    # D2 — FALLBACK synthesis
    assert manip["fallback_triggered"] is True, (
        "D2 FAIL: FALLBACK synthesis not detected — compute_manipulation_signals may have regressed"
    )

    # D2 — High divergence: architect=92, red_team=38 → divergence=54
    assert manip["critic_divergence_score"] > 40, (
        f"D2 FAIL: expected divergence >40, got {manip['critic_divergence_score']} — "
        "score extraction from expert_validations may have regressed"
    )

    # D2 — Confidence swing: final=71.0, base=89.0 → swing=18.0
    assert manip["confidence_swing"] == pytest.approx(18.0, abs=0.1), (
        f"D2 FAIL: expected confidence swing 18.0, got {manip['confidence_swing']}"
    )

    assert manip["severity"] == "HIGH", (
        f"D2 FAIL: expected HIGH severity (fallback + div>40), got {manip['severity']!r}"
    )

    # ── Merge + overall risk ──────────────────────────────────────────────────
    merged = input_sig.merge(artifact_sig)
    merged.architecture_name = "all_dims_smoke"

    assert merged.overall_risk_level == "CRITICAL", (
        f"Merge FAIL: overall_risk_level should be CRITICAL when D1+D3 are critical, "
        f"got {merged.overall_risk_level!r}"
    )
    assert set(["external_boundary", "deterministic_layer", "llm_layer"]).issubset(
        set(merged.kill_chain_coverage)
    ), f"Merge FAIL: kill_chain_coverage incomplete: {merged.kill_chain_coverage}"

    # ── Persist and verify ────────────────────────────────────────────────────
    save_governance_signals(merged, str(tmp_path))
    written = json.loads((tmp_path / "governance_signals.json").read_text())

    assert written["architecture_name"] == "all_dims_smoke"
    assert written["overall_risk_level"] == "CRITICAL"
    assert "exploitation" in written
    assert "leakage" in written
    assert "sovereignty" in written
    assert "identity" in written
    assert written["leakage"]["flagged"] is True
    assert written["sovereignty"]["flagged"] is True
