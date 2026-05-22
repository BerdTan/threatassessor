"""
Base Service Layer for ThreatAssessor API

Provides:
- Request context isolation (no shared state between requests)
- Thread-safe operations
- Structured error handling
- Base service class for all agent teams

Design Principles:
- Each request gets isolated context
- No global state mutations
- Thread-safe caching for MITRE data
- Consistent error responses

Version: 1.0 (Stage 2, Phase 2A)
"""

import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


@dataclass
class ServiceContext:
    """
    Isolated context for a single request.

    Contains:
    - request_id: Unique identifier for tracing
    - timestamp: Request start time
    - metadata: Custom request metadata
    - results: Accumulated results (mutable within context)
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "results": self.results
        }


@dataclass
class ServiceResult:
    """
    Standard service result format.

    All services return this format for consistency.
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    request_id: Optional[str] = None
    execution_time_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "success": self.success,
            "request_id": self.request_id
        }

        if self.data is not None:
            result["data"] = self.data

        if self.error is not None:
            result["error"] = self.error

        if self.execution_time_ms is not None:
            result["execution_time_ms"] = self.execution_time_ms

        return result


class ServiceError(Exception):
    """Base exception for service layer errors."""
    def __init__(self, message: str, code: str = "SERVICE_ERROR", details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class ValidationError(ServiceError):
    """Input validation error."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, code="VALIDATION_ERROR", details=details)


class ProcessingError(ServiceError):
    """Error during request processing."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, code="PROCESSING_ERROR", details=details)


class BaseService(ABC):
    """
    Abstract base class for all ThreatAssessor services.

    Provides:
    - Request context management
    - Thread safety
    - Structured logging
    - Error handling

    Subclasses:
    - ThreatAnalysisService (Team 1: Deterministic)
    - CritiqueService (Team 2: MoE Critics)
    - OrchestrationService (Team 3: Consensus)
    """

    def __init__(self, name: str):
        """
        Initialize service.

        Args:
            name: Service name for logging
        """
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self._lock = threading.RLock()  # Re-entrant lock for thread safety
        self.logger.info(f"Initialized {name} service")

    @abstractmethod
    def execute(self, context: ServiceContext, **kwargs) -> ServiceResult:
        """
        Execute service with isolated context.

        Args:
            context: Isolated request context
            **kwargs: Service-specific parameters

        Returns:
            ServiceResult with success/error info
        """
        pass

    def create_context(self, metadata: Optional[Dict[str, Any]] = None) -> ServiceContext:
        """
        Create isolated context for new request.

        Args:
            metadata: Optional request metadata

        Returns:
            New ServiceContext with unique request_id
        """
        return ServiceContext(metadata=metadata or {})

    def _validate_input(self, **kwargs) -> None:
        """
        Validate service inputs.

        Raises:
            ValidationError: If validation fails
        """
        # Subclasses override to add validation logic
        pass

    def _log_request(self, context: ServiceContext, action: str, **details):
        """Log request with context."""
        self.logger.info(
            f"[{context.request_id}] {self.name}.{action}",
            extra={
                "request_id": context.request_id,
                "service": self.name,
                "action": action,
                **details
            }
        )

    def _log_error(self, context: ServiceContext, error: Exception):
        """Log error with context."""
        self.logger.error(
            f"[{context.request_id}] {self.name} error: {str(error)}",
            extra={
                "request_id": context.request_id,
                "service": self.name,
                "error_type": type(error).__name__,
                "error_message": str(error)
            },
            exc_info=True
        )

    def safe_execute(self, metadata: Optional[Dict] = None, **kwargs) -> ServiceResult:
        """
        Execute service with automatic context management and error handling.

        Args:
            metadata: Optional request metadata
            **kwargs: Service-specific parameters

        Returns:
            ServiceResult (always returns, never raises)
        """
        context = self.create_context(metadata)
        start_time = datetime.utcnow()

        try:
            self._log_request(context, "start", **kwargs)
            self._validate_input(**kwargs)

            result = self.execute(context, **kwargs)

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            result.execution_time_ms = execution_time
            result.request_id = context.request_id

            self._log_request(
                context, "complete",
                success=result.success,
                execution_time_ms=execution_time
            )

            return result

        except ValidationError as e:
            self._log_error(context, e)
            return ServiceResult(
                success=False,
                error=f"Validation error: {e.message}",
                request_id=context.request_id
            )

        except ProcessingError as e:
            self._log_error(context, e)
            return ServiceResult(
                success=False,
                error=f"Processing error: {e.message}",
                request_id=context.request_id
            )

        except Exception as e:
            self._log_error(context, e)
            return ServiceResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                request_id=context.request_id
            )


# Thread-safe singleton cache for MITRE data
class MitreCache:
    """
    Thread-safe singleton cache for MITRE ATT&CK data.

    Ensures:
    - Single load of 44MB enterprise-attack.json
    - Thread-safe access from concurrent requests
    - Lazy initialization (loaded on first use)
    """

    _instance = None
    _lock = threading.Lock()
    _data_lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._data = None
                    self._embeddings = None
                    self._initialized = True
                    logger.info("MitreCache singleton initialized")

    def get_data(self):
        """Get MITRE ATT&CK data (lazy load)."""
        if self._data is None:
            with self._data_lock:
                if self._data is None:
                    logger.info("Loading MITRE ATT&CK data...")
                    from chatbot.modules.mitre import MitreHelper
                    helper = MitreHelper()
                    self._data = helper.get_enterprise_data()
                    logger.info("MITRE data loaded (cached)")
        return self._data

    def get_embeddings(self):
        """Get technique embeddings (lazy load)."""
        if self._embeddings is None:
            with self._data_lock:
                if self._embeddings is None:
                    logger.info("Loading technique embeddings...")
                    from chatbot.modules.mitre_embeddings import load_embeddings
                    self._embeddings = load_embeddings()
                    logger.info("Embeddings loaded (cached)")
        return self._embeddings

    def clear(self):
        """Clear cache (for testing/updates)."""
        with self._data_lock:
            self._data = None
            self._embeddings = None
            logger.info("MitreCache cleared")


__all__ = [
    'BaseService',
    'ServiceContext',
    'ServiceResult',
    'ServiceError',
    'ValidationError',
    'ProcessingError',
    'MitreCache'
]
