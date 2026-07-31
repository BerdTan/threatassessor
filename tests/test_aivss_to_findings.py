"""
Tests for aivss-to-findings skill: AIVSS governance_signals → OCSF SecurityFinding export.

Covers:
  - classify(): all three branches (confirmed / suspicious / anomalous) and boundary values
  - process_signals(): OCSF field correctness, flow filtering, overall finding always present
  - OCSF schema validation: required fields, class_uid, status_id, severity_id mapping
  - CLI modes: single arch, --file --dry-run, missing governance_signals
  - Edge cases: zero composite, all flows zero, hard block overrides high composite

No LLM calls, no network, no file writes to report/.
Expected runtime: < 1 second.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# ---------------------------------------------------------------------------
# Import the skill script without requiring it to be a package
# ---------------------------------------------------------------------------

_SKILL_SCRIPT = (
    Path(__file__).parents[1]
    / ".claude/skills/aivss-to-findings/scripts/aivss_to_findings.py"
)

spec = importlib.util.spec_from_file_location("aivss_to_findings", _SKILL_SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

classify         = _mod.classify
process_signals  = _mod.process_signals
CONFIRMED_MIN    = _mod.CONFIRMED_MIN
SUSPICIOUS_MIN   = _mod.SUSPICIOUS_MIN


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _signals(
    overall_composite: float = 3.12,
    overall_severity: str = "LOW",
    internal_composite: float = 0.0,
    internal_severity: str = "LOW",
    inbound_composite: float = 0.0,
    outbound_composite: float = 0.0,
    manipulation_severity: str = "LOW",
    exploitation_severity: str = "LOW",
    leakage_detected: bool = False,
    confidence_swing: float = 0.0,
    per_threat: list | None = None,
) -> Dict[str, Any]:
    return {
        "manipulation": {
            "severity": manipulation_severity,
            "confidence_swing_detected": confidence_swing > 0,
            "confidence_swing": confidence_swing,
            "divergence_detected": False,
        },
        "exploitation": {
            "severity": exploitation_severity,
        },
        "leakage": {
            "detected": leakage_detected,
            "severity": "HIGH" if leakage_detected else "LOW",
        },
        "aivss": {
            "overall": {"composite": overall_composite, "severity": overall_severity},
            "inbound":  {"composite": inbound_composite,  "severity": "LOW", "coverage_pct": 0 if inbound_composite == 0 else 50},
            "internal": {"composite": internal_composite, "severity": internal_severity, "coverage_pct": 0 if internal_composite == 0 else 50},
            "outbound": {"composite": outbound_composite, "severity": "LOW", "coverage_pct": 0 if outbound_composite == 0 else 50},
            "per_threat": per_threat or [],
            "coverage_pct": 20,
        },
    }


def _critical_threat():
    return {"technique_id": "T1190", "technique_name": "Exploit Public-Facing App",
            "composite": 10.0, "severity": "CRITICAL", "top_metric": "DC"}


# ---------------------------------------------------------------------------
# classify() — confirmed branch
# ---------------------------------------------------------------------------

class TestClassifyConfirmed:
    def test_at_threshold(self):
        sig = _signals(overall_composite=CONFIRMED_MIN)
        assert classify(CONFIRMED_MIN, sig, sig["aivss"]) == "confirmed"

    def test_above_threshold(self):
        sig = _signals(overall_composite=9.5)
        assert classify(9.5, sig, sig["aivss"]) == "confirmed"

    def test_max_score(self):
        sig = _signals(overall_composite=10.0, overall_severity="CRITICAL")
        assert classify(10.0, sig, sig["aivss"]) == "confirmed"

    def test_hard_block_overrides_confirmed_score(self):
        """CRITICAL exploitation block must flip confirmed → anomalous."""
        sig = _signals(overall_composite=8.0, exploitation_severity="CRITICAL")
        assert classify(8.0, sig, sig["aivss"]) == "anomalous"

    def test_manipulation_critical_overrides_confirmed_score(self):
        sig = _signals(overall_composite=7.5, manipulation_severity="CRITICAL")
        assert classify(7.5, sig, sig["aivss"]) == "anomalous"


# ---------------------------------------------------------------------------
# classify() — suspicious branch
# ---------------------------------------------------------------------------

class TestClassifySuspicious:
    def test_composite_in_range(self):
        sig = _signals(overall_composite=5.0)
        assert classify(5.0, sig, sig["aivss"]) == "suspicious"

    def test_at_suspicious_min(self):
        sig = _signals(overall_composite=SUSPICIOUS_MIN)
        assert classify(SUSPICIOUS_MIN, sig, sig["aivss"]) == "suspicious"

    def test_just_below_confirmed(self):
        composite = CONFIRMED_MIN - 0.01
        sig = _signals(overall_composite=composite)
        assert classify(composite, sig, sig["aivss"]) == "suspicious"

    def test_low_composite_but_manipulation_medium(self):
        """Composite below suspicious_min, but soft signal elevates to suspicious."""
        sig = _signals(overall_composite=2.0, manipulation_severity="MEDIUM")
        assert classify(2.0, sig, sig["aivss"]) == "suspicious"

    def test_low_composite_but_manipulation_high(self):
        sig = _signals(overall_composite=1.0, manipulation_severity="HIGH")
        assert classify(1.0, sig, sig["aivss"]) == "suspicious"

    def test_low_composite_but_leakage_detected(self):
        sig = _signals(overall_composite=1.5, leakage_detected=True)
        assert classify(1.5, sig, sig["aivss"]) == "suspicious"

    def test_composite_4_no_soft_signals(self):
        sig = _signals(overall_composite=4.0)
        assert classify(4.0, sig, sig["aivss"]) == "suspicious"


# ---------------------------------------------------------------------------
# classify() — anomalous branch
# ---------------------------------------------------------------------------

class TestClassifyAnomalous:
    def test_low_composite_with_critical_per_threat(self):
        sig = _signals(overall_composite=2.0, per_threat=[_critical_threat()])
        assert classify(2.0, sig, sig["aivss"]) == "anomalous"

    def test_zero_composite_with_critical_threat(self):
        sig = _signals(overall_composite=0.0, per_threat=[_critical_threat()])
        assert classify(0.0, sig, sig["aivss"]) == "anomalous"

    def test_low_composite_no_threats_no_soft_signals(self):
        sig = _signals(overall_composite=1.0)
        assert classify(1.0, sig, sig["aivss"]) == "anomalous"

    def test_zero_everything(self):
        sig = _signals(overall_composite=0.0)
        assert classify(0.0, sig, sig["aivss"]) == "anomalous"

    def test_exploitation_critical_is_hard_block(self):
        sig = _signals(overall_composite=6.0, exploitation_severity="CRITICAL")
        assert classify(6.0, sig, sig["aivss"]) == "anomalous"

    def test_manipulation_critical_is_hard_block(self):
        sig = _signals(overall_composite=5.5, manipulation_severity="CRITICAL")
        assert classify(5.5, sig, sig["aivss"]) == "anomalous"

    def test_high_composite_no_threats_no_block(self):
        """Composite just below confirmed, no per-threat, no soft signals → suspicious not anomalous."""
        sig = _signals(overall_composite=5.0)
        result = classify(5.0, sig, sig["aivss"])
        assert result != "anomalous"


# ---------------------------------------------------------------------------
# process_signals() — OCSF field correctness
# ---------------------------------------------------------------------------

class TestProcessSignalsOCSFShape:
    def test_always_emits_overall_finding(self):
        sig = _signals(overall_composite=3.12)
        findings = process_signals("test_arch", sig, run_id="run1", ts=1000)
        flows = [f["finding"]["uid"].split("-")[-1] for f in findings]
        assert "overall" in flows

    def test_zero_coverage_flows_are_skipped(self):
        """inbound/outbound at 0.0 with 0 coverage should not appear."""
        sig = _signals(overall_composite=3.12, inbound_composite=0.0, outbound_composite=0.0)
        findings = process_signals("test_arch", sig, run_id="r1", ts=1)
        flows = {f["finding"]["uid"].split("-")[-1] for f in findings}
        assert "inbound" not in flows
        assert "outbound" not in flows

    def test_nonzero_flow_is_included(self):
        sig = _signals(overall_composite=3.12, internal_composite=6.25,
                       internal_severity="MEDIUM")
        findings = process_signals("test_arch", sig, run_id="r1", ts=1)
        flows = {f["finding"]["uid"].split("-")[-1] for f in findings}
        assert "internal" in flows

    def test_class_uid_is_2001(self):
        sig = _signals()
        for f in process_signals("a", sig, run_id="r", ts=1):
            assert f["class_uid"] == 2001

    def test_class_name(self):
        sig = _signals()
        for f in process_signals("a", sig, run_id="r", ts=1):
            assert f["class_name"] == "Security Finding"

    def test_ocsf_version(self):
        sig = _signals()
        for f in process_signals("a", sig, run_id="r", ts=1):
            assert f["ocsf_version"] == "1.1"

    def test_severity_id_mapping(self):
        mapping = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        for sev, expected_id in mapping.items():
            sig = _signals(overall_composite=3.0, overall_severity=sev)
            overall = next(f for f in process_signals("a", sig, run_id="r", ts=1)
                           if f["finding"]["uid"].endswith("overall"))
            assert overall["severity_id"] == expected_id, f"severity_id wrong for {sev}"

    def test_status_id_mapping(self):
        """confirmed=1, suspicious=2, anomalous=3."""
        # confirmed
        sig = _signals(overall_composite=8.0, overall_severity="HIGH")
        overall = next(f for f in process_signals("a", sig, run_id="r", ts=1)
                       if f["finding"]["uid"].endswith("overall"))
        assert overall["status"] == "confirmed"
        assert overall["status_id"] == 1

        # suspicious
        sig2 = _signals(overall_composite=5.0)
        overall2 = next(f for f in process_signals("a", sig2, run_id="r", ts=1)
                        if f["finding"]["uid"].endswith("overall"))
        assert overall2["status"] == "suspicious"
        assert overall2["status_id"] == 2

        # anomalous
        sig3 = _signals(overall_composite=1.0)
        overall3 = next(f for f in process_signals("a", sig3, run_id="r", ts=1)
                        if f["finding"]["uid"].endswith("overall"))
        assert overall3["status"] == "anomalous"
        assert overall3["status_id"] == 3

    def test_finding_uid_includes_run_id_and_flow(self):
        sig = _signals()
        findings = process_signals("my_arch", sig, run_id="run99", ts=1)
        for f in findings:
            assert "run99" in f["finding"]["uid"]
            # flow suffix is always the last segment
            assert f["finding"]["uid"].split("-")[-1] in {"inbound", "internal", "outbound", "overall"}

    def test_resource_arch_name(self):
        sig = _signals()
        for f in process_signals("my_arch", sig, run_id="r", ts=1):
            assert f["resources"][0]["name"] == "my_arch"

    def test_metadata_product_name(self):
        sig = _signals()
        for f in process_signals("a", sig, run_id="r", ts=1):
            assert f["metadata"]["product"]["name"] == "ThreatAssessor"

    def test_unmapped_carries_composite(self):
        sig = _signals(overall_composite=6.25)
        overall = next(f for f in process_signals("a", sig, run_id="r", ts=1)
                       if f["finding"]["uid"].endswith("overall"))
        assert overall["unmapped"]["aivss_composite"] == 6.25

    def test_top_threats_in_unmapped_and_related_events(self):
        threats = [
            {"technique_id": "T1190", "technique_name": "Exploit", "composite": 9.0, "severity": "CRITICAL"},
            {"technique_id": "T1078", "technique_name": "Valid Accounts", "composite": 7.5, "severity": "HIGH"},
            {"technique_id": "T1059", "technique_name": "Command Exec", "composite": 5.0, "severity": "MEDIUM"},
            {"technique_id": "T1110", "technique_name": "Brute Force", "composite": 2.0, "severity": "LOW"},
        ]
        sig = _signals(overall_composite=3.12, per_threat=threats)
        overall = next(f for f in process_signals("a", sig, run_id="r", ts=1)
                       if f["finding"]["uid"].endswith("overall"))
        # Top 3 by composite, sorted descending
        assert overall["finding"]["related_events"] == ["T1190", "T1078", "T1059"]
        assert overall["unmapped"]["top_threats"] == ["T1190", "T1078", "T1059"]

    def test_manipulation_signal_in_desc(self):
        sig = _signals(overall_composite=5.0, manipulation_severity="HIGH")
        overall = next(f for f in process_signals("a", sig, run_id="r", ts=1)
                       if f["finding"]["uid"].endswith("overall"))
        assert "manipulation=HIGH" in overall["finding"]["desc"]

    def test_leakage_in_desc(self):
        sig = _signals(overall_composite=5.0, leakage_detected=True)
        overall = next(f for f in process_signals("a", sig, run_id="r", ts=1)
                       if f["finding"]["uid"].endswith("overall"))
        assert "leakage detected" in overall["finding"]["desc"]

    def test_json_serialisable(self):
        sig = _signals(overall_composite=3.12, internal_composite=6.25,
                       per_threat=[_critical_threat()])
        findings = process_signals("arch", sig, run_id="r", ts=1)
        assert json.dumps(findings)  # must not raise


# ---------------------------------------------------------------------------
# Scenario: real corpus-like governance_signals shapes
# ---------------------------------------------------------------------------

class TestCorpusScenarios:
    def _complex_enterprise_signals(self):
        """Mirrors 10_complex_enterprise: internal 6.25, overall 3.12, per-threat CRITICAL."""
        return _signals(
            overall_composite=3.12,
            overall_severity="LOW",
            internal_composite=6.25,
            internal_severity="MEDIUM",
            manipulation_severity="LOW",
            confidence_swing=12.64,
            per_threat=[
                {"technique_id": "AP-1", "composite": 10.0, "severity": "CRITICAL", "top_metric": "DC"},
                {"technique_id": "AP-2", "composite": 10.0, "severity": "CRITICAL", "top_metric": "DC"},
            ],
        )

    def test_complex_enterprise_internal_is_suspicious(self):
        sig = self._complex_enterprise_signals()
        findings = process_signals("10_complex_enterprise", sig, run_id="r", ts=1)
        internal = next(f for f in findings if f["finding"]["uid"].endswith("internal"))
        assert internal["status"] == "suspicious"

    def test_complex_enterprise_overall_is_anomalous(self):
        sig = self._complex_enterprise_signals()
        findings = process_signals("10_complex_enterprise", sig, run_id="r", ts=1)
        overall = next(f for f in findings if f["finding"]["uid"].endswith("overall"))
        assert overall["status"] == "anomalous"

    def test_fully_defended_high_aivss_is_confirmed(self):
        """A well-scored architecture with no governance blocks should be confirmed."""
        sig = _signals(
            overall_composite=7.5,
            overall_severity="HIGH",
            internal_composite=8.0,
            internal_severity="HIGH",
            manipulation_severity="LOW",
            exploitation_severity="LOW",
        )
        findings = process_signals("defended_arch", sig, run_id="r", ts=1)
        overall = next(f for f in findings if f["finding"]["uid"].endswith("overall"))
        assert overall["status"] == "confirmed"

    def test_injection_attack_always_anomalous(self):
        """CRITICAL exploitation (injection detected) must dominate regardless of AIVSS score."""
        sig = _signals(
            overall_composite=6.5,
            internal_composite=6.5,
            exploitation_severity="CRITICAL",
        )
        for f in process_signals("attacked_arch", sig, run_id="r", ts=1):
            assert f["status"] == "anomalous"

    def test_minimal_vulnerable_shape(self):
        """Mirrors 01_minimal_vulnerable: manipulation MEDIUM, internal 6.25."""
        sig = _signals(
            overall_composite=3.12,
            internal_composite=6.25,
            internal_severity="MEDIUM",
            manipulation_severity="MEDIUM",
        )
        findings = process_signals("01_minimal_vulnerable", sig, run_id="r", ts=1)
        internal = next(f for f in findings if f["finding"]["uid"].endswith("internal"))
        assert internal["status"] == "suspicious"

    def test_zero_aivss_no_threats_no_signals(self):
        """Fully clean arch with no signal should produce only overall=anomalous."""
        sig = _signals(overall_composite=0.0)
        findings = process_signals("clean_arch", sig, run_id="r", ts=1)
        assert len(findings) == 1
        assert findings[0]["status"] == "anomalous"
        assert findings[0]["finding"]["uid"].endswith("overall")


# ---------------------------------------------------------------------------
# CLI modes — write/read via tmp_path
# ---------------------------------------------------------------------------

class TestCLIModes:
    def test_file_mode_writes_ocsf_json(self, tmp_path):
        sig = _signals(overall_composite=5.0, internal_composite=5.0,
                       internal_severity="MEDIUM")
        sig_path = tmp_path / "governance_signals.json"
        sig_path.write_text(json.dumps(sig))

        # Simulate --file mode
        signals = json.loads(sig_path.read_text())
        findings = _mod.process_signals(sig_path.parent.name, signals)
        out = sig_path.parent / "ocsf_findings.json"
        out.write_text(json.dumps(findings, indent=2))

        assert out.exists()
        loaded = json.loads(out.read_text())
        assert isinstance(loaded, list)
        assert all(f["class_uid"] == 2001 for f in loaded)

    def test_missing_governance_signals_returns_zeros(self, tmp_path):
        arch_dir = tmp_path / "no_signals_arch"
        arch_dir.mkdir()
        name, c, s, a, out_path = _mod.process_arch(arch_dir)
        assert c == s == a == 0
        assert out_path is None

    def test_process_arch_writes_findings(self, tmp_path):
        arch_dir = tmp_path / "test_arch"
        arch_dir.mkdir()
        sig = _signals(overall_composite=5.0, internal_composite=5.0,
                       internal_severity="MEDIUM")
        (arch_dir / "governance_signals.json").write_text(json.dumps(sig))

        name, c, s, a, out_path = _mod.process_arch(arch_dir)
        assert out_path is not None and out_path.exists()
        assert name == "test_arch"
        assert s > 0

    def test_process_arch_counts_are_accurate(self, tmp_path):
        arch_dir = tmp_path / "counted_arch"
        arch_dir.mkdir()
        # internal=suspicious, overall=anomalous → 0 confirmed, 1 suspicious, 1 anomalous
        sig = _signals(overall_composite=3.12, internal_composite=6.25,
                       internal_severity="MEDIUM",
                       per_threat=[_critical_threat()])
        (arch_dir / "governance_signals.json").write_text(json.dumps(sig))
        _, c, s, a, _ = _mod.process_arch(arch_dir)
        assert c == 0
        assert s == 1
        assert a == 1
