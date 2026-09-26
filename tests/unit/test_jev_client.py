"""
Unit tests — JevClient (chatbot/modules/jev_client.py).

All offline. No network calls.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from chatbot.modules.jev_client import JevClient, get_jev_client


@pytest.fixture(autouse=True)
def reset_circuit():
    """Reset class-level circuit state before every test."""
    JevClient.reset_circuit()
    yield
    JevClient.reset_circuit()


# ── is_enabled ────────────────────────────────────────────────────────────────

def test_is_enabled_false_when_no_api_key(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    assert JevClient.is_enabled() is False


def test_is_enabled_false_when_disabled_env(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "some-key")
    monkeypatch.setenv("JEV_ENABLED", "0")
    assert JevClient.is_enabled() is False


def test_is_enabled_false_when_disabled_false(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "some-key")
    monkeypatch.setenv("JEV_ENABLED", "false")
    assert JevClient.is_enabled() is False


def test_is_enabled_true_when_key_set(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "some-key")
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    assert JevClient.is_enabled() is True


# ── ask: disabled / fallback ──────────────────────────────────────────────────

def test_ask_returns_empty_when_disabled(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    client = JevClient(api_key="")
    result = client.ask({"x": 1}, {"q": {"type": "noul", "instructions": "test"}})
    assert result == {}


def test_ask_returns_answers_on_success(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answers": {"is_ok": {"noul": 0.9}}}
    with patch("requests.post", return_value=mock_resp):
        client = JevClient(api_key="test-key")
        result = client.ask({"x": 1}, {"is_ok": {"type": "noul", "instructions": "test?"}})
    assert result == {"is_ok": {"noul": 0.9}}


# ── Circuit breaker ────────────────────────────────────────────────────────────

def test_circuit_breaker_opens_after_3_failures(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    client = JevClient(api_key="test-key")
    with patch("requests.post", side_effect=ConnectionError("timeout")):
        client.ask({}, {})
        client.ask({}, {})
        assert not JevClient._circuit_open
        client.ask({}, {})
        assert JevClient._circuit_open


def test_circuit_breaker_blocks_subsequent_calls(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    client = JevClient(api_key="test-key")
    with patch("requests.post", side_effect=ConnectionError("timeout")):
        for _ in range(3):
            client.ask({}, {})
    assert JevClient._circuit_open
    # After circuit opens, ask() should return {} without calling requests.post
    with patch("requests.post") as mock_post:
        result = client.ask({"x": 1}, {})
        mock_post.assert_not_called()
    assert result == {}


def test_reset_circuit_re_enables(monkeypatch):
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.delenv("JEV_ENABLED", raising=False)
    client = JevClient(api_key="test-key")
    with patch("requests.post", side_effect=ConnectionError("timeout")):
        for _ in range(3):
            client.ask({}, {})
    assert JevClient._circuit_open
    JevClient.reset_circuit()
    assert not JevClient._circuit_open
    assert JevClient._consecutive_failures == 0


# ── Singleton ─────────────────────────────────────────────────────────────────

def test_get_jev_client_returns_same_instance():
    import chatbot.modules.jev_client as mod
    mod._DEFAULT_CLIENT = None  # reset singleton
    c1 = get_jev_client()
    c2 = get_jev_client()
    assert c1 is c2
    mod._DEFAULT_CLIENT = None  # cleanup
