# Shim — canonical source is chatbot/harness/controller.py
from chatbot.harness.controller import *  # noqa: F401,F403
from chatbot.harness.controller import (
    ThreatAssessorHarness,
    PipelineContext,
    PipelineStage,
    ScenarioConfig,
    ModelRouter,
    SyncExecutor,
    AgentExecutor,
    StageExecutor,
    register_scenario,
)
