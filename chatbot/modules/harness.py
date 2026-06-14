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

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass


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

class ModelRouter:
    """Selects a model from a fallback chain by attempt index.

    Uses llm_client.py as the underlying provider — no new packages needed.
    Future: swap implementation to LiteLLMRouter without changing the interface.
    """

    def __init__(self, primary: str, fallbacks: Optional[List[str]] = None):
        self.primary = primary
        self.fallbacks = fallbacks or []

    def get_model(self, attempt: int = 0) -> str:
        chain = [self.primary] + self.fallbacks
        return chain[min(attempt, len(chain) - 1)]


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

        stages = list(self.stages)

        if enable_moe and not any(s.name == "critics" for s in stages):
            from chatbot.modules.harness_stages import CriticStage
            stages.append(CriticStage())

        if enable_scrum_master and not any(s.name == "scrum_master" for s in stages):
            from chatbot.modules.harness_stages import ScrumMasterStage
            stages.append(ScrumMasterStage())

        for stage in stages:
            try:
                stage.run(ctx, progress_callback=self.progress_callback)
                ctx.stage_outputs[stage.name] = "ok"
            except Exception as exc:
                ctx.errors.append(f"{stage.name}: {exc}")
                ctx.stage_outputs[stage.name] = "error"
                if stage.required:
                    raise
                # optional stage failure: logged, pipeline continues

        return ctx


# ---------------------------------------------------------------------------
# Scenario registrations (lazy-import stages to avoid circular imports)
# ---------------------------------------------------------------------------

@register_scenario(ScenarioConfig.QUICK_DET)
def _quick_det() -> List[PipelineStage]:
    from chatbot.modules.harness_stages import AnalysisStage
    return [AnalysisStage()]


@register_scenario(ScenarioConfig.API_ONLY)
def _api_only() -> List[PipelineStage]:
    from chatbot.modules.harness_stages import AnalysisStage, ReportStage
    return [AnalysisStage(), ReportStage()]


@register_scenario(ScenarioConfig.FULL_MOE)
def _full_moe() -> List[PipelineStage]:
    from chatbot.modules.harness_stages import (
        AnalysisStage, ReportStage, CriticStage, ScrumMasterStage,
    )
    return [AnalysisStage(), ReportStage(), CriticStage(), ScrumMasterStage()]


@register_scenario(ScenarioConfig.BACKTEST)
def _backtest() -> List[PipelineStage]:
    from chatbot.modules.harness_stages import AnalysisStage
    return [AnalysisStage()]
