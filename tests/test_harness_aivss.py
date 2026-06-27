"""Tests for AIVSS v4 flow scorer and per-agent gate."""
import pytest
from chatbot.modules.harness_aivss import (
    AIVSSFlowScorer,
    AIVSSAgentGate,
    AIVSSFlowScore,
    AIVSSScore,
    _severity,
    _composite,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_signals():
    return {
        "exploitation": {"severity": "LOW", "injection_patterns": [], "path_traversal": [], "homoglyph_count": 0, "url_encoded_count": 0},
        "manipulation": {"severity": "LOW", "confidence_swing_detected": False, "divergence_detected": False},
        "leakage": {"severity": "LOW", "pii_indicators": [], "supply_chain_risk": False},
        "identity": {"severity": "LOW", "tool_errors": [], "critic_tool_calls": {}, "supply_chain_modified_modules": False},
        "sovereignty": {"severity": "LOW", "cross_boundary_nodes": []},
    }


@pytest.fixture
def injection_signals(clean_signals):
    s = dict(clean_signals)
    s["exploitation"] = {
        "severity": "HIGH",
        "injection_patterns": ["javascript:alert(1)"],
        "path_traversal": [],
        "homoglyph_count": 0,
        "url_encoded_count": 0,
    }
    return s


@pytest.fixture
def pii_signals(clean_signals):
    s = dict(clean_signals)
    s["leakage"] = {
        "severity": "HIGH",
        "pii_indicators": ["S1234567A", "john@example.com"],
        "supply_chain_risk": False,
    }
    return s


@pytest.fixture
def traversal_signals(clean_signals):
    s = dict(clean_signals)
    s["exploitation"] = {
        "severity": "CRITICAL",
        "injection_patterns": [],
        "path_traversal": ["../../etc/passwd"],
        "homoglyph_count": 0,
        "url_encoded_count": 0,
    }
    return s


@pytest.fixture
def minimal_ground_truth():
    return {
        "expected_attack_paths": [
            {
                "id": "AP-1",
                "title": "Ransomware via T1486",
                "techniques": ["T1486"],
                "criticality_tier": "CRITICAL",
            }
        ],
        "rapids_scores": {
            "ransomware": {"score": 85},
            "defensibility": 40,
        },
    }


@pytest.fixture
def scorer():
    return AIVSSFlowScorer(industry="government_public")


# ---------------------------------------------------------------------------
# Severity helper
# ---------------------------------------------------------------------------

class TestSeverity:
    def test_low(self):
        assert _severity(0.0) == "LOW"
        assert _severity(3.9) == "LOW"

    def test_medium(self):
        assert _severity(4.0) == "MEDIUM"
        assert _severity(6.9) == "MEDIUM"

    def test_high(self):
        assert _severity(7.0) == "HIGH"
        assert _severity(8.9) == "HIGH"

    def test_critical(self):
        assert _severity(9.0) == "CRITICAL"
        assert _severity(10.0) == "CRITICAL"


class TestComposite:
    def test_empty_is_zero(self):
        assert _composite({}) == 0.0

    def test_single_metric(self):
        assert _composite({"a": 0.70}) == pytest.approx(7.0)

    def test_capped_at_10(self):
        assert _composite({"a": 1.0, "b": 0.95}) == 10.0


# ---------------------------------------------------------------------------
# Inbound scoring
# ---------------------------------------------------------------------------

class TestInbound:
    def test_clean_input_scores_low(self, scorer, clean_signals):
        result = scorer.score_inbound(clean_signals)
        assert isinstance(result, AIVSSFlowScore)
        assert result.composite == 0.0
        assert result.severity == "LOW"

    def test_injection_raises_score(self, scorer, injection_signals):
        result = scorer.score_inbound(injection_signals)
        assert result.composite > 0
        assert "LL" in result.metrics or "CS" in result.metrics

    def test_traversal_populates_cs(self, scorer, traversal_signals):
        result = scorer.score_inbound(traversal_signals)
        assert "CS" in result.metrics
        assert result.metrics["CS"].composite >= 9.0

    def test_pii_adds_ds(self, scorer, pii_signals):
        result = scorer.score_inbound(pii_signals)
        assert "DS" in result.metrics

    def test_homoglyph_adds_mr(self, scorer, clean_signals):
        signals = dict(clean_signals)
        signals["exploitation"] = {**signals["exploitation"], "homoglyph_count": 3}
        result = scorer.score_inbound(signals)
        assert "MR" in result.metrics

    def test_sovereignty_adds_gv(self, scorer, clean_signals):
        signals = dict(clean_signals)
        signals["sovereignty"] = {"severity": "MEDIUM", "cross_boundary_nodes": ["SG→AU"]}
        result = scorer.score_inbound(signals)
        assert "GV" in result.metrics

    def test_coverage_pct_increases_with_signals(self, scorer, injection_signals):
        clean_result = scorer.score_inbound({"exploitation": {}, "leakage": {}, "identity": {}, "sovereignty": {}, "manipulation": {}})
        inject_result = scorer.score_inbound(injection_signals)
        assert inject_result.coverage_pct >= clean_result.coverage_pct


# ---------------------------------------------------------------------------
# Internal scoring
# ---------------------------------------------------------------------------

class TestInternal:
    def test_clean_internal_is_low(self, scorer, clean_signals):
        result = scorer.score_internal(clean_signals)
        assert result.composite == 0.0

    def test_confidence_swing_populates_aa_dc(self, scorer, clean_signals):
        signals = dict(clean_signals)
        signals["manipulation"] = {"severity": "HIGH", "confidence_swing_detected": True, "divergence_detected": False}
        result = scorer.score_internal(signals)
        assert "AA" in result.metrics
        assert "DC" in result.metrics

    def test_tool_errors_populate_gv_ll(self, scorer, clean_signals):
        signals = dict(clean_signals)
        signals["identity"] = {"severity": "MEDIUM", "tool_errors": ["architect: PermissionError"], "critic_tool_calls": {}, "supply_chain_modified_modules": False}
        result = scorer.score_internal(signals)
        assert "GV" in result.metrics
        assert "LL" in result.metrics

    def test_sm_retriggers_add_ad(self, scorer, clean_signals):
        class FakeSM:
            retrigger_count = 3
        result = scorer.score_internal(clean_signals, sm_result=FakeSM())
        assert "AD" in result.metrics


# ---------------------------------------------------------------------------
# Outbound scoring
# ---------------------------------------------------------------------------

class TestOutbound:
    def test_clean_outbound_is_low(self, scorer, clean_signals):
        result = scorer.score_outbound(clean_signals)
        assert result.composite == 0.0

    def test_pii_adds_ds_cs(self, scorer, pii_signals):
        result = scorer.score_outbound(pii_signals)
        assert "DS" in result.metrics
        assert "CS" in result.metrics
        assert result.metrics["DS"].composite > 0

    def test_sovereignty_adds_ei(self, scorer, clean_signals):
        signals = dict(clean_signals)
        signals["sovereignty"] = {"severity": "HIGH", "cross_boundary_nodes": ["SG→US"]}
        result = scorer.score_outbound(signals)
        assert "EI" in result.metrics

    def test_high_arc_soc_adds_ei(self, scorer, clean_signals):
        result = scorer.score_outbound(clean_signals, arc_scores={"SOC": 80})
        assert "EI" in result.metrics


# ---------------------------------------------------------------------------
# Per-threat scoring
# ---------------------------------------------------------------------------

class TestPerThreat:
    def test_known_technique_scored(self, scorer, minimal_ground_truth):
        results = scorer.score_per_threat(minimal_ground_truth)
        assert len(results) == 1
        t = results[0]
        assert t.composite > 0
        assert t.severity in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_ransomware_technique_is_high_or_critical(self, scorer, minimal_ground_truth):
        results = scorer.score_per_threat(minimal_ground_truth)
        assert results[0].composite >= 7.0

    def test_defensibility_reduces_score(self, scorer):
        gt_low_def = {
            "expected_attack_paths": [{"id": "AP-1", "title": "Ransomware", "techniques": ["T1486"]}],
            "rapids_scores": {"defensibility": 10},
        }
        gt_high_def = {
            "expected_attack_paths": [{"id": "AP-1", "title": "Ransomware", "techniques": ["T1486"]}],
            "rapids_scores": {"defensibility": 90},
        }
        low = scorer.score_per_threat(gt_low_def)[0].composite
        high = scorer.score_per_threat(gt_high_def)[0].composite
        assert low > high

    def test_unknown_technique_still_scores_via_rapids(self, scorer):
        gt = {
            "expected_attack_paths": [{"id": "AP-1", "title": "Custom", "techniques": ["T9999"]}],
            "rapids_scores": {"ransomware": {"score": 85}},
        }
        results = scorer.score_per_threat(gt)
        assert len(results) == 1
        assert results[0].composite > 0

    def test_empty_ground_truth_returns_empty(self, scorer):
        assert scorer.score_per_threat({}) == []


# ---------------------------------------------------------------------------
# Full compute
# ---------------------------------------------------------------------------

class TestCompute:
    def test_compute_returns_aivss_score(self, scorer, clean_signals, minimal_ground_truth):
        result = scorer.compute(clean_signals, minimal_ground_truth)
        assert isinstance(result, AIVSSScore)
        assert result.industry == "government_public"
        assert isinstance(result.overall, float)
        assert 0.0 <= result.overall <= 10.0

    def test_compute_to_dict_schema(self, scorer, clean_signals, minimal_ground_truth):
        d = scorer.compute(clean_signals, minimal_ground_truth).to_dict()
        assert all(k in d for k in ("industry", "inbound", "internal", "outbound", "overall", "per_threat", "coverage_pct"))
        assert "composite" in d["overall"]
        assert "severity" in d["overall"]

    def test_compute_per_threat_populated(self, scorer, clean_signals, minimal_ground_truth):
        result = scorer.compute(clean_signals, minimal_ground_truth)
        assert len(result.per_threat) == 1

    def test_overall_weighted_within_bounds(self, scorer, injection_signals, minimal_ground_truth):
        result = scorer.compute(injection_signals, minimal_ground_truth)
        assert 0.0 <= result.overall <= 10.0


# ---------------------------------------------------------------------------
# AIVSSAgentGate
# ---------------------------------------------------------------------------

class TestAgentGate:
    def test_no_config_allows_all_tools(self):
        gate = AIVSSAgentGate()
        assert gate.check_tool_allowed("architect", "search_mitre", None) is True

    def test_allowed_tools_restricts(self):
        class FakeCS:
            allowed_tools = ["search_mitre"]
            allowed_models = []
        gate = AIVSSAgentGate({"architect": FakeCS()})
        assert gate.check_tool_allowed("architect", "search_mitre", FakeCS()) is True
        assert gate.check_tool_allowed("architect", "run_exploit", FakeCS()) is False

    def test_empty_allowed_tools_allows_all(self):
        class FakeCS:
            allowed_tools = []
            allowed_models = []
        gate = AIVSSAgentGate({"architect": FakeCS()})
        assert gate.check_tool_allowed("architect", "anything", FakeCS()) is True

    def test_tighten_high_disables_tools(self, scorer, injection_signals):
        class FakeCritic:
            _tools_enabled = True
            model = "claude-sonnet-4-6"
            role = "architect"
        class FakeOrch:
            architect = FakeCritic()
            tester = FakeCritic()
            red_team = FakeCritic()
            purple_team = FakeCritic()

        inbound = scorer.score_inbound(traversal_signals_for_gate())
        gate = AIVSSAgentGate()
        gate.tighten(FakeOrch(), inbound)
        # If traversal composite >= 7.0, tools should be disabled
        if inbound.composite >= 7.0:
            assert FakeOrch.architect._tools_enabled is False

    def test_tighten_with_none_orchestrator_is_noop(self):
        gate = AIVSSAgentGate()
        inbound = AIVSSFlowScore(composite=8.5, severity="HIGH")
        gate.tighten(None, inbound)  # should not raise

    def test_configure_critic_restricts_model(self):
        class FakeCS:
            allowed_models = ["haiku-4-5"]
            allowed_tools = []
        class FakeCritic:
            def __init__(self):
                self.model = "claude-sonnet-4-6"
                self.role = "tester"
        gate = AIVSSAgentGate({"tester": FakeCS()})
        critic = FakeCritic()
        gate.configure_critic(critic, "tester")
        assert critic.model == "haiku-4-5"


def traversal_signals_for_gate():
    return {
        "exploitation": {"severity": "CRITICAL", "injection_patterns": [], "path_traversal": ["../../etc"], "homoglyph_count": 0, "url_encoded_count": 0},
        "manipulation": {"severity": "LOW"},
        "leakage": {"severity": "LOW", "pii_indicators": []},
        "identity": {"severity": "LOW", "tool_errors": [], "critic_tool_calls": {}},
        "sovereignty": {"severity": "LOW", "cross_boundary_nodes": []},
    }


# ---------------------------------------------------------------------------
# to_dict round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_flow_score_to_dict(self):
        from chatbot.modules.harness_aivss import AIVSSMetricScore
        score = AIVSSFlowScore(
            metrics={"CS": AIVSSMetricScore("CS", {"model_manipulation": 0.9}, 9.0, 1)},
            composite=9.0,
            severity="CRITICAL",
            coverage_pct=10,
        )
        d = score.to_dict()
        assert d["composite"] == 9.0
        assert d["severity"] == "CRITICAL"
        assert "CS" in d["metrics"]

    def test_aivss_score_to_dict_no_per_agent(self, scorer, clean_signals):
        result = scorer.compute(clean_signals, {})
        d = result.to_dict()
        assert isinstance(d["per_threat"], list)
        assert isinstance(d["per_agent"], dict)
