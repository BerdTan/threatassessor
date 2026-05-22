"""
ThreatAssessor Service Layer

Provides thread-safe, request-isolated services for:
- Team 1: Threat Analysis (Deterministic + Pattern Registry)
- Team 2: Critic Validation (MoE: Architect, Tester, Red Team)
- Team 3: Orchestration (Consensus + Executive Summary)
- Team 4: Parsing (Embedded in Team 1)

All services inherit from BaseService and provide:
- Request context isolation
- Thread-safe operations
- Structured error handling
- Consistent result format

Usage:
    from chatbot.services import ThreatAnalysisService

    service = ThreatAnalysisService()
    result = service.safe_execute(
        architecture_path="path/to/architecture.mmd"
    )

    if result.success:
        print(result.data)
    else:
        print(f"Error: {result.error}")

Version: 1.0 (Stage 2, Phase 2A)
"""

from chatbot.services.base_service import (
    BaseService,
    ServiceContext,
    ServiceResult,
    ServiceError,
    ValidationError,
    ProcessingError,
    MitreCache
)

from chatbot.services.threat_analysis_service import ThreatAnalysisService
from chatbot.services.validation_service import ValidationService

__all__ = [
    # Base classes
    'BaseService',
    'ServiceContext',
    'ServiceResult',
    'ServiceError',
    'ValidationError',
    'ProcessingError',
    'MitreCache',

    # Services
    'ThreatAnalysisService',
    'ValidationService'
]
