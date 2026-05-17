"""
Orchestrator Agents - Coordinate & Consensus

Orchestrator agents coordinate multiple agents and synthesize consensus:

1. **MoEOrchestrator** (Phase 3D - Current)
   - Sequential validation: Analyst → Architect → Tester → Red Team → Consensus
   - Fail-fast: Missing prerequisite = abort
   - Confidence adjustments: Base ± expert validations
   - Unified recommendations: Critical (3 agree) > High (2 agree) > Review (1 only)

2. **LegacyOrchestrator** (Phase 3C - Deprecated)
   - Parallel agent execution
   - Composite scoring (conflicting with deterministic)
   - Non-deterministic output (±11 point variance)
   - Kept for backward compatibility only

Usage:
    >>> from chatbot.modules.agents import run_moe_pipeline
    >>> result = run_moe_pipeline("report/architecture_name")
    >>> print(f"Confidence: {result.final_confidence:.1f}%")

Version: 1.0 (Phase 3D)
"""

from chatbot.modules.agents.orchestrators.moe_orchestrator import (
    MoEOrchestrator,
    MoEResult,
    ValidationResult,
    MissingPrerequisiteError,
    run_moe_pipeline
)

__all__ = [
    "MoEOrchestrator",
    "MoEResult",
    "ValidationResult",
    "MissingPrerequisiteError",
    "run_moe_pipeline",
]
