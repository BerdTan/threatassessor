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

import logging
import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.config.settings import AgentModelConfig, AgentSwarmConfig

_log = logging.getLogger(__name__)


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
        critic_mode: str = "sequential",
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


# ---------------------------------------------------------------------------
# Scenario registrations (lazy-import stages to avoid circular imports)
# ---------------------------------------------------------------------------

@register_scenario(ScenarioConfig.QUICK_DET)
def _quick_det() -> List[PipelineStage]:
    from chatbot.harness.stages import AnalysisStage
    return [AnalysisStage()]


@register_scenario(ScenarioConfig.API_ONLY)
def _api_only() -> List[PipelineStage]:
    from chatbot.harness.stages import AnalysisStage, ReportStage, QualityStage, AIVSSStage
    # AIVSSStage runs after QualityStage; no critics/SM so internal flow scores
    # with governance signals only (moe_result=None, sm_result=None).
    return [AnalysisStage(), ReportStage(), QualityStage(), AIVSSStage()]


@register_scenario(ScenarioConfig.FULL_MOE)
def _full_moe() -> List[PipelineStage]:
    from chatbot.harness.stages import (
        AnalysisStage, ReportStage, QualityStage, CriticStage, ScrumMasterStage,
        AIVSSStage, OutboundAIVSSGate,
    )
    # AIVSSStage runs after ScrumMasterStage so moe_result + scrum_master_result
    # are available for internal flow (manipulation, drift signals).
    return [
        AnalysisStage(), ReportStage(), QualityStage(),
        CriticStage(), ScrumMasterStage(), AIVSSStage(), OutboundAIVSSGate(),
    ]


@register_scenario(ScenarioConfig.BACKTEST)
def _backtest() -> List[PipelineStage]:
    from chatbot.harness.stages import AnalysisStage
    return [AnalysisStage()]
