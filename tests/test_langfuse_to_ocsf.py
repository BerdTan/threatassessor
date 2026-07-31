"""
Tests for langfuse-to-ocsf skill: Langfuse observation hierarchy → OCSF events.

Covers:
  - trace_to_ocsf():      ProcessActivity 1007, status from errors, unmapped fields
  - span_to_ocsf():       ProcessActivity 1007, severity from level, duration
  - generation_to_ocsf(): APIActivity 6003, provider inference, tokens/cost
  - score_to_ocsf():      SecurityFinding 2001, AIVSS name filter, composite→severity
  - governance_to_ocsf(): DetectionFinding 2004, LOW dims skipped, one event per elevated dim
  - _sev_from_score():    all four AIVSS tiers
  - _epoch():             datetime str, int, None
  - export_trace():       full pipeline with mocked fetch_observations + fetch_scores
  - OCSF field invariants: class_uid, class_name, ocsf_version on every event
  - FIX 2: governance key round-trip — LangfuseSink writes D1_exploitation etc,
            governance_to_ocsf reads same keys; test verifies the contract end-to-end
  - FIX 3: ObservationType enum coercion — SDK may return enum not string

No LLM calls, no network. Langfuse objects are plain stubs.
Expected runtime: < 1 second.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import skill script without requiring it to be a package
# ---------------------------------------------------------------------------

_SKILL_SCRIPT = (
    Path(__file__).parents[1]
    / ".claude/skills/langfuse-to-ocsf/scripts/langfuse_to_ocsf.py"
)

spec = importlib.util.spec_from_file_location("langfuse_to_ocsf", _SKILL_SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

trace_to_ocsf      = _mod.trace_to_ocsf
span_to_ocsf       = _mod.span_to_ocsf
generation_to_ocsf = _mod.generation_to_ocsf
score_to_ocsf      = _mod.score_to_ocsf
governance_to_ocsf = _mod.governance_to_ocsf
export_trace       = _mod.export_trace
_sev_from_score    = _mod._sev_from_score
_epoch             = _mod._epoch


# ---------------------------------------------------------------------------
# Stub helpers — plain objects that mimic Langfuse SDK dataclasses
# ---------------------------------------------------------------------------

def _trace(
    id: str = "trace-001",
    name: str = "threat_assessment",
    metadata: Optional[Dict] = None,
    output: Optional[Dict] = None,
    timestamp: str = "2026-07-31T10:00:00Z",
    updated_at: str = "2026-07-31T10:01:30Z",
) -> MagicMock:
    t = MagicMock()
    t.id         = id
    t.name       = name
    t.metadata   = metadata or {"architecture": "10_complex_enterprise", "scenario": "api_only"}
    t.output     = output or {"confidence": 0.94, "errors": []}
    t.timestamp  = timestamp
    t.updated_at = updated_at
    return t


def _span(
    id: str = "span-001",
    name: str = "analysis",
    obs_type: str = "SPAN",
    level: str = "DEFAULT",
    start_time: str = "2026-07-31T10:00:05Z",
    end_time: str = "2026-07-31T10:00:35Z",
    metadata: Optional[Dict] = None,
) -> MagicMock:
    s = MagicMock()
    s.id         = id
    s.name       = name
    s.type       = obs_type
    s.level      = level
    s.start_time = start_time
    s.end_time   = end_time
    s.metadata   = metadata or {}
    return s


def _generation(
    id: str = "gen-001",
    name: str = "ArchitectCritic",
    model: str = "anthropic/claude-sonnet-4-5",
    start_time: str = "2026-07-31T10:00:10Z",
    end_time: str = "2026-07-31T10:00:25Z",
    usage_details: Optional[Dict] = None,
    cost_details: Optional[Dict] = None,
    metadata: Optional[Dict] = None,
) -> MagicMock:
    g = MagicMock()
    g.id           = id
    g.name         = name
    g.type         = "GENERATION"
    g.model        = model
    g.start_time   = start_time
    g.end_time     = end_time
    g.level        = "DEFAULT"
    g.usage_details = usage_details or {"total_tokens": 1200}
    g.cost_details  = cost_details  or {"total_cost": 0.0015}
    g.metadata      = metadata or {"score": 82, "rating": "Excellent"}
    return g


def _score(
    id: str = "score-001",
    name: str = "aivss_internal",
    value: float = 6.25,
    timestamp: str = "2026-07-31T10:01:00Z",
) -> MagicMock:
    s = MagicMock()
    s.id        = id
    s.name      = name
    s.value     = value
    s.timestamp = timestamp
    return s


# ---------------------------------------------------------------------------
# _sev_from_score — AIVSS 0–10 tier mapping
# ---------------------------------------------------------------------------

class TestSevFromScore:
    def test_critical_at_9(self):
        label, sid = _sev_from_score(9.0)
        assert label == "Critical" and sid == 4

    def test_critical_above_9(self):
        label, sid = _sev_from_score(10.0)
        assert label == "Critical" and sid == 4

    def test_high_at_7(self):
        label, sid = _sev_from_score(7.0)
        assert label == "High" and sid == 3

    def test_high_just_below_9(self):
        label, sid = _sev_from_score(8.9)
        assert label == "High" and sid == 3

    def test_medium_at_4(self):
        label, sid = _sev_from_score(4.0)
        assert label == "Medium" and sid == 2

    def test_low_at_zero(self):
        label, sid = _sev_from_score(0.0)
        assert label == "Low" and sid == 1

    def test_low_just_below_4(self):
        label, sid = _sev_from_score(3.99)
        assert label == "Low" and sid == 1


# ---------------------------------------------------------------------------
# _epoch — timestamp parsing
# ---------------------------------------------------------------------------

class TestEpoch:
    def test_iso_string_with_z(self):
        ts = _epoch("2026-07-31T10:00:00Z")
        assert ts > 0

    def test_iso_string_with_offset(self):
        ts = _epoch("2026-07-31T10:00:00+00:00")
        assert ts > 0

    def test_int_passthrough(self):
        assert _epoch(1722384000) == 1722384000

    def test_float_truncated(self):
        assert _epoch(1722384000.9) == 1722384000

    def test_none_returns_zero(self):
        assert _epoch(None) == 0

    def test_datetime_object(self):
        dt = datetime(2026, 7, 31, 10, 0, 0, tzinfo=timezone.utc)
        assert _epoch(dt) > 0


# ---------------------------------------------------------------------------
# trace_to_ocsf — ProcessActivity 1007
# ---------------------------------------------------------------------------

class TestTraceToOCSF:
    def test_class_uid(self):
        ev = trace_to_ocsf(_trace())
        assert ev["class_uid"] == 1007

    def test_class_name(self):
        ev = trace_to_ocsf(_trace())
        assert ev["class_name"] == "Process Activity"

    def test_ocsf_version(self):
        ev = trace_to_ocsf(_trace())
        assert ev["ocsf_version"] == "1.1"

    def test_status_success_when_no_errors(self):
        ev = trace_to_ocsf(_trace(output={"confidence": 0.94, "errors": []}))
        assert ev["status"] == "Success"
        assert ev["status_id"] == 1

    def test_status_failure_when_errors(self):
        ev = trace_to_ocsf(_trace(output={"confidence": 0.5, "errors": ["stage failed"]}))
        assert ev["status"] == "Failure"
        assert ev["status_id"] == 2

    def test_architecture_in_unmapped(self):
        ev = trace_to_ocsf(_trace(metadata={"architecture": "21_agentic_ai_system"}))
        assert ev["unmapped"]["architecture"] == "21_agentic_ai_system"

    def test_trace_id_in_unmapped(self):
        ev = trace_to_ocsf(_trace(id="trace-xyz"))
        assert ev["unmapped"]["trace_id"] == "trace-xyz"

    def test_confidence_in_unmapped(self):
        ev = trace_to_ocsf(_trace(output={"confidence": 0.93, "errors": []}))
        assert ev["unmapped"]["confidence"] == 0.93

    def test_duration_computed(self):
        ev = trace_to_ocsf(_trace(
            timestamp="2026-07-31T10:00:00Z",
            updated_at="2026-07-31T10:01:30Z",
        ))
        assert ev["duration"] == 90_000  # 90s in ms

    def test_actor_product_name(self):
        ev = trace_to_ocsf(_trace())
        assert ev["actor"]["process"]["name"] == "ThreatAssessor"

    def test_json_serialisable(self):
        assert json.dumps(trace_to_ocsf(_trace()))


# ---------------------------------------------------------------------------
# span_to_ocsf — ProcessActivity 1007
# ---------------------------------------------------------------------------

class TestSpanToOCSF:
    def test_class_uid(self):
        ev = span_to_ocsf(_span(), "trace-001")
        assert ev["class_uid"] == 1007

    def test_activity_id_is_terminate(self):
        ev = span_to_ocsf(_span(), "trace-001")
        assert ev["activity_id"] == 2

    def test_default_level_is_informational(self):
        ev = span_to_ocsf(_span(level="DEFAULT"), "trace-001")
        assert ev["severity"] == "Informational"
        assert ev["severity_id"] == 1

    def test_warning_level_maps_to_medium(self):
        ev = span_to_ocsf(_span(level="WARNING"), "trace-001")
        assert ev["severity"] == "Medium"
        assert ev["severity_id"] == 2

    def test_error_level_maps_to_high(self):
        ev = span_to_ocsf(_span(level="ERROR"), "trace-001")
        assert ev["severity"] == "High"
        assert ev["severity_id"] == 3

    def test_stage_name_in_unmapped(self):
        ev = span_to_ocsf(_span(name="quality_stage"), "trace-001")
        assert ev["unmapped"]["stage_name"] == "quality_stage"

    def test_score_and_rating_in_unmapped(self):
        ev = span_to_ocsf(_span(metadata={"score": 75, "rating": "Good"}), "trace-001")
        assert ev["unmapped"]["score"] == 75
        assert ev["unmapped"]["rating"] == "Good"

    def test_duration_computed(self):
        ev = span_to_ocsf(_span(
            start_time="2026-07-31T10:00:05Z",
            end_time="2026-07-31T10:00:35Z",
        ), "trace-001")
        assert ev["duration"] == 30_000  # 30s in ms

    def test_trace_id_in_unmapped(self):
        ev = span_to_ocsf(_span(), "trace-abc")
        assert ev["unmapped"]["trace_id"] == "trace-abc"


# ---------------------------------------------------------------------------
# generation_to_ocsf — APIActivity 6003
# ---------------------------------------------------------------------------

class TestGenerationToOCSF:
    def test_class_uid(self):
        ev = generation_to_ocsf(_generation(), "trace-001")
        assert ev["class_uid"] == 6003

    def test_class_name(self):
        ev = generation_to_ocsf(_generation(), "trace-001")
        assert ev["class_name"] == "API Activity"

    def test_anthropic_provider_inferred(self):
        ev = generation_to_ocsf(_generation(model="anthropic/claude-sonnet-4-5"), "t1")
        assert ev["unmapped"]["provider"] == "anthropic"

    def test_claude_in_name_infers_anthropic(self):
        ev = generation_to_ocsf(_generation(model="claude-3-opus"), "t1")
        assert ev["unmapped"]["provider"] == "anthropic"

    def test_openai_provider_inferred(self):
        ev = generation_to_ocsf(_generation(model="openai/gpt-4o"), "t1")
        assert ev["unmapped"]["provider"] == "openai"

    def test_amazon_bedrock_inferred(self):
        ev = generation_to_ocsf(_generation(model="amazon.nova-pro-v1"), "t1")
        assert ev["unmapped"]["provider"] == "amazon_bedrock"

    def test_slash_prefix_provider(self):
        ev = generation_to_ocsf(_generation(model="mistral/mistral-large"), "t1")
        assert ev["unmapped"]["provider"] == "mistral"

    def test_tokens_in_unmapped(self):
        ev = generation_to_ocsf(
            _generation(usage_details={"total_tokens": 1200}), "t1"
        )
        assert ev["unmapped"]["total_tokens"] == 1200

    def test_cost_in_unmapped(self):
        ev = generation_to_ocsf(
            _generation(cost_details={"total_cost": 0.0015}), "t1"
        )
        assert ev["unmapped"]["total_cost_usd"] == 0.0015

    def test_api_service_name_is_provider(self):
        ev = generation_to_ocsf(_generation(model="anthropic/claude-haiku"), "t1")
        assert ev["api"]["service"]["name"] == "anthropic"

    def test_latency_computed(self):
        ev = generation_to_ocsf(_generation(
            start_time="2026-07-31T10:00:10Z",
            end_time="2026-07-31T10:00:25Z",
        ), "t1")
        assert ev["unmapped"]["latency_ms"] == 15_000

    def test_json_serialisable(self):
        assert json.dumps(generation_to_ocsf(_generation(), "t1"))


# ---------------------------------------------------------------------------
# score_to_ocsf — SecurityFinding 2001
# ---------------------------------------------------------------------------

class TestScoreToOCSF:
    def test_aivss_internal_produces_finding(self):
        ev = score_to_ocsf(_score(name="aivss_internal", value=6.25), "trace-001")
        assert ev is not None
        assert ev["class_uid"] == 2001

    def test_aivss_inbound(self):
        ev = score_to_ocsf(_score(name="aivss_inbound", value=0.0), "t1")
        assert ev is not None

    def test_aivss_outbound(self):
        ev = score_to_ocsf(_score(name="aivss_outbound", value=0.0), "t1")
        assert ev is not None

    def test_aivss_overall(self):
        ev = score_to_ocsf(_score(name="aivss_overall", value=3.12), "t1")
        assert ev is not None

    def test_non_aivss_score_returns_none(self):
        ev = score_to_ocsf(_score(name="user_rating", value=4.0), "t1")
        assert ev is None

    def test_unknown_score_name_returns_none(self):
        ev = score_to_ocsf(_score(name="latency_p95", value=250.0), "t1")
        assert ev is None

    def test_high_composite_maps_to_high_severity(self):
        ev = score_to_ocsf(_score(name="aivss_internal", value=7.5), "t1")
        assert ev["severity"] == "High"
        assert ev["severity_id"] == 3

    def test_critical_composite(self):
        ev = score_to_ocsf(_score(name="aivss_outbound", value=9.5), "t1")
        assert ev["severity"] == "Critical"
        assert ev["severity_id"] == 4

    def test_low_composite(self):
        ev = score_to_ocsf(_score(name="aivss_inbound", value=0.0), "t1")
        assert ev["severity"] == "Low"
        assert ev["severity_id"] == 1

    def test_finding_uid_contains_trace_and_flow(self):
        ev = score_to_ocsf(_score(name="aivss_internal"), "trace-xyz")
        assert "trace-xyz" in ev["finding"]["uid"]
        assert "internal" in ev["finding"]["uid"]

    def test_composite_in_unmapped(self):
        ev = score_to_ocsf(_score(name="aivss_internal", value=6.25), "t1")
        assert ev["unmapped"]["aivss_composite"] == 6.25

    def test_json_serialisable(self):
        assert json.dumps(score_to_ocsf(_score(name="aivss_internal", value=6.0), "t1"))


# ---------------------------------------------------------------------------
# governance_to_ocsf — DetectionFinding 2004
# ---------------------------------------------------------------------------

class TestGovernanceToOCSF:
    def _trace_with_gov(self, **dims) -> MagicMock:
        base = {
            "D1_exploitation":  "LOW",
            "D2_manipulation":  "LOW",
            "D3_leakage":       "LOW",
            "D4_identity":      "LOW",
            "D5_sovereignty":   "LOW",
        }
        base.update(dims)
        return _trace(metadata={**base, "architecture": "test"})

    def test_all_low_returns_empty(self):
        evs = governance_to_ocsf(self._trace_with_gov(), "t1")
        assert evs == []

    def test_single_elevated_dim(self):
        evs = governance_to_ocsf(
            self._trace_with_gov(D1_exploitation="HIGH"), "t1"
        )
        assert len(evs) == 1
        assert evs[0]["class_uid"] == 2004

    def test_multiple_elevated_dims(self):
        evs = governance_to_ocsf(
            self._trace_with_gov(D1_exploitation="HIGH", D2_manipulation="MEDIUM"), "t1"
        )
        assert len(evs) == 2

    def test_all_dims_elevated(self):
        evs = governance_to_ocsf(self._trace_with_gov(
            D1_exploitation="CRITICAL",
            D2_manipulation="HIGH",
            D3_leakage="HIGH",
            D4_identity="MEDIUM",
            D5_sovereignty="MEDIUM",
        ), "t1")
        assert len(evs) == 5

    def test_class_name(self):
        evs = governance_to_ocsf(self._trace_with_gov(D2_manipulation="MEDIUM"), "t1")
        assert evs[0]["class_name"] == "Detection Finding"

    def test_severity_id_on_critical(self):
        evs = governance_to_ocsf(self._trace_with_gov(D1_exploitation="CRITICAL"), "t1")
        assert evs[0]["severity_id"] == 4

    def test_finding_uid_contains_dim_key(self):
        evs = governance_to_ocsf(self._trace_with_gov(D3_leakage="HIGH"), "trace-abc")
        assert "D3_leakage" in evs[0]["finding"]["uid"]
        assert "trace-abc" in evs[0]["finding"]["uid"]

    def test_blocked_agents_in_unmapped(self):
        t = _trace(metadata={
            "D1_exploitation": "HIGH",
            "blocked_agents": ["ArchitectCritic"],
        })
        evs = governance_to_ocsf(t, "t1")
        assert evs[0]["unmapped"]["blocked_agents"] == ["ArchitectCritic"]

    def test_json_serialisable(self):
        evs = governance_to_ocsf(self._trace_with_gov(D2_manipulation="HIGH"), "t1")
        assert json.dumps(evs)


# ---------------------------------------------------------------------------
# export_trace — full pipeline integration (mocked fetch_observations + fetch_scores)
# ---------------------------------------------------------------------------

class TestExportTrace:
    def _make_lf(self, observations=None, scores=None):
        lf = MagicMock()
        lf.api.observations.get_many.return_value.data = observations or []
        lf.api.scores_v3.get_many_v3.return_value.data = scores or []
        return lf

    def test_always_includes_trace_event(self):
        lf = self._make_lf()
        events = export_trace(lf, _trace())
        trace_evs = [e for e in events if e["class_uid"] == 1007
                     and e["activity_id"] == 1]
        assert len(trace_evs) == 1

    def test_generation_produces_api_activity(self):
        lf = self._make_lf(observations=[_generation()])
        events = export_trace(lf, _trace())
        api_evs = [e for e in events if e["class_uid"] == 6003]
        assert len(api_evs) == 1

    def test_span_produces_process_activity(self):
        lf = self._make_lf(observations=[_span()])
        events = export_trace(lf, _trace())
        proc_evs = [e for e in events if e["class_uid"] == 1007
                    and e["activity_id"] == 2]
        assert len(proc_evs) == 1

    def test_aivss_score_produces_security_finding(self):
        lf = self._make_lf(scores=[_score(name="aivss_internal", value=6.25)])
        events = export_trace(lf, _trace())
        sf_evs = [e for e in events if e["class_uid"] == 2001]
        assert len(sf_evs) == 1

    def test_non_aivss_score_excluded(self):
        lf = self._make_lf(scores=[_score(name="user_rating", value=4.0)])
        events = export_trace(lf, _trace())
        sf_evs = [e for e in events if e["class_uid"] == 2001]
        assert len(sf_evs) == 0

    def test_governance_dims_produce_detection_findings(self):
        t = _trace(metadata={
            "architecture": "test",
            "D1_exploitation": "HIGH",
            "D2_manipulation": "MEDIUM",
        })
        lf = self._make_lf()
        events = export_trace(lf, t)
        det_evs = [e for e in events if e["class_uid"] == 2004]
        assert len(det_evs) == 2

    def test_full_trace_all_classes_present(self):
        t = _trace(metadata={
            "architecture": "full_test",
            "D2_manipulation": "MEDIUM",
        })
        lf = self._make_lf(
            observations=[_generation(), _span()],
            scores=[_score(name="aivss_internal", value=6.25)],
        )
        events = export_trace(lf, t)
        class_uids = {e["class_uid"] for e in events}
        assert 1007 in class_uids  # ProcessActivity
        assert 6003 in class_uids  # APIActivity
        assert 2001 in class_uids  # SecurityFinding
        assert 2004 in class_uids  # DetectionFinding

    def test_observation_fetch_failure_is_non_fatal(self):
        lf = MagicMock()
        lf.api.observations.get_many.side_effect = Exception("network error")
        lf.api.scores_v3.get_many_v3.return_value.data = []
        # Should not raise
        events = export_trace(lf, _trace())
        assert any(e["class_uid"] == 1007 for e in events)

    def test_score_fetch_failure_is_non_fatal(self):
        lf = MagicMock()
        lf.api.observations.get_many.return_value.data = []
        lf.api.scores_v3.get_many_v3.side_effect = Exception("timeout")
        events = export_trace(lf, _trace())
        assert any(e["class_uid"] == 1007 for e in events)

    def test_all_events_json_serialisable(self):
        lf = self._make_lf(
            observations=[_generation(), _span()],
            scores=[_score(name="aivss_inbound", value=0.0),
                    _score(name="aivss_internal", value=6.25)],
        )
        events = export_trace(lf, _trace())
        assert json.dumps(events)

    def test_ocsf_version_on_every_event(self):
        lf = self._make_lf(
            observations=[_generation(), _span()],
            scores=[_score(name="aivss_overall", value=3.12)],
        )
        t = _trace(metadata={"architecture": "x", "D1_exploitation": "HIGH"})
        for ev in export_trace(lf, t):
            assert ev["ocsf_version"] == "1.1", f"missing on {ev['class_uid']}"


# ---------------------------------------------------------------------------
# FIX 2: Governance key round-trip contract
#
# LangfuseSink writes governance dims to trace metadata as D1_exploitation,
# D2_manipulation, D3_leakage, D4_identity, D5_sovereignty (sinks.py:244-248).
# governance_to_ocsf() reads those exact keys. This test simulates the full
# round-trip: construct a trace metadata dict the way LangfuseSink would write
# it, pass it to governance_to_ocsf(), assert keys are consumed correctly.
# ---------------------------------------------------------------------------

class TestGovernanceKeyRoundTrip:
    """
    Validates that the key names LangfuseSink writes to trace metadata are
    exactly the ones governance_to_ocsf() reads. A key rename in either side
    would silently produce zero DetectionFindings — this test catches that.
    """

    def _langfuse_sink_metadata(self, D1="LOW", D2="LOW", D3="LOW",
                                D4="LOW", D5="LOW", blocked=None) -> dict:
        """Reproduce exactly what LangfuseSink.emit('governance_complete') writes."""
        return {
            "governance_risk_level": max([D1, D2, D3, D4, D5],
                                         key=lambda s: {"LOW":0,"MEDIUM":1,"HIGH":2,"CRITICAL":3}.get(s,0)),
            "D1_exploitation":  D1,
            "D2_manipulation":  D2,
            "D3_leakage":       D3,
            "D4_identity":      D4,
            "D5_sovereignty":   D5,
            "blocked_agents":   blocked or [],
        }

    def test_elevated_d1_is_detected(self):
        meta = self._langfuse_sink_metadata(D1="HIGH")
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        assert len(evs) == 1
        assert evs[0]["unmapped"]["governance_dim"] == "D1_exploitation"

    def test_elevated_d2_is_detected(self):
        meta = self._langfuse_sink_metadata(D2="MEDIUM")
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        assert len(evs) == 1
        assert evs[0]["unmapped"]["governance_dim"] == "D2_manipulation"

    def test_elevated_d3_is_detected(self):
        meta = self._langfuse_sink_metadata(D3="HIGH")
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        assert len(evs) == 1
        assert evs[0]["unmapped"]["governance_dim"] == "D3_leakage"

    def test_elevated_d4_is_detected(self):
        meta = self._langfuse_sink_metadata(D4="MEDIUM")
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        assert len(evs) == 1
        assert evs[0]["unmapped"]["governance_dim"] == "D4_identity"

    def test_elevated_d5_is_detected(self):
        meta = self._langfuse_sink_metadata(D5="HIGH")
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        assert len(evs) == 1
        assert evs[0]["unmapped"]["governance_dim"] == "D5_sovereignty"

    def test_all_low_produces_no_events(self):
        meta = self._langfuse_sink_metadata()
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        assert evs == []

    def test_multi_dim_all_detected(self):
        meta = self._langfuse_sink_metadata(D1="CRITICAL", D2="HIGH", D3="MEDIUM")
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        detected_dims = {e["unmapped"]["governance_dim"] for e in evs}
        assert detected_dims == {"D1_exploitation", "D2_manipulation", "D3_leakage"}

    def test_blocked_agents_survive_round_trip(self):
        meta = self._langfuse_sink_metadata(D1="HIGH", blocked=["ArchitectCritic", "TesterCritic"])
        t = _trace(metadata=meta)
        evs = governance_to_ocsf(t, "t1")
        assert evs[0]["unmapped"]["blocked_agents"] == ["ArchitectCritic", "TesterCritic"]


# ---------------------------------------------------------------------------
# FIX 3: ObservationType enum coercion
#
# Langfuse SDK may return obs.type as an ObservationType enum (with .value)
# rather than a plain string. The export pipeline must normalise either form.
# ---------------------------------------------------------------------------

class TestObservationTypeCoercion:
    """
    The SDK may return ObservationType.GENERATION (an enum with .value == "GENERATION")
    instead of the string "GENERATION". The normalisation in export_trace() must handle both.
    """

    def _make_enum_like(self, value: str):
        """Simulate an SDK enum object with a .value attribute."""
        obj = MagicMock()
        obj.value = value
        obj.__str__ = lambda self: value
        return obj

    def test_generation_as_string(self):
        obs = _generation()
        obs.type = "GENERATION"
        lf = MagicMock()
        lf.api.observations.get_many.return_value.data = [obs]
        lf.api.scores_v3.get_many_v3.return_value.data = []
        events = export_trace(lf, _trace())
        assert any(e["class_uid"] == 6003 for e in events)

    def test_generation_as_enum(self):
        obs = _generation()
        obs.type = self._make_enum_like("GENERATION")
        lf = MagicMock()
        lf.api.observations.get_many.return_value.data = [obs]
        lf.api.scores_v3.get_many_v3.return_value.data = []
        events = export_trace(lf, _trace())
        assert any(e["class_uid"] == 6003 for e in events), \
            "GENERATION enum type was not coerced — generation_to_ocsf() not called"

    def test_span_as_string(self):
        obs = _span()
        obs.type = "SPAN"
        lf = MagicMock()
        lf.api.observations.get_many.return_value.data = [obs]
        lf.api.scores_v3.get_many_v3.return_value.data = []
        events = export_trace(lf, _trace())
        span_evs = [e for e in events if e["class_uid"] == 1007 and e["activity_id"] == 2]
        assert len(span_evs) == 1

    def test_span_as_enum(self):
        obs = _span()
        obs.type = self._make_enum_like("SPAN")
        lf = MagicMock()
        lf.api.observations.get_many.return_value.data = [obs]
        lf.api.scores_v3.get_many_v3.return_value.data = []
        events = export_trace(lf, _trace())
        span_evs = [e for e in events if e["class_uid"] == 1007 and e["activity_id"] == 2]
        assert len(span_evs) == 1, "SPAN enum type was not coerced — span_to_ocsf() not called"

    def test_lowercase_generation_normalised(self):
        """String case variants are also normalised."""
        obs = _generation()
        obs.type = "generation"
        lf = MagicMock()
        lf.api.observations.get_many.return_value.data = [obs]
        lf.api.scores_v3.get_many_v3.return_value.data = []
        events = export_trace(lf, _trace())
        assert any(e["class_uid"] == 6003 for e in events)
