# ThreatAssessor Harness v2 — Extension Architecture Design

**Status:** Implemented — 2026-08-01 (commits 224d95a, 5c4326e). Two items intentionally deferred (see end of doc).  
**Scope:** Three roles: Orchestrator (decouple front/backend), Broker (policy-driven routing), Bouncer (kill switch / isolation). Incremental additions only — nothing removed, existing callers unaffected.

---

## Current state (what works well, do not touch)

- `PipelineContext` as a transport-agnostic dict — all stages read/write a single bag. Clean.
- `ThreatAssessorHarness` as the single callable surface — API, MCP, backtest all use the same entry point.
- `CriticRegistry.activate()` + `blocked_agents` — governance already suppresses critics by name.
- `HarnessModelGuardian` / `ModelRouter` — per-agent model routing with fallback chains already exists.
- `EventBrokerCritic` + three sinks — event fan-out is already decoupled from pipeline logic.
- `OutboundAIVSSGate` — a post-pipeline gate already exists. Its signal (`ctx["_outbound_blocked"]`) just isn't wired to actually stop anything.

## Three roles — gap → fix mapping

---

### Role 1: Orchestrator (decouple front/backend)

**Problem:** `ThreatAssessorHarness.run()` is synchronous and blocking. Any long caller (MCP, CI/CD job) blocks the thread. No typed request/response contract means the front/backend coupling is implicit — callers must read source to know what to pass.

**Design:**

```
PipelineRequest   ← typed entry point (replaces 9 positional keyword args)
PipelineResponse  ← typed exit point (success/failure, ctx summary, errors)
AsyncHarness      ← thin async wrapper via asyncio.to_thread()
ProgressProtocol  ← TypeAlias for the callback contract
```

**`PipelineRequest` (new dataclass in controller.py):**
```python
@dataclass
class PipelineRequest:
    architecture_path: str
    report_dir: str
    ssp_profile: str = "low_risk_cloud"
    use_llm: bool = False
    use_moe: bool = False
    use_sm: bool = False
    scenario: str = ScenarioConfig.API_ONLY
    run_id: str = ""           # caller-supplied; auto-generated if empty
    metadata: dict = field(default_factory=dict)  # passthrough to ctx
```

**`PipelineResponse` (new dataclass in controller.py):**
```python
@dataclass
class PipelineResponse:
    success: bool
    run_id: str
    architecture_name: str
    confidence: Optional[float]
    errors: List[str]
    stage_timings: Dict[str, dict]
    governance_summary: dict      # overall_risk_level + AIVSS composite
    detect_summary: dict          # which DETECT rules fired + trends
    ctx: PipelineContext          # full context for callers that need raw access
```

**`AsyncThreatAssessorHarness` (new class, same file):**
```python
class AsyncThreatAssessorHarness:
    async def run(self, request: PipelineRequest,
                  progress_callback=None) -> PipelineResponse:
        loop = asyncio.get_event_loop()
        harness = ThreatAssessorHarness(scenario=request.scenario)
        return await loop.run_in_executor(
            None, lambda: harness.run_typed(request, progress_callback)
        )
```

`ThreatAssessorHarness.run()` gains a `run_typed(request, callback)` method that wraps the existing keyword-arg interface. Old callers unchanged.

**`ProgressProtocol`:**
```python
ProgressCallback = Callable[[str, int, str], None]  # (stage, pct, msg)
```

---

### Role 2: Broker (policy-driven routing)

**Problem:** Model routing is static (settings.yaml). Blocked agents are computed once from governance severity before critics run and never updated mid-pipeline. Event fan-out has no content-based routing — a CRITICAL governance event and a DEBUG stage_complete share the same sink path.

**Design:**

```
PolicyBroker      ← new class: consumes live signals → BrokerDecision
BrokerDecision    ← dataclass: blocked_agents + model_overrides + sink_tier
EventPriority     ← enum: CRITICAL | HIGH | NORMAL | DEBUG
```

**`PolicyBroker` (new file: `chatbot/harness/policy_broker.py`):**
```python
@dataclass
class BrokerDecision:
    blocked_agents:  List[str]          # dynamic update to ctx["blocked_agents"]
    model_overrides: Dict[str, str]     # {agent_name: model_id}
    sink_tier:       str                # "critical" | "normal" | "audit_only"
    rationale:       str                # for audit trail

class PolicyBroker:
    def decide(self, governance: GovernanceSignals,
               aivss: AIVSSScore) -> BrokerDecision:
        """
        Called by ThreatAssessorHarness after QualityStage, before CriticStage.
        Reads live signals and returns a routing decision.

        Rules (in priority order):
          1. CRITICAL exploitation.blocked → block ALL critics, sink_tier=critical
          2. AIVSS inbound >= 7.0          → block red_team + blackhat (attack surface too high)
          3. governance.overall == HIGH     → downgrade blackhat to cheaper model
          4. sm_verdicts.acceptance_rate <= 0.4 → flag to sink_tier=critical
          5. Default                        → no changes from settings.yaml baseline
        """
```

**Wire into `ThreatAssessorHarness.run()`** after `QualityStage`, before `CriticStage`:
```python
broker = PolicyBroker()
decision = broker.decide(merged_governance, ctx.get("_aivss_gate"))
ctx["blocked_agents"] = decision.blocked_agents
ctx["_broker_decision"] = decision
self._guardian.apply_overrides(decision.model_overrides)
```

**Event priority routing** in `EventBrokerCritic.emit()`:
```python
# Add priority field to HarnessEvent
event_priority = _infer_priority(event)  # CRITICAL for blocked/gate events
if event_priority == EventPriority.CRITICAL:
    for sink in self._priority_sinks:    # separate list of high-priority sinks
        sink.emit(event)
else:
    for sink in self._sinks:
        sink.emit(event)
```

`_priority_sinks` is configured in `agent_governance.yaml` — a SIEM sink can be listed as priority-only so DEBUG events never reach it.

---

### Role 3: Bouncer (kill switch / isolation layer)

**Problem:** `ctx["_outbound_blocked"]` is set but never read. `QualityStage.required=False` means CRITICAL input only appends to `ctx.errors`, never halts. No post-critic output governance. No circuit breaker on model calls.

**Design:**

```
BouncerStage           ← new required stage: reads signals, raises BlockedPipelineError
BlockedPipelineError   ← new exception: carries block reason + audit payload
PostCriticGuard        ← inline check in CriticStage after MoE returns
CircuitBreaker         ← wrapper around ModelRouter
```

**`BouncerStage` (add to stages.py, insert after QualityStage):**
```python
class BouncerStage(PipelineStage):
    """
    Hard isolation gate. Runs after QualityStage, before CriticStage.
    Raises BlockedPipelineError (required=True → halts pipeline) when:
      - exploitation.blocked is True (CRITICAL injection/traversal)
      - outbound_blocked is True (AIVSS gate tripped from prior run)
      - governance.overall_risk_level == CRITICAL

    Also checks the bouncer_config in agent_governance.yaml for:
      - kill_switch: true  → unconditional block regardless of signals
      - blocked_architectures: [name, ...]  → block specific arch names
    """
    name = "bouncer"
    required = True   # ← hard stop, not optional

    def _logic(self, ctx, **kw):
        exploit  = ctx.get("governance_signals", {}).get("exploitation", {})
        outbound = ctx.get("_outbound_blocked", False)

        if exploit.get("blocked"):
            raise BlockedPipelineError("exploitation.blocked=True", ctx)
        if outbound:
            raise BlockedPipelineError("outbound_aivss_gate_tripped", ctx)

        # Kill switch from policy YAML
        bouncer_cfg = self._load_bouncer_cfg()
        if bouncer_cfg.get("kill_switch"):
            raise BlockedPipelineError("kill_switch=True in agent_governance.yaml", ctx)
        if ctx.get("architecture_name") in bouncer_cfg.get("blocked_architectures", []):
            raise BlockedPipelineError("architecture explicitly blocked", ctx)

        return ctx
```

**`BlockedPipelineError` (add to controller.py):**
```python
class BlockedPipelineError(Exception):
    def __init__(self, reason: str, ctx: PipelineContext):
        self.reason = reason
        self.ctx    = ctx
        super().__init__(f"Pipeline blocked: {reason}")
```

**Post-critic output governance** (add to `CriticStage._logic()` after `run_moe_pipeline()`):
```python
# Scan MoE output for PII/credential leakage before writing to ctx
moe_dict = moe_result.to_dict() if moe_result else {}
output_sig = adapter.check_artifact(moe_dict)
if output_sig.leakage.get("severity") == "CRITICAL":
    _emit(ctx, "governance_complete", "post_critic_guard", {
        "blocked": True, "reason": "critic_output_leakage"
    })
    raise BlockedPipelineError("critic output contains critical leakage", ctx)
```

**`CircuitBreaker` (add to controller.py, wraps `ModelRouter`):**
```python
class CircuitBreaker:
    """Wraps ModelRouter. Opens after N consecutive ModelChainExhaustedErrors."""
    THRESHOLD = 3
    RESET_SECONDS = 60

    def get_model(self, agent_name: str) -> Optional[str]:
        if self._is_open(agent_name):
            raise BlockedPipelineError(f"circuit_open:{agent_name}", PipelineContext())
        try:
            model = self._router.get_model(agent_name)
            self._reset(agent_name)
            return model
        except ModelChainExhaustedError:
            self._record_failure(agent_name)
            raise
```

---

## Stage order after v2

```
QualityStage          ← governance signals from input + artifact
BouncerStage (NEW)    ← hard isolation gate (required=True)
PolicyBroker call     ← dynamic routing decision injected into ctx
CriticStage           ← MoE critics (post-output guard deferred — see status table)
ScrumMasterStage
AIVSSStage
OutboundAIVSSGate     ← wire _outbound_blocked read → BouncerStage handles it
RecordEventStage
```

---

## What does NOT change

- `PipelineContext` dict interface — all existing stages read/write unchanged
- `ThreatAssessorHarness.run()` keyword signature — old callers still work
- `EventBrokerCritic` fan-out — adding priority routing is additive
- `CriticRegistry.activate()` + `blocked_agents` — PolicyBroker adds to it, doesn't replace it
- Any sink implementation — SiemSink, LangfuseSink, WebhookSink unchanged

---

## Why this order matters for MCP

When MCP calls `analyze_architecture()`:
1. `PipelineRequest` carries the submitted .mmd and ssp_profile cleanly
2. `AsyncThreatAssessorHarness` runs it in a thread, returns `PipelineResponse`
3. If the input is adversarial, `BouncerStage` raises `BlockedPipelineError` — MCP returns a structured error to the caller, not a partial result
4. If governance signals indicate risk mid-run, `PolicyBroker` reroutes critics at runtime
5. `PipelineResponse.detect_summary` gives the caller the DETECT rule firing summary in one field — no need to call `get_detect_trends()` separately for a quick assessment

This design makes TA safe to expose externally: external callers cannot affect the internal pipeline (bouncer), and the pipeline cannot affect external systems without explicit policy (broker + outbound gate).

---

## Implementation status — 2026-08-08

| Component | Status | Notes |
|---|---|---|
| `PipelineRequest` / `PipelineResponse` | ✅ Shipped | `controller.py` |
| `AsyncThreatAssessorHarness` | ✅ Shipped | `asyncio.to_thread()` wrapper |
| `ProgressCallback` TypeAlias | ✅ Shipped | `controller.py` |
| `PolicyBroker` / `BrokerDecision` | ✅ Shipped | `policy_broker.py`; 5 routing rules |
| `BouncerStage` (`required=True`) | ✅ Shipped | `stages.py`; kill_switch + blocked_architectures |
| `BlockedPipelineError` | ✅ Shipped | `controller.py`; API returns 400 |
| `CircuitBreaker` | ✅ Shipped | `controller.py`; wraps ModelRouter |
| `PipelineResponse.detect_summary` | ✅ Shipped | `{rules_fired, total_fired}` populated by AIVSSStage |
| **`EventPriority` / `_priority_sinks`** | ⏸ Deferred | `sink_tier` is computed in `BrokerDecision` but `EventBrokerCritic` does not read it. No current consumer needs priority routing — all sinks receive all events. Implement when a SIEM sink needs to suppress DEBUG events. |
| **Post-critic output guard** | ⏸ Deferred | Design: scan MoE output dict through `check_artifact()` for leakage before writing to ctx. Not built — MoE critics do not handle raw user data, so leakage risk is low. Revisit if critics gain direct file/network access. |
