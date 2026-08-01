"""
ThreatAssessor Harness — controller gateway.

Responsibilities:
- Routes analysis runs to stage configurations by scenario
- Isolates stage failures (optional stages caught, not raised)
- Exposes model fallback via ModelRouter (wired to llm_client.py — no new deps)
- Single callable surface for API routes, MCP tools, and backtest loops

Framework alignment: interfaces mirror CrewAI Task/Agent/Crew and LiteLLM fallback
patterns without importing them. Future swap is one line per stage:
    stage.executor = CrewAIExecutor(...)
    stage.model_router = LiteLLMRouter(...)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.config.settings import AgentModelConfig, AgentSwarmConfig

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

#: Callback contract for pipeline progress updates.
#: Called as: callback(stage_name: str, percent: int, message: str)
ProgressCallback = Callable[[str, int, str], None]


# ---------------------------------------------------------------------------
# Typed request / response contract  (v2)
# ---------------------------------------------------------------------------

@dataclass
class PipelineRequest:
    """Typed entry point for ThreatAssessorHarness.run_typed() and AsyncHarness.

    Replaces the previous 9-keyword-argument surface. Old callers using
    harness.run(...keyword args...) continue to work unchanged.
    """
    architecture_path:    str
    report_dir:           str
    ssp_profile:          str  = "low_risk_cloud"
    use_llm:              bool = False
    enable_ssp:           bool = True
    enable_moe:           bool = False
    enable_scrum_master:  bool = False
    critic_mode:          str  = "partial_parallel"
    run_blackhat:         Optional[bool] = None
    architecture_name:    str  = ""
    run_id:               str  = ""   # auto-generated if empty
    metadata:             dict = field(default_factory=dict)


@dataclass
class PipelineResponse:
    """Typed exit point from run_typed() / AsyncHarness.

    success=False means the pipeline completed with errors but did not raise.
    If BlockedPipelineError was raised, the caller receives the exception
    directly rather than a PipelineResponse.
    """
    success:          bool
    run_id:           str
    architecture_name: str
    confidence:       Optional[float]
    errors:           List[str]
    stage_timings:    Dict[str, dict]
    governance_summary: dict   # {overall_risk_level, aivss_overall, aivss_severity}
    detect_summary:   dict     # {rules_fired: [...], total_fired: int}
    ctx:              "PipelineContext"   # raw context for callers that need it


# ---------------------------------------------------------------------------
# Bouncer exception
# ---------------------------------------------------------------------------

class BlockedPipelineError(Exception):
    """Raised by BouncerStage when the pipeline must halt for safety reasons.

    Callers should catch this and return a structured 400/403 response
    rather than a 500 — the pipeline was deliberately stopped, not broken.

    Attributes:
        reason:  short machine-readable code (exploitation.blocked, kill_switch, etc.)
        ctx:     PipelineContext at the point of blocking (for audit logging)
    """

    def __init__(self, reason: str, ctx: "PipelineContext"):
        self.reason = reason
        self.ctx    = ctx
        super().__init__(f"Pipeline blocked: {reason}")


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

_SCENARIO_REGISTRY: Dict[str, Callable[[], List["PipelineStage"]]] = {}


def register_scenario(name: str) -> Callable:
    """Decorator — register a stage-factory function under a scenario name.
    Adding a new scenario = one decorated function, no edits elsewhere.
    """
    def decorator(fn: Callable) -> Callable:
        _SCENARIO_REGISTRY[name] = fn
        return fn
    return decorator


class ScenarioConfig:
    QUICK_DET = "quick_det"   # AnalysisStage only — fast deterministic pass
    FULL_MOE  = "full_moe"    # Analysis + Report + Critics + ScrumMaster
    API_ONLY  = "api_only"    # Analysis + Report (default for streaming API)
    BACKTEST  = "backtest"    # AnalysisStage only — used in batch backtest loops


# ---------------------------------------------------------------------------
# PipelineContext
# ---------------------------------------------------------------------------

class PipelineContext(dict):
    """Mutable shared-state bag passed between stages.

    Subclasses dict so existing plain-dict consumers continue to work unchanged.
    Properties are read-only views of well-known keys.
    """

    @property
    def ground_truth(self) -> Optional[Dict]:
        return self.get("ground_truth")

    @property
    def moe_result(self):
        return self.get("moe_result")

    @property
    def scrum_master_result(self):
        return self.get("scrum_master_result")

    @property
    def errors(self) -> List[str]:
        return self.setdefault("errors", [])

    @property
    def stage_outputs(self) -> Dict[str, str]:
        return self.setdefault("stage_outputs", {})

    @property
    def stage_timings(self) -> Dict[str, Dict]:
        """Per-stage wall-clock timing: {stage_name: {wall_s, status, model}}"""
        return self.setdefault("stage_timings", {})

    @property
    def model_fallbacks(self) -> List[Dict]:
        return self.setdefault("model_fallbacks", [])

    def to_skill_output(self) -> Dict:
        """Trimmed JSON-serialisable dict for skill/MCP consumers.

        Stable contract — no internal state, no file paths.
        Includes ScrumMaster results when available.
        """
        gt = self.get("ground_truth") or {}
        sm = self.get("scrum_master_result")
        return {
            "architecture": gt.get("architecture"),
            "confidence": self.get("confidence", 0),
            "expected_risk_score": gt.get("expected_risk_score"),
            "attack_path_count": len(gt.get("expected_attack_paths", [])),
            "controls_missing": gt.get("controls_missing", []),
            "action_plan": sm.action_plan if sm else None,
            "final_confidence": sm.final_confidence if sm else self.get("confidence"),
            "redesign_signal": sm.redesign_signal if sm else None,
            "baseline_feedback": (
                {
                    "weak_controls": sm.baseline_feedback.weak_controls,
                    "pattern_gaps": sm.baseline_feedback.pattern_gaps,
                    "rapids_weight_hints": sm.baseline_feedback.rapids_weight_hints,
                    "ground_truth_gaps": sm.baseline_feedback.ground_truth_gaps,
                }
                if sm and sm.baseline_feedback else None
            ),
            "errors": self.get("errors", []),
            "model_fallbacks": self.get("model_fallbacks", []),
            "model_fallback_warning": len(self.get("model_fallbacks", [])) > 0,
        }


# ---------------------------------------------------------------------------
# Executor protocol — swap to migrate a stage without touching harness logic
# ---------------------------------------------------------------------------

class StageExecutor:
    """Base executor protocol. Mirrors CrewAI Task executor contract."""

    def execute(self, fn: Callable, ctx: PipelineContext, **kwargs) -> Any:
        raise NotImplementedError


class SyncExecutor(StageExecutor):
    """Default: calls fn(ctx) directly in the current thread."""

    def execute(self, fn: Callable, ctx: PipelineContext, **kwargs) -> Any:
        return fn(ctx, **kwargs)


class AgentExecutor(StageExecutor):
    """Stub for future LLM-agent migration.

    When ready: serialise ctx → JSON, invoke via agentic/llm_client.py,
    merge structured output back into ctx. Zero harness changes needed.
    """

    def __init__(self, agent_model: str, agent_prompt_template: str):
        self.agent_model = agent_model
        self.agent_prompt_template = agent_prompt_template

    def execute(self, fn: Callable, ctx: PipelineContext, **kwargs) -> Any:
        raise NotImplementedError(
            "AgentExecutor is a stub — not yet wired. "
            "Implement agentic/llm_client.py integration when migrating this stage."
        )


# ---------------------------------------------------------------------------
# ModelRouter — primary → fallback chain (mirrors LiteLLM pattern, no dep)
# ---------------------------------------------------------------------------

class ModelChainExhaustedError(RuntimeError):
    """All models in a fallback chain have been tried and failed."""

    def __init__(self, agent_name: str, chain: List[str]):
        self.agent_name = agent_name
        self.chain = chain
        super().__init__(
            f"Model chain exhausted for agent '{agent_name}'. "
            f"Tried: {chain}. Add fallbacks in settings.agent_models.{agent_name}.fallbacks."
        )


class ModelRouter:
    """Selects a model from a fallback chain by attempt index.

    Uses llm_client.py as the underlying provider — no new packages needed.
    Future: swap implementation to LiteLLMRouter without changing the interface.

    Empty primary string means "no per-agent config" — get_model() returns None
    so callers fall through to the env-var LLM_PROVIDER default (backward-compat).
    """

    def __init__(
        self,
        primary: str,
        fallbacks: Optional[List[str]] = None,
        agent_name: str = "",
    ):
        self.primary = primary
        self.fallbacks = fallbacks or []
        self.agent_name = agent_name
        self._fallback_events: List[Dict] = []

    @classmethod
    def from_config(cls, config: "AgentModelConfig", agent_name: str) -> "ModelRouter":
        return cls(
            primary=config.model,
            fallbacks=list(config.fallbacks),
            agent_name=agent_name,
        )

    def get_model(self, attempt: int = 0) -> Optional[str]:
        """Return the model string for this attempt.

        Returns None when primary is '' (env-var fallback — backward compat).
        Raises ModelChainExhaustedError when attempt exceeds the full chain.
        """
        if not self.primary:
            return None

        chain = [self.primary] + self.fallbacks
        if attempt >= len(chain):
            raise ModelChainExhaustedError(self.agent_name, chain)

        model = chain[attempt]
        if attempt > 0:
            event = {
                "agent": self.agent_name,
                "attempt": attempt,
                "model": model,
                "primary": self.primary,
            }
            self._fallback_events.append(event)
            _log.warning(
                f"ModelRouter: fallback triggered for '{self.agent_name}' "
                f"(attempt {attempt}) → {model}"
            )
        return model

    def drain_events(self) -> List[Dict]:
        """Return and clear all fallback events accumulated since last call."""
        events, self._fallback_events = list(self._fallback_events), []
        return events


# ---------------------------------------------------------------------------
# CircuitBreaker (v2) — wraps ModelRouter, opens after N consecutive failures
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Wraps a ModelRouter and opens the circuit after consecutive failures.

    When open, get_model() raises BlockedPipelineError immediately rather than
    trying models that are known to be unavailable, preventing cascading retries.
    The circuit resets after RESET_SECONDS.

    Usage: opt-in only — existing callers that instantiate ModelRouter directly
    are unaffected. HarnessModelGuardian can wrap routers on creation.
    """

    THRESHOLD      = 3     # consecutive failures before opening
    RESET_SECONDS  = 60

    def __init__(self, router: "ModelRouter"):
        self._router       = router
        self._failures     = 0
        self._opened_at: Optional[float] = None

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self.RESET_SECONDS:
            # Auto-reset after timeout — try again
            self._failures   = 0
            self._opened_at  = None
            return False
        return True

    def get_model(self, attempt: int = 0) -> Optional[str]:
        if self._is_open():
            raise BlockedPipelineError(
                f"circuit_open:{self._router.agent_name}",
                PipelineContext({}),
            )
        try:
            model = self._router.get_model(attempt)
            self._failures = 0   # success resets counter
            return model
        except ModelChainExhaustedError:
            self._failures += 1
            if self._failures >= self.THRESHOLD:
                self._opened_at = time.monotonic()
                _log.error(
                    f"CircuitBreaker: opened for '{self._router.agent_name}' "
                    f"after {self._failures} consecutive failures"
                )
            raise

    def drain_events(self) -> List[Dict]:
        return self._router.drain_events()


# ---------------------------------------------------------------------------
# HarnessModelGuardian — owns one ModelRouter per agent; single source of truth
# ---------------------------------------------------------------------------

_SWARM_AGENT_NAMES = [
    "architect", "tester", "red_team", "purple_team",
    "blackhat", "storycaster", "scrum_master",
    "moe_orchestrator", "threat_analyst",
    "ta_wiz",
]


class HarnessModelGuardian:
    """Central guardian for per-agent model routing in ThreatAssessor.

    Constructed once per pipeline run and stored in ctx["_model_guardian"].
    All stages and agents pull their model through this object — no direct
    env-var reads for model selection in stage logic.

    Usage:
        guardian = HarnessModelGuardian()
        model = guardian.get_model("architect")         # None → env-var default
        model = guardian.get_model("architect", attempt=1)  # first fallback

    Fallback events are accumulated and drained into ctx["model_fallbacks"]
    after each stage by ThreatAssessorHarness.run().
    """

    def __init__(self, swarm_config: Optional["AgentSwarmConfig"] = None):
        if swarm_config is None:
            try:
                from chatbot.config.settings import get_settings
                swarm_config = get_settings().agent_models
            except Exception:
                from chatbot.config.settings import AgentSwarmConfig
                swarm_config = AgentSwarmConfig()

        self._routers: Dict[str, ModelRouter] = {}
        for name in _SWARM_AGENT_NAMES:
            cfg = getattr(swarm_config, name, None)
            if cfg is None:
                from chatbot.config.settings import AgentModelConfig
                cfg = AgentModelConfig()
            self._routers[name] = ModelRouter.from_config(cfg, agent_name=name)

    def get_model(self, agent_name: str, attempt: int = 0) -> Optional[str]:
        """Return the configured model for an agent at a given attempt index.

        Returns None if no per-agent config exists (env-var default applies).
        Raises ModelChainExhaustedError if the attempt exceeds the chain length.
        """
        router = self._routers.get(agent_name)
        return router.get_model(attempt) if router else None

    def models_dict(self, agent_names: Optional[List[str]] = None) -> Dict[str, str]:
        """Return a {name: model} dict for the given agents (or all), skipping None entries."""
        names = agent_names or _SWARM_AGENT_NAMES
        result = {}
        for name in names:
            m = self.get_model(name)
            if m:
                result[name] = m
        return result

    def resolve(self, agent_name: str, quality: str = "default") -> Optional[str]:
        """Return the fully-resolved model string for an agent.

        Resolution order:
          1. AgentSwarmConfig.{agent_name}.model (settings.yaml / user_config override),
             skipped if the string is an unresolved ${VAR} placeholder.
          2. PROVIDER_MODELS[primary_provider][quality] from llm_client.py.
          3. None — LLMClient picks its own default.

        This is the sole model resolution point for all components.
        """
        from agentic.llm_client import PROVIDER_MODELS, LLMProvider
        from agentic.helper import get_llm_provider

        router = self._routers.get(agent_name)
        if router:
            m = router.get_model(0)
            if m and not m.startswith("${"):
                return m

        try:
            provider = LLMProvider(get_llm_provider())
            return PROVIDER_MODELS.get(provider, {}).get(quality)
        except Exception:
            return None

    def drain_fallback_events(self) -> List[Dict]:
        """Collect and clear fallback events from all routers since last call."""
        events = []
        for router in self._routers.values():
            events.extend(router.drain_events())
        return events


# ---------------------------------------------------------------------------
# PipelineStage — isolation chamber
# ---------------------------------------------------------------------------

class PipelineStage:
    """Base pipeline stage.

    Each stage runs in isolation — exceptions caught by the harness and recorded
    in ctx.errors; only stages with required=True halt the pipeline on failure.

    Swap .executor to change execution mode (sync → agent) without harness changes.
    Swap .model_router to change the model chain without touching stage logic.
    """

    name: str = ""
    required: bool = True
    executor: StageExecutor = SyncExecutor()
    model_router: Optional[ModelRouter] = None
    max_retries: int = 1
    retry_delay: float = 0.5   # seconds; doubles on each retry

    def run(
        self,
        ctx: PipelineContext,
        progress_callback: Optional[Callable] = None,
    ) -> PipelineContext:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                if self.model_router:
                    ctx[f"_{self.name}_model"] = self.model_router.get_model(attempt)
                return self.executor.execute(
                    self._logic, ctx, progress_callback=progress_callback
                )
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
        assert last_exc is not None
        raise last_exc

    def _logic(self, ctx: PipelineContext, **kwargs) -> PipelineContext:
        raise NotImplementedError(f"{self.__class__.__name__}._logic not implemented")


# ---------------------------------------------------------------------------
# ThreatAssessorHarness
# ---------------------------------------------------------------------------

class ThreatAssessorHarness:
    """Master controller gateway.

    - Routes to stage configurations per scenario via ScenarioRegistry
    - Isolates optional stage failures (caught, logged, pipeline continues)
    - Required stage failure halts the pipeline and propagates the exception
    - Exposes model fallback via ModelRouter on each stage
    - Single callable surface for: streaming API, MCP gateway, backtest loops

    Extension points:
        New scenario:      add @register_scenario("name") factory function
        New enricher:      harness.stages.insert(-1, MyEnricherStage())
        New critic:        extend CriticStage or add standalone PipelineStage
        Agent migration:   stage.executor = AgentExecutor(model, prompt)
        Model fallback:    stage.model_router = ModelRouter("sonnet", ["haiku"])
    """

    def __init__(
        self,
        stages: Optional[List[PipelineStage]] = None,
        model: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        scenario: Optional[str] = None,
    ):
        self.model = model
        self.progress_callback = progress_callback
        self.scenario = scenario or ScenarioConfig.API_ONLY
        if self.scenario not in _SCENARIO_REGISTRY:
            raise ValueError(
                f"Unknown scenario '{self.scenario}'. "
                f"Available: {list(_SCENARIO_REGISTRY.keys())}"
            )
        self.stages: List[PipelineStage] = stages or _SCENARIO_REGISTRY[self.scenario]()

    def run(
        self,
        architecture_path: str,
        report_dir: str,
        use_llm: bool = False,
        ssp_profile: str = "low_risk_cloud",
        enable_ssp: bool = True,
        enable_moe: bool = False,
        enable_scrum_master: bool = False,
        critic_mode: str = "partial_parallel",
        run_blackhat: Optional[bool] = None,
        **kwargs,
    ) -> PipelineContext:
        """Execute the pipeline. Returns a PipelineContext with all stage results.

        Optional stages are dynamically appended when their enable_* flag is set
        and they are not already present in the scenario's stage list.
        """
        ctx = PipelineContext({
            "architecture_path": architecture_path,
            "report_dir": report_dir,
            "use_llm": use_llm,
            "ssp_profile": ssp_profile,
            "enable_ssp": enable_ssp,
            "enable_moe": enable_moe,
            "enable_scrum_master": enable_scrum_master,
            "critic_mode": critic_mode,
            "run_blackhat": run_blackhat,
        })
        # Forward any extra kwargs into ctx (e.g. architecture_name, include_validation)
        ctx.update(kwargs)

        # Instantiate the model guardian — single owner of all per-agent ModelRouters
        guardian = HarnessModelGuardian()
        ctx["_model_guardian"] = guardian
        ctx.setdefault("model_fallbacks", [])

        # Inject governance adapter so QualityStage reuses the same instance
        try:
            from chatbot.harness.governance import get_governance_adapter
            ctx["_governance_adapter"] = get_governance_adapter()
        except ImportError:
            pass

        # Inject run metadata consumed by OutboundAIVSSGate + SIEM
        import datetime as _dt
        ctx["_run_ts"] = _dt.datetime.utcnow().isoformat() + "Z"
        ctx["_run_id"] = f"{ctx.get('architecture_name', 'run')}_{ctx['_run_ts'][:19].replace(':', '-')}"

        # Instantiate EventBroker (no-op if disabled or package absent)
        try:
            from chatbot.harness.event_broker import EventBrokerCritic, HarnessEvent as _HE
            _broker = EventBrokerCritic()
            if _broker._enabled:
                ctx["_event_broker"] = _broker
                _broker.emit(_HE(
                    event_type="run_start",
                    source="harness",
                    run_id=ctx["_run_id"],
                    ts=ctx["_run_ts"],
                    payload={
                        "scenario": self.scenario,
                        "architecture": ctx.get("architecture_name", ""),
                    },
                ))
        except Exception:
            pass

        import time as _time

        stages = list(self.stages)

        if enable_moe and not any(s.name == "critics" for s in stages):
            from chatbot.harness.stages import CriticStage
            stages.append(CriticStage())

        if enable_scrum_master and not any(s.name == "scrum_master" for s in stages):
            from chatbot.harness.stages import ScrumMasterStage
            stages.append(ScrumMasterStage())

        _pipeline_start = _time.perf_counter()

        for stage in stages:
            _stage_start = _time.perf_counter()
            _status = "ok"
            try:
                stage.run(ctx, progress_callback=self.progress_callback)
                ctx.stage_outputs[stage.name] = "ok"

                # ── PolicyBroker: dynamic routing after QualityStage ─────────
                # Runs immediately after quality checks complete so live signals
                # (governance_signals populated by QualityStage) inform routing
                # before CriticStage runs. Non-fatal — routing failure keeps
                # existing blocked_agents unchanged.
                if stage.name == "quality":
                    try:
                        from chatbot.harness.policy_broker import PolicyBroker
                        broker   = PolicyBroker()
                        decision = broker.decide(
                            ctx.get("governance_signals", {}),
                            ctx.get("_aivss_score"),
                        )
                        # Merge: add broker-decided blocks to existing list
                        existing = set(ctx.get("blocked_agents", []))
                        existing.update(decision.blocked_agents)
                        ctx["blocked_agents"] = list(existing)
                        ctx["_broker_decision"] = decision
                        # Apply model overrides to guardian
                        guardian = ctx.get("_model_guardian")
                        if guardian and decision.model_overrides:
                            for agent, model in decision.model_overrides.items():
                                if hasattr(guardian, "_routers") and agent in guardian._routers:
                                    from chatbot.harness.controller import ModelRouter
                                    guardian._routers[agent] = ModelRouter(
                                        model, [], agent_name=agent
                                    )
                        if decision.rationale and decision.rationale != "no policy match":
                            _log.info(f"PolicyBroker: {decision.rationale}")
                    except BlockedPipelineError:
                        raise  # BouncerStage may raise this — let it propagate
                    except Exception as _pb_exc:
                        _log.debug(f"PolicyBroker skipped (non-fatal): {_pb_exc}")

            except BlockedPipelineError:
                raise  # always propagate — bouncer decisions are intentional
            except Exception as exc:
                _status = "error"
                ctx.errors.append(f"{stage.name}: {exc}")
                ctx.stage_outputs[stage.name] = "error"
                if stage.required:
                    raise
            finally:
                _wall = round(_time.perf_counter() - _stage_start, 2)
                # Map stage name to agent name for model lookup
                _STAGE_TO_AGENT = {
                    "critics": None,       # multiple agents — per-critic model shown elsewhere
                    "scrum_master": "scrum_master",
                    "aivss": None,
                    "quality": None,
                    "analysis": "threat_analyst",
                    "report": None,
                    "outbound_aivss": None,
                }
                _agent = _STAGE_TO_AGENT.get(stage.name)
                try:
                    _model = guardian.get_model(_agent, 0) if _agent else None
                except Exception:
                    _model = None
                ctx.stage_timings[stage.name] = {
                    "wall_s": _wall,
                    "status": _status,
                    "model": _model,
                }
                events = guardian.drain_fallback_events()
                if events:
                    ctx.model_fallbacks.extend(events)

        _pipeline_wall = round(_time.perf_counter() - _pipeline_start, 2)

        # Save harness_perf.json alongside other report artefacts
        if ctx.get("report_dir"):
            try:
                import json as _json
                from pathlib import Path as _Path
                _perf = {
                    "run_id":          ctx.get("_run_id", ""),
                    "run_ts":          ctx.get("_run_ts", ""),
                    "scenario":        self.scenario,
                    "pipeline_wall_s": _pipeline_wall,
                    "stages":          ctx.stage_timings,
                }
                (_Path(ctx["report_dir"]) / "harness_perf.json").write_text(
                    _json.dumps(_perf, indent=2), encoding="utf-8"
                )
            except Exception:
                pass

        if ctx.model_fallbacks:
            agents_with_fallbacks = list({e["agent"] for e in ctx.model_fallbacks})
            _log.warning(
                f"Pipeline completed with {len(ctx.model_fallbacks)} model fallback(s) "
                f"— agents affected: {agents_with_fallbacks}"
            )
            ctx.errors.append(
                f"model_fallback_warning: {len(ctx.model_fallbacks)} fallback(s) used "
                f"for agents: {agents_with_fallbacks}"
            )

        # Emit run_complete and flush broker (LangfuseSink sends buffered spans)
        _broker = ctx.get("_event_broker")
        if _broker is not None:
            try:
                from chatbot.harness.event_broker import HarnessEvent as _HE2
                import datetime as _dt2
                _broker.emit(_HE2(
                    event_type="run_complete",
                    source="harness",
                    run_id=ctx.get("_run_id", ""),
                    ts=_dt2.datetime.utcnow().isoformat() + "Z",
                    payload={
                        "confidence": ctx.get("confidence"),
                        "errors": ctx.errors,
                        "pipeline_wall_s": _pipeline_wall,
                    },
                ))
                _broker.flush()
            except Exception:
                pass

        return ctx

    # ------------------------------------------------------------------
    # Typed interface (v2) — run_typed wraps run() with PipelineRequest/
    # PipelineResponse so MCP tools and async callers get a clean contract.
    # Old callers using run(**kwargs) are completely unaffected.
    # ------------------------------------------------------------------

    def run_typed(
        self,
        request: PipelineRequest,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> PipelineResponse:
        """Execute the pipeline from a PipelineRequest, return a PipelineResponse.

        Raises BlockedPipelineError if BouncerStage halts the pipeline.
        All other exceptions propagate normally (caller decides 500 vs retry).
        """
        if progress_callback:
            self.progress_callback = progress_callback

        ctx = self.run(
            architecture_path   = request.architecture_path,
            report_dir          = request.report_dir,
            use_llm             = request.use_llm,
            ssp_profile         = request.ssp_profile,
            enable_ssp          = request.enable_ssp,
            enable_moe          = request.enable_moe,
            enable_scrum_master = request.enable_scrum_master,
            critic_mode         = request.critic_mode,
            run_blackhat        = request.run_blackhat,
            architecture_name   = request.architecture_name or "",
            **(request.metadata or {}),
        )

        # Build governance summary
        gov = ctx.get("governance_signals", {})
        aivss = gov.get("aivss", {}).get("overall", {})
        gov_summary = {
            "overall_risk_level": gov.get("overall_risk_level", "LOW"),
            "aivss_overall":      aivss.get("composite"),
            "aivss_severity":     aivss.get("severity"),
        }

        # Build detect summary from ocsf_findings if available
        detect_summary: dict = {"rules_fired": [], "total_fired": 0}
        try:
            import json as _json
            from pathlib import Path as _Path
            _ocsf = _Path(request.report_dir) / "ocsf_findings.json"
            if _ocsf.exists():
                findings = _json.loads(_ocsf.read_text(encoding="utf-8"))
                fired = [
                    f["unmapped"]["rule_id"]
                    for f in findings
                    if f.get("class_uid") == 2004 and f.get("unmapped", {}).get("rule_id")
                ]
                detect_summary = {"rules_fired": fired, "total_fired": len(fired)}
        except Exception:
            pass

        # Extract confidence
        confidence: Optional[float] = None
        gt = ctx.get("ground_truth", {})
        if gt:
            cb = gt.get("confidence_breakdown", {})
            confidence = cb.get("final") or gt.get("expected_risk_score")

        return PipelineResponse(
            success           = not ctx.errors,
            run_id            = ctx.get("_run_id", ""),
            architecture_name = ctx.get("architecture_name", ""),
            confidence        = confidence,
            errors            = list(ctx.errors),
            stage_timings     = dict(ctx.stage_timings),
            governance_summary = gov_summary,
            detect_summary    = detect_summary,
            ctx               = ctx,
        )


# ---------------------------------------------------------------------------
# AsyncThreatAssessorHarness (v2)
# ---------------------------------------------------------------------------

class AsyncThreatAssessorHarness:
    """Async wrapper around ThreatAssessorHarness for MCP tools and CI/CD jobs.

    Runs the synchronous harness in a thread via asyncio.to_thread() so the
    calling event loop is not blocked during the ~30s analysis.

    Usage:
        harness = AsyncThreatAssessorHarness(scenario=ScenarioConfig.API_ONLY)
        response = await harness.run(request, progress_callback=cb)
    """

    def __init__(
        self,
        scenario: str = ScenarioConfig.API_ONLY,
        model: Optional[str] = None,
    ):
        self.scenario = scenario
        self.model    = model

    async def run(
        self,
        request: PipelineRequest,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> PipelineResponse:
        """Run analysis in a thread; return PipelineResponse.

        Raises BlockedPipelineError if BouncerStage halts — callers should
        catch this and return a structured error to the client.
        """
        harness = ThreatAssessorHarness(
            scenario = self.scenario,
            model    = self.model,
        )
        return await asyncio.to_thread(
            harness.run_typed, request, progress_callback
        )


# ---------------------------------------------------------------------------
# Scenario registrations (lazy-import stages to avoid circular imports)
# ---------------------------------------------------------------------------

@register_scenario(ScenarioConfig.QUICK_DET)
def _quick_det() -> List[PipelineStage]:
    from chatbot.harness.stages import AnalysisStage
    return [AnalysisStage()]


@register_scenario(ScenarioConfig.API_ONLY)
def _api_only() -> List[PipelineStage]:
    from chatbot.harness.stages import (
        AnalysisStage, ReportStage, QualityStage, BouncerStage, AIVSSStage,
    )
    # BouncerStage after QualityStage: reads exploitation.blocked + kill_switch.
    # required=False (v2 phase 1) — non-fatal until callers handle BlockedPipelineError.
    return [AnalysisStage(), ReportStage(), QualityStage(), BouncerStage(), AIVSSStage()]


@register_scenario(ScenarioConfig.FULL_MOE)
def _full_moe() -> List[PipelineStage]:
    from chatbot.harness.stages import (
        AnalysisStage, ReportStage, QualityStage, BouncerStage,
        CriticStage, ScrumMasterStage, AIVSSStage, OutboundAIVSSGate,
    )
    # BouncerStage between QualityStage and CriticStage: blocks adversarial
    # inputs before any LLM call is made.
    return [
        AnalysisStage(), ReportStage(), QualityStage(), BouncerStage(),
        CriticStage(), ScrumMasterStage(), AIVSSStage(), OutboundAIVSSGate(),
    ]


@register_scenario(ScenarioConfig.BACKTEST)
def _backtest() -> List[PipelineStage]:
    from chatbot.harness.stages import AnalysisStage
    return [AnalysisStage()]
