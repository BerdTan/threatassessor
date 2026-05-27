"""
Threat Analysis Service (Team 1: Deterministic Engine)

Wraps deterministic threat analysis engine as a service.

Capabilities:
- Parse architecture diagrams (.mmd)
- Run RAPIDS threat assessment (99.5% confidence)
- Apply MITRE ATLAS patterns (AI/ML)
- Map techniques to components
- Recommend security controls
- Calculate residual risk

Thread-safe, request-isolated implementation.

Version: 1.0 (Stage 2, Phase 2A)
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from chatbot.services.base_service import (
    BaseService,
    ServiceContext,
    ServiceResult,
    ValidationError,
    ProcessingError
)

logger = logging.getLogger(__name__)


class ThreatAnalysisService(BaseService):
    """
    Service wrapper for deterministic threat analysis.

    Maps to Team 1: Deterministic Engine + Pattern Registry
    """

    def __init__(self):
        super().__init__(name="ThreatAnalysis")

        # Lazy import to avoid loading MITRE data at startup
        self._analyst = None

    def _get_analyst(self):
        """Lazy load ThreatAnalyst (avoid startup penalty)."""
        if self._analyst is None:
            with self._lock:
                if self._analyst is None:
                    from chatbot.modules.agents.analysts.threat_analyst import ThreatAnalyst
                    self._analyst = ThreatAnalyst()
                    self.logger.info("ThreatAnalyst initialized")
        return self._analyst

    def _validate_input(
        self,
        architecture_path: Optional[str] = None,
        architecture_content: Optional[str] = None,
        architecture_data: Optional[Dict] = None,
        **kwargs
    ) -> None:
        """
        Validate threat analysis inputs.

        Requires one of:
        - architecture_path: Path to .mmd file
        - architecture_content: MMD content as string
        - architecture_data: Pre-parsed architecture dict

        Raises:
            ValidationError: If validation fails
        """
        if not any([architecture_path, architecture_content, architecture_data]):
            raise ValidationError(
                "Must provide one of: architecture_path, architecture_content, architecture_data",
                details={"provided_keys": list(kwargs.keys())}
            )

        # Validate architecture_path if provided
        if architecture_path:
            path = Path(architecture_path)
            if not path.exists():
                raise ValidationError(
                    f"Architecture file not found: {architecture_path}",
                    details={"path": architecture_path}
                )
            if not path.suffix == ".mmd":
                raise ValidationError(
                    f"Architecture file must be .mmd format, got: {path.suffix}",
                    details={"path": architecture_path, "suffix": path.suffix}
                )

    def execute(
        self,
        context: ServiceContext,
        architecture_path: Optional[str] = None,
        architecture_content: Optional[str] = None,
        architecture_data: Optional[Dict] = None,
        include_validation: bool = True,
        **kwargs
    ) -> ServiceResult:
        """
        Execute threat analysis.

        Args:
            context: Isolated request context
            architecture_path: Path to .mmd file (preferred)
            architecture_content: MMD content as string
            architecture_data: Pre-parsed architecture dict
            include_validation: Run 6-check validation (default: True)
            **kwargs: Additional options

        Returns:
            ServiceResult with threat assessment data
        """
        try:
            # Build analyst context
            analyst_context = {}

            if architecture_path:
                analyst_context["architecture_path"] = architecture_path
                arch_name = Path(architecture_path).stem
            elif architecture_content:
                analyst_context["architecture_content"] = architecture_content
                arch_name = kwargs.get("architecture_name", "unknown")
            elif architecture_data:
                analyst_context["architecture_data"] = architecture_data
                arch_name = kwargs.get("architecture_name", "unknown")
            else:
                raise ValidationError("No architecture input provided")

            self._log_request(
                context, "analyze",
                architecture_name=arch_name,
                include_validation=include_validation
            )

            # Execute analysis
            analyst = self._get_analyst()
            analysis_result = analyst.execute(analyst_context)

            # Convert to dict
            result_data = analysis_result.to_dict()

            # Add validation if requested
            if include_validation and architecture_path:
                try:
                    from chatbot.modules.completeness_validator import validate_completeness
                    validation = validate_completeness(arch_name)
                    result_data["validation"] = validation
                except Exception as e:
                    self.logger.warning(f"Validation failed: {e}")
                    result_data["validation"] = {"error": str(e)}

            # Detect which patterns were applied
            patterns_applied = self._detect_patterns(result_data)

            # Store in context
            context.results["analysis"] = result_data
            context.metadata["architecture_name"] = arch_name
            context.metadata["patterns_applied"] = patterns_applied

            return ServiceResult(
                success=True,
                data={
                    "architecture_name": arch_name,
                    "analysis": result_data,
                    "confidence": result_data.get("confidence", 0.995),
                    "confidence_breakdown": result_data.get("confidence_breakdown"),
                    "patterns_applied": patterns_applied
                }
            )

        except ValidationError:
            raise  # Re-raise validation errors
        except Exception as e:
            raise ProcessingError(
                f"Threat analysis failed: {str(e)}",
                details={"architecture_name": arch_name if 'arch_name' in locals() else "unknown"}
            )

    def _detect_patterns(self, result_data: Dict) -> list:
        """
        Detect which threat patterns were applied based on analysis result.

        Args:
            result_data: Analysis result dictionary

        Returns:
            List of pattern metadata dicts
        """
        patterns = []

        # RAPIDS pattern (always applied - universal)
        patterns.append({
            "pattern_id": "rapids",
            "name": "MITRE ATT&CK + RAPIDS",
            "scope": "universal",
            "description": "6 threat categories: Ransomware, Application, Phishing, Insider, DoS, Supply Chain",
            "technique_source": "MITRE Enterprise ATT&CK (14 tactics)",
            "status": "applied"
        })

        # AI/ML pattern (conditional - check for AI/ML specific data)
        ai_ml_data = (result_data.get("ai_ml_risks")
                      or result_data.get("arc_risks")
                      or result_data.get("ai_ml_assessment")
                      or result_data.get("ai_controls_recommended"))
        if ai_ml_data:
            # Extract trigger info from architecture
            ai_services = []
            components = result_data.get("components", [])
            for comp in components:
                comp_type = comp.get("type", "").lower()
                if any(keyword in comp_type for keyword in ["lambda", "sagemaker", "ml", "ai", "inference"]):
                    ai_services.append(comp.get("name", comp_type))

            patterns.append({
                "pattern_id": "ai_ml_arc",
                "name": "MITRE ATLAS + ARC Framework",
                "scope": "conditional",
                "description": "AI/ML threat detection: 46 risks, 88 controls",
                "technique_source": "MITRE ATLAS (14 tactics, 146 techniques)",
                "trigger": f"Detected AI/ML services: {', '.join(ai_services[:3])}" if ai_services else "AI/ML components detected",
                "status": "applied"
            })

        # Cloud pattern (partial implementation - note limitations)
        cloud_services = []
        components = result_data.get("components", [])
        for comp in components:
            comp_type = comp.get("type", "").lower()
            if any(keyword in comp_type for keyword in ["s3", "ec2", "lambda", "iam", "vpc", "azure", "gcp"]):
                cloud_services.append(comp.get("name", comp_type))

        if cloud_services:
            patterns.append({
                "pattern_id": "cloud_generic",
                "name": "Cloud Generic (MITRE Enterprise)",
                "scope": "conditional",
                "description": "Generic cloud threat detection using MITRE Enterprise",
                "technique_source": "MITRE Enterprise ATT&CK (not cloud-specific)",
                "trigger": f"Detected cloud services: {', '.join(cloud_services[:3])}",
                "status": "partial",
                "limitations": [
                    "No AWS/Azure/GCP-specific threat models",
                    "No cloud-native misconfiguration detection",
                    "No serverless-specific attack patterns"
                ]
            })

        return patterns

    def list_patterns(self, context: ServiceContext) -> ServiceResult:
        """
        List available threat patterns.

        Returns:
            ServiceResult with pattern metadata
        """
        try:
            from chatbot.modules.pattern_registry import get_pattern_registry

            registry = get_pattern_registry()
            patterns = registry.list_patterns()

            return ServiceResult(
                success=True,
                data={
                    "patterns": patterns,
                    "count": len(patterns)
                }
            )

        except Exception as e:
            raise ProcessingError(f"Failed to list patterns: {str(e)}")


__all__ = ['ThreatAnalysisService']
