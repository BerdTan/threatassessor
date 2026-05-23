"""
API Request Models

Pydantic schemas for API requests.
"""

from pydantic import BaseModel, Field
from typing import Optional


class AnalyzeRequest(BaseModel):
    """Request schema for POST /analyze endpoint."""

    include_validation: bool = Field(
        default=True,
        description="Run 6-check completeness validation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "include_validation": True
            }
        }
