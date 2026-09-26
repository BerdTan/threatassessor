"""
JevClient — shared System 1 client for all Jev integration points.

Features:
- JEV_ENABLED env var: "0" or "false" → disabled globally
  Defaults to enabled when JEV_API_KEY is set, disabled otherwise.
- Session-level circuit breaker: 3 consecutive API failures → _circuit_open=True
  Logged once; all subsequent calls return {} instantly.
- ask(state, questions) → dict of answers, or {} on any error / disabled
- is_enabled() → bool
- No LLM, no generation. Falls back silently — callers never raise.
"""
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

JEV_API_URL = os.environ.get("JEV_API_URL", "https://api.typesafe.ai/v1/systemone")
JEV_MODEL = os.environ.get("JEV_MODEL", "jev-latest")
_FAILURE_THRESHOLD = 3


class JevClient:
    """Thread-safe Jev API client with circuit breaker and global enable/disable."""

    _lock = threading.Lock()
    _consecutive_failures = 0
    _circuit_open = False

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key or os.environ.get("JEV_API_KEY", "")
        self.timeout = timeout

    @classmethod
    def is_enabled(cls) -> bool:
        """Return True if Jev is enabled and circuit is closed."""
        env = os.environ.get("JEV_ENABLED", "").lower()
        if env in ("0", "false", "off", "no"):
            return False
        if cls._circuit_open:
            return False
        return bool(os.environ.get("JEV_API_KEY", ""))

    def ask(self, state: dict, questions: dict) -> dict:
        """
        POST to Jev /v1/systemone. Returns answers dict on success, {} on any failure.
        Never raises. Updates circuit breaker on failure.
        """
        if not self.is_enabled():
            return {}
        import requests
        try:
            resp = requests.post(
                JEV_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": JEV_MODEL, "state": state, "questions": questions},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            with self.__class__._lock:
                self.__class__._consecutive_failures = 0
            return resp.json().get("answers", {})
        except Exception as exc:
            with self.__class__._lock:
                self.__class__._consecutive_failures += 1
                if self.__class__._consecutive_failures >= _FAILURE_THRESHOLD:
                    if not self.__class__._circuit_open:
                        self.__class__._circuit_open = True
                        logger.error(
                            "JevClient: circuit breaker OPEN after %d failures — "
                            "Jev disabled for this session. Last error: %s",
                            _FAILURE_THRESHOLD, exc,
                        )
                    return {}
            logger.warning("JevClient: API error (failure %d/%d): %s",
                           self.__class__._consecutive_failures, _FAILURE_THRESHOLD, exc)
            return {}

    @classmethod
    def reset_circuit(cls) -> None:
        """Reset circuit breaker. For tests only."""
        with cls._lock:
            cls._consecutive_failures = 0
            cls._circuit_open = False


_DEFAULT_CLIENT: Optional[JevClient] = None


def get_jev_client() -> JevClient:
    """Return the session-singleton JevClient."""
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = JevClient()
    return _DEFAULT_CLIENT
