"""
chatbot.harness — pipeline controller, stages, governance, and registry.

Public surface (mirrors chatbot.modules.harness* shims for backwards compat):
    from chatbot.harness import ThreatAssessorHarness, PipelineContext, ScenarioConfig
    from chatbot.harness.governance import GovernanceSignals, get_governance_adapter
    from chatbot.harness.registry import CriticRegistry, _DEFAULT_REGISTRY
"""

from chatbot.harness.controller import (
    ThreatAssessorHarness,
    PipelineContext,
    PipelineStage,
    ScenarioConfig,
    ModelRouter,
    ModelChainExhaustedError,
    HarnessModelGuardian,
    SyncExecutor,
    AgentExecutor,
    StageExecutor,
    register_scenario,
)

__all__ = [
    "ThreatAssessorHarness",
    "PipelineContext",
    "PipelineStage",
    "ScenarioConfig",
    "ModelRouter",
    "ModelChainExhaustedError",
    "HarnessModelGuardian",
    "SyncExecutor",
    "AgentExecutor",
    "StageExecutor",
    "register_scenario",
]
