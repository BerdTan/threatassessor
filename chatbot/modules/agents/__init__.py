"""
ThreatAssessor Agent Module (MoE Architecture)

This module contains all agents in the Mixture of Experts (MoE) architecture:

1. **CriticAgents** - Validate analysis quality (LLM-based)
   - Architect: Validates threat model completeness & control design
   - Tester: Validates MITRE mappings & internal consistency
   - Red Teamer: Validates control effectiveness & exploit difficulty

2. **AnalystAgents** - Generate threat assessments (Deterministic)
   - ThreatAnalyst: Wraps deterministic engine (99.5% confidence)
   - PatternRegistry: Manages threat patterns (RAPIDS, AI/ML, Cloud, ICS)

3. **OrchestratorAgents** - Coordinate & synthesize consensus
   - MoEOrchestrator: Sequential validation with fail-fast (Phase 3D)
   - LegacyOrchestrator: Composite scoring (Phase 3C, deprecated)

MoE Pipeline:
    Layer 1: AnalystAgent (ThreatAnalyst)
        └─> ground_truth.json (99.5% base confidence)

    Layer 2: CriticAgents (Sequential validation)
        └─> Architect → Tester → Red Teamer
            (Each validates previous layer, adjusts confidence)

    Layer 3: OrchestratorAgent (MoEOrchestrator)
        └─> Synthesizes consensus, generates unified report

Version: 1.0 (Phase 3D)
Date: 2025-05-17
"""

# Base classes
from chatbot.modules.base_agent import BaseAgent, AgentResult
from chatbot.modules.analyst_agent import AnalystAgent, AnalysisResult
from chatbot.modules.agent_framework import CriticAgent, CritiqueScore

# Critic Agents
from chatbot.modules.agents.critics.architect_critic import EnhancedArchitectCritic
from chatbot.modules.agents.critics.tester_critic import TesterCritic
from chatbot.modules.agents.critics.red_teamer_critic import RedTeamerCritic

# Analyst Agents
from chatbot.modules.agents.analysts.threat_analyst import ThreatAnalyst
from chatbot.modules.agents.analysts.pattern_registry import PatternRegistry

# Orchestrator Agents
from chatbot.modules.agents.orchestrators.moe_orchestrator import (
    MoEOrchestrator,
    MoEResult,
    ValidationResult,
    MissingPrerequisiteError,
    run_moe_pipeline
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentResult",
    "AnalystAgent",
    "AnalysisResult",
    "CriticAgent",
    "CritiqueScore",

    # Critics
    "EnhancedArchitectCritic",
    "TesterCritic",
    "RedTeamerCritic",

    # Analysts
    "ThreatAnalyst",
    "PatternRegistry",

    # Orchestrators
    "MoEOrchestrator",
    "MoEResult",
    "ValidationResult",
    "MissingPrerequisiteError",
    "run_moe_pipeline",
]
