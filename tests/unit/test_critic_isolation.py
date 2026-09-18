"""
Tests for the _run_isolated critic subprocess isolation utility
(Engine Item 6.1 — chatbot/modules/agents/orchestrators/moe_orchestrator.py).
"""

import pytest
import time

import chatbot.modules.agents.orchestrators.moe_orchestrator as _mod
from chatbot.modules.agents.orchestrators.moe_orchestrator import _run_isolated, CRITIC_ISOLATION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _identity(x):
    return x


def _raise_value_error():
    raise ValueError("critic exploded")


def _sleep_and_return(secs, value):
    time.sleep(secs)
    return value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunIsolated:
    def test_returns_result_on_success(self):
        result = _run_isolated(_identity, 42)
        assert result == 42

    def test_passes_multiple_args(self):
        result = _run_isolated(lambda a, b: a + b, 3, 4)
        assert result == 7

    def test_propagates_exception_as_runtime_error(self):
        with pytest.raises(RuntimeError, match="critic exploded"):
            _run_isolated(_raise_value_error)

    def test_timeout_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="timed out"):
            _run_isolated(_sleep_and_return, 60, "never", timeout=1)

    def test_inline_when_isolation_disabled(self, monkeypatch):
        monkeypatch.setattr(_mod, "CRITIC_ISOLATION", False)
        result = _run_isolated(_identity, "hello")
        assert result == "hello"

    def test_picklable_dataclass_roundtrip(self):
        from chatbot.modules.artifact_extractor import ArtifactSet
        a = ArtifactSet(tier1_critical={"k": 1}, tier2_important={}, completeness={})
        result = _run_isolated(_identity, a)
        assert result.tier1_critical == {"k": 1}

    def test_default_isolation_is_enabled(self):
        assert CRITIC_ISOLATION is True
