"""
chatbot.harness — pipeline controller, stages, governance, and registry.

Public surface (mirrors chatbot.modules.harness* shims for backwards compat):
    from chatbot.harness import ThreatAssessorHarness, PipelineContext, ScenarioConfig
    from chatbot.harness.governance import GovernanceSignals, get_governance_adapter
    from chatbot.harness.registry import CriticRegistry, _DEFAULT_REGISTRY

v2 additions:
    from chatbot.harness import (
        PipelineRequest, PipelineResponse,   # typed contract
        AsyncThreatAssessorHarness,           # async wrapper
        BlockedPipelineError,                 # bouncer exception
        CircuitBreaker,                       # model router protection
        ProgressCallback,                     # type alias
    )
    from chatbot.harness.policy_broker import PolicyBroker, BrokerDecision
    from chatbot.harness.stages import BouncerStage
"""

from chatbot.harness.controller import (
    ThreatAssessorHarness,
    AsyncThreatAssessorHarness,
    PipelineContext,
    PipelineStage,
    PipelineRequest,
    PipelineResponse,
    BlockedPipelineError,
    CircuitBreaker,
    ProgressCallback,
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
    # Core (unchanged)
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
    # v2 additions
    "AsyncThreatAssessorHarness",
    "PipelineRequest",
    "PipelineResponse",
    "BlockedPipelineError",
    "CircuitBreaker",
    "ProgressCallback",
]
