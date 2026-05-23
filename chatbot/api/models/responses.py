"""
API Response Models

Pydantic schemas for API responses.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime


class AnalyzeResponse(BaseModel):
    """Response schema for POST /analyze endpoint."""

    success: bool = Field(description="Whether analysis succeeded")
    request_id: str = Field(description="Unique request identifier (UUID)")
    execution_time_ms: float = Field(description="Execution time in milliseconds")
    data: Dict[str, Any] = Field(description="Analysis results")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "execution_time_ms": 28734.5,
                "data": {
                    "architecture_name": "web_app",
                    "confidence": 0.995,
                    "analysis": {
                        "controls_present": ["waf", "mfa", "edr"],
                        "controls_missing": ["logging", "backup"],
                        "expected_risk_score": 77,
                        "expected_defensibility": 54
                    }
                }
            }
        }


class HealthResponse(BaseModel):
    """Response schema for GET /health endpoint."""

    status: str = Field(description="Health status: healthy, degraded, or unhealthy")
    version: str = Field(description="API version")
    timestamp: str = Field(description="Current timestamp (ISO 8601)")
    services: Dict[str, Any] = Field(description="Service status details")
    errors: Optional[list] = Field(default=None, description="Error messages if unhealthy")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.3.0",
                "timestamp": "2026-05-23T10:30:00Z",
                "services": {
                    "deterministic_engine": "operational",
                    "service_layer": "operational",
                    "mitre_cache": "loaded"
                }
            }
        }


class ErrorResponse(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs."""

    type: str = Field(description="Problem type URI")
    title: str = Field(description="Short human-readable summary")
    status: int = Field(description="HTTP status code")
    detail: str = Field(description="Human-readable explanation")
    instance: str = Field(description="API endpoint that generated error")
    request_id: Optional[str] = Field(default=None, description="Request correlation ID")

    class Config:
        json_schema_extra = {
            "example": {
                "type": "https://api.threatassessor.example.com/errors/bad-request",
                "title": "Invalid request",
                "status": 400,
                "detail": "File must have .mmd extension",
                "instance": "/api/v1/analyze",
                "request_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
