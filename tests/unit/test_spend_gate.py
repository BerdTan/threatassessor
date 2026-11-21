"""Spend gate (Entry 264 step 1): one fail-closed gate, verdict not boolean.

Principle 5: enforcement lives in code. Fail closed: a kill switch that
cannot be read must not silently allow spend.
"""
import pytest

from chatbot.harness import spend_gate as sg


def _policy(tmp_path, text):
    p = tmp_path / "agent_governance.yaml"
    p.write_text(text)
    return p


class TestVerdict:
    def test_allow_when_policy_clean(self, tmp_path):
        p = _policy(tmp_path, "bouncer:\n  kill_switch: false\n")
        v = sg.check(entry_point="analyze-stream", policy_path=p)
        assert v.action == "allow" and v.allowed

    def test_kill_switch_true_is_kill(self, tmp_path):
        p = _policy(tmp_path, "bouncer:\n  kill_switch: true\n")
        v = sg.check(entry_point="x", policy_path=p)
        assert v.action == "kill" and not v.allowed
        assert "kill_switch=True in agent_governance.yaml" in v.reason

    def test_blocked_architecture_is_block(self, tmp_path):
        p = _policy(tmp_path, "bouncer:\n  blocked_architectures: [evil]\n")
        v = sg.check(entry_point="x", architecture="evil", policy_path=p)
        assert v.action == "block" and "blocked_architectures" in v.reason
        assert sg.check(entry_point="x", architecture="ok", policy_path=p).allowed

    def test_missing_bouncer_section_allows(self, tmp_path):
        p = _policy(tmp_path, "other: 1\n")
        assert sg.check(entry_point="x", policy_path=p).allowed


class TestFailClosed:
    def test_unparseable_policy_blocks(self, tmp_path):
        p = _policy(tmp_path, "bouncer: [unclosed\n  - : :\n")
        v = sg.check(entry_point="x", policy_path=p)
        assert v.action == "block" and v.reason.startswith("policy_unreadable")

    def test_missing_policy_file_blocks(self, tmp_path):
        v = sg.check(entry_point="x", policy_path=tmp_path / "nope.yaml")
        assert v.action == "block" and v.reason.startswith("policy_unreadable")

    def test_non_mapping_policy_blocks(self, tmp_path):
        p = _policy(tmp_path, "- just\n- a list\n")
        assert sg.check(entry_point="x", policy_path=p).action == "block"

    def test_non_bool_kill_switch_blocks(self, tmp_path):
        p = _policy(tmp_path, "bouncer:\n  kill_switch: 'yes please'\n")
        assert sg.check(entry_point="x", policy_path=p).action == "block"

    def test_default_path_independent_of_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        v = sg.check(entry_point="x")
        assert not v.reason.startswith("policy_unreadable")

    def test_check_never_raises(self, tmp_path):
        v = sg.check(entry_point="x", policy_path=object())
        assert v.action == "block"


class TestVerdictShape:
    def test_ladder_actions(self):
        assert sg.ACTIONS == ("allow", "steer", "throttle", "block", "kill")

    def test_only_allow_is_allowed(self):
        for a in sg.ACTIONS:
            assert sg.Verdict(a, "r").allowed == (a == "allow")


class TestEntryPointCoverage:
    """One test per spend route: the gate dependency must be attached."""

    @pytest.fixture(scope="class")
    def gated(self):
        from chatbot.api.app import create_app
        app = create_app()
        found = {}
        for r in app.routes:
            dep = getattr(r, "dependant", None)
            if not dep:
                continue
            names = _walk(dep)
            for m in getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}:
                found[(m, r.path)] = "spend_gate" in names
        return found

    @pytest.mark.parametrize("method,path", sg.SPEND_ROUTES)
    def test_route_has_gate(self, gated, method, path):
        key = next((k for k in gated if k[0] == method and k[1].endswith(path)), None)
        assert key is not None, f"route {method} {path} not found in app"
        assert gated[key], f"{method} {path} spends but lacks spend_gate"

    def test_no_unlisted_route_calls_llm_directly(self):
        """A new route that calls an LLM path must be listed in SPEND_ROUTES."""
        import inspect
        from chatbot.api.app import create_app
        markers = ("LLMClient(", "run_moe_pipeline(", "harness.run(", "run_typed(",
                   "analyze_with_progress(")
        listed = {(m, p) for m, p in sg.SPEND_ROUTES}
        offenders = []
        for r in create_app().routes:
            fn = getattr(r, "endpoint", None)
            if fn is None:
                continue
            try:
                src = inspect.getsource(fn)
            except (OSError, TypeError):
                continue
            if any(mk in src for mk in markers):
                for m in getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}:
                    if not any(m == lm and r.path.endswith(lp) for lm, lp in listed):
                        offenders.append((m, r.path))
        assert not offenders, f"LLM-calling routes missing from SPEND_ROUTES: {offenders}"


def _walk(dep):
    names = set()
    call = getattr(dep, "call", None)
    if call is not None:
        names.add(getattr(call, "__name__", ""))
        names.add(getattr(call, "gate_name", ""))
    for sub in getattr(dep, "dependencies", []):
        names |= _walk(sub)
    return names


class TestLiveRoute:
    """The gate actually refuses a request, ahead of any spend."""

    def _client(self, monkeypatch, tmp_path, text):
        from fastapi.testclient import TestClient
        from chatbot.api.app import create_app
        monkeypatch.setenv("API_KEY", "k")
        monkeypatch.setattr(sg, "POLICY_PATH", _policy(tmp_path, text))
        return TestClient(create_app())

    def test_kill_switch_returns_503_before_work(self, monkeypatch, tmp_path):
        c = self._client(monkeypatch, tmp_path, "bouncer:\n  kill_switch: true\n")
        r = c.post("/api/v1/boxing/run", json={}, headers={"TM-API-KEY": "k"})
        assert r.status_code == 503
        assert r.json()["detail"]["action"] == "kill"

    def test_unreadable_policy_returns_403(self, monkeypatch, tmp_path):
        c = self._client(monkeypatch, tmp_path, "bouncer: [unclosed\n")
        r = c.post("/api/v1/boxing/run", json={}, headers={"TM-API-KEY": "k"})
        assert r.status_code == 403
        assert r.json()["detail"]["reason"].startswith("policy_unreadable")

    def test_auth_still_checked_first(self, monkeypatch, tmp_path):
        c = self._client(monkeypatch, tmp_path, "bouncer:\n  kill_switch: true\n")
        r = c.post("/api/v1/boxing/run", json={}, headers={"TM-API-KEY": "wrong"})
        assert r.status_code == 401


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestThrottle:
    """Per-caller soft limit (Entry 264 step 3): verdict is throttle, not block."""

    LIMITS = "bouncer:\n  caller_limits: {window_s: 60, max_requests: 2, max_tokens: 100}\n"

    def _ledger(self):
        from chatbot.harness.spend_ledger import SpendLedger
        clk = _Clock()
        return SpendLedger(clock=clk), clk

    def test_under_limit_allows(self, tmp_path):
        led, _ = self._ledger()
        led.record("a", requests=1)
        v = sg.check("x", caller_id="a", policy_path=_policy(tmp_path, self.LIMITS), ledger=led)
        assert v.action == "allow"

    def test_request_limit_throttles(self, tmp_path):
        led, _ = self._ledger()
        led.record("a", requests=2)
        v = sg.check("x", caller_id="a", policy_path=_policy(tmp_path, self.LIMITS), ledger=led)
        assert v.action == "throttle" and "requests" in v.reason and not v.allowed

    def test_token_limit_throttles(self, tmp_path):
        led, _ = self._ledger()
        led.record("a", tokens=100)
        v = sg.check("x", caller_id="a", policy_path=_policy(tmp_path, self.LIMITS), ledger=led)
        assert v.action == "throttle" and "tokens" in v.reason

    def test_other_caller_unaffected(self, tmp_path):
        led, _ = self._ledger()
        led.record("a", requests=5)
        assert sg.check("x", caller_id="b", policy_path=_policy(tmp_path, self.LIMITS), ledger=led).allowed

    def test_window_slides(self, tmp_path):
        led, clk = self._ledger()
        led.record("a", requests=2)
        clk.t += 61
        assert sg.check("x", caller_id="a", policy_path=_policy(tmp_path, self.LIMITS), ledger=led).allowed

    def test_no_limits_configured_means_allow(self, tmp_path):
        led, _ = self._ledger()
        led.record("a", requests=999)
        assert sg.check("x", caller_id="a", policy_path=_policy(tmp_path, "bouncer: {}\n"), ledger=led).allowed

    def test_malformed_limits_fail_closed(self, tmp_path):
        led, _ = self._ledger()
        p = _policy(tmp_path, "bouncer:\n  caller_limits: {window_s: -5, max_requests: 1}\n")
        assert sg.check("x", caller_id="a", policy_path=p, ledger=led).action == "block"

    def test_kill_outranks_throttle(self, tmp_path):
        led, _ = self._ledger()
        led.record("a", requests=9)
        p = _policy(tmp_path, "bouncer:\n  kill_switch: true\n  caller_limits: {max_requests: 1}\n")
        assert sg.check("x", caller_id="a", policy_path=p, ledger=led).action == "kill"

    def test_pipeline_stage_does_not_double_throttle(self, tmp_path):
        led, _ = self._ledger()
        led.record("a", requests=2)
        v = sg.check("pipeline", caller_id="a", policy_path=_policy(tmp_path, self.LIMITS),
                     ledger=led, enforce_limits=False)
        assert v.allowed

    def test_ledger_bounded(self):
        from chatbot.harness import spend_ledger as sl
        led, _ = self._ledger()
        for i in range(sl._MAX_CALLERS + 10):
            led.record(f"c{i}", requests=1)
        assert len(led._events) <= sl._MAX_CALLERS


class TestThrottleLive:
    def test_second_request_gets_429_then_other_caller_passes(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient
        from chatbot.api.app import create_app
        from chatbot.harness.spend_ledger import LEDGER
        LEDGER.reset()
        monkeypatch.setenv("API_KEY", "k")
        monkeypatch.setattr(sg, "POLICY_PATH", _policy(
            tmp_path, "bouncer:\n  caller_limits: {window_s: 60, max_requests: 1}\n"))
        c = TestClient(create_app())
        h = {"TM-API-KEY": "k", "TM-CALLER": "noisy"}
        c.post("/api/v1/boxing/run", json={}, headers=h)  # counted; body may 4xx later
        r = c.post("/api/v1/boxing/run", json={}, headers=h)
        assert r.status_code == 429 and r.json()["detail"]["action"] == "throttle"
        r2 = c.post("/api/v1/boxing/run", json={}, headers={"TM-API-KEY": "k", "TM-CALLER": "quiet"})
        assert r2.status_code != 429
        LEDGER.reset()
