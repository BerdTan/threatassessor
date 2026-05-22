"""
Validation Service (Team 2+3: Critic Engine + Orchestration)

Wraps MoE validation and orchestration as a service.

Capabilities:
Team 2 (Critics):
- Architect validation (threat model completeness)
- Tester validation (MITRE mappings consistency)
- Red Team validation (control effectiveness)

Team 3 (Orchestration):
- Sequential validation with fail-fast
- Confidence synthesis
- Executive summary generation

Thread-safe, request-isolated implementation.

Version: 1.0 (Stage 2, Phase 2A)
"""

import logging
from typing import Dict, Optional, List
from pathlib import Path

from chatbot.services.base_service import (
    BaseService,
    ServiceContext,
    ServiceResult,
    ValidationError,
    ProcessingError
)

logger = logging.getLogger(__name__)


class ValidationService(BaseService):
    """
    Service wrapper for MoE validation + orchestration.

    Maps to:
    - Team 2: Critic Engine (Architect, Tester, Red Team)
    - Team 3: Orchestration Engine (Consensus synthesis)
    """

    def __init__(self):
        super().__init__(name="Validation")

        # Lazy load critics
        self._critics_loaded = False
        self._architect = None
        self._tester = None
        self._red_teamer = None
        self._orchestrator = None

    def _load_critics(self):
        """Lazy load critic agents."""
        if not self._critics_loaded:
            with self._lock:
                if not self._critics_loaded:
                    from chatbot.modules.agents.critics import (
                        EnhancedArchitectCritic,
                        TesterCritic,
                        RedTeamerCritic
                    )
                    from chatbot.modules.agents.orchestrators.moe_orchestrator import (
                        MoEOrchestrator
                    )

                    self._architect = EnhancedArchitectCritic()
                    self._tester = TesterCritic()
                    self._red_teamer = RedTeamerCritic()
                    self._orchestrator = MoEOrchestrator(
                        architect_critic=self._architect,
                        tester_critic=self._tester,
                        red_teamer_critic=self._red_teamer
                    )

                    self._critics_loaded = True
                    self.logger.info("Critics and orchestrator loaded")

    def _validate_input(
        self,
        ground_truth_path: Optional[str] = None,
        ground_truth_data: Optional[Dict] = None,
        **kwargs
    ) -> None:
        """
        Validate inputs for MoE validation.

        Requires one of:
        - ground_truth_path: Path to ground_truth.json
        - ground_truth_data: Ground truth dict

        Raises:
            ValidationError: If validation fails
        """
        if not any([ground_truth_path, ground_truth_data]):
            raise ValidationError(
                "Must provide one of: ground_truth_path, ground_truth_data",
                details={"provided_keys": list(kwargs.keys())}
            )

        if ground_truth_path:
            path = Path(ground_truth_path)
            if not path.exists():
                raise ValidationError(
                    f"Ground truth file not found: {ground_truth_path}",
                    details={"path": ground_truth_path}
                )

    def execute(
        self,
        context: ServiceContext,
        ground_truth_path: Optional[str] = None,
        ground_truth_data: Optional[Dict] = None,
        enable_fail_fast: bool = True,
        critic_subset: Optional[List[str]] = None,
        **kwargs
    ) -> ServiceResult:
        """
        Execute MoE validation (Team 2) + orchestration (Team 3).

        Args:
            context: Isolated request context
            ground_truth_path: Path to ground_truth.json
            ground_truth_data: Ground truth dict
            enable_fail_fast: Stop on first failing critic (default: True)
            critic_subset: Optional list of critics to run ["architect", "tester", "red_teamer"]
            **kwargs: Additional options

        Returns:
            ServiceResult with validation results + consensus
        """
        try:
            # Load ground truth
            if ground_truth_path:
                import json
                with open(ground_truth_path, 'r') as f:
                    ground_truth = json.load(f)
                arch_name = Path(ground_truth_path).parent.name
            else:
                ground_truth = ground_truth_data
                arch_name = ground_truth.get("architecture", "unknown")

            self._log_request(
                context, "validate",
                architecture_name=arch_name,
                fail_fast=enable_fail_fast,
                critic_subset=critic_subset
            )

            # Load critics
            self._load_critics()

            # Run orchestration
            orchestrator_context = {
                "ground_truth_path": ground_truth_path,
                "ground_truth": ground_truth,
                "enable_fail_fast": enable_fail_fast
            }

            moe_result = self._orchestrator.execute(orchestrator_context)

            # Convert to dict
            result_data = {
                "architecture_name": arch_name,
                "validation_results": [
                    {
                        "critic": v.critic_name,
                        "passed": v.passed,
                        "confidence_delta": v.confidence_delta,
                        "summary": v.summary,
                        "issues_found": len(v.issues)
                    }
                    for v in moe_result.validation_results
                ],
                "consensus": {
                    "final_confidence": moe_result.final_confidence,
                    "initial_confidence": moe_result.initial_confidence,
                    "total_adjustments": moe_result.final_confidence - moe_result.initial_confidence,
                    "all_passed": moe_result.all_critics_passed
                },
                "synthesis": moe_result.synthesis
            }

            # Store in context
            context.results["validation"] = result_data
            context.metadata["architecture_name"] = arch_name

            return ServiceResult(
                success=True,
                data=result_data
            )

        except ValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            raise ProcessingError(
                f"Validation failed: {str(e)}",
                details={"architecture_name": arch_name if 'arch_name' in locals() else "unknown"}
            )

    def run_single_critic(
        self,
        context: ServiceContext,
        critic_name: str,
        ground_truth_path: Optional[str] = None,
        ground_truth_data: Optional[Dict] = None,
        **kwargs
    ) -> ServiceResult:
        """
        Run a single critic (for debugging/testing).

        Args:
            context: Isolated request context
            critic_name: One of: "architect", "tester", "red_teamer"
            ground_truth_path: Path to ground_truth.json
            ground_truth_data: Ground truth dict

        Returns:
            ServiceResult with single critic result
        """
        try:
            # Validate critic name
            valid_critics = ["architect", "tester", "red_teamer"]
            if critic_name not in valid_critics:
                raise ValidationError(
                    f"Invalid critic name: {critic_name}",
                    details={"valid_critics": valid_critics}
                )

            # Load ground truth
            if ground_truth_path:
                import json
                with open(ground_truth_path, 'r') as f:
                    ground_truth = json.load(f)
            else:
                ground_truth = ground_truth_data

            # Load critics
            self._load_critics()

            # Select critic
            critic_map = {
                "architect": self._architect,
                "tester": self._tester,
                "red_teamer": self._red_teamer
            }
            critic = critic_map[critic_name]

            # Execute
            critic_context = {"ground_truth": ground_truth}
            result = critic.execute(critic_context)

            return ServiceResult(
                success=True,
                data={
                    "critic": critic_name,
                    "score": result.score,
                    "confidence_delta": result.confidence_delta,
                    "issues": result.issues,
                    "recommendations": result.recommendations
                }
            )

        except ValidationError:
            raise
        except Exception as e:
            raise ProcessingError(f"Critic execution failed: {str(e)}")


__all__ = ['ValidationService']
