"""
API Request Models

Pydantic schemas for API requests.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional

SspProfile = Literal[
    "low_risk_cloud",
    "low_risk_onprem",
    "medium_risk_cloud",
    "high_risk_cloud_cii",
    "generative_ai",
    "digital_services_others",
    "digital_services_high_impact",
    "sandbox",
]


class AnalyzeRequest(BaseModel):
    """Request schema for POST /analyze endpoint."""

    include_validation: bool = Field(
        default=True,
        description="Run 6-check completeness validation"
    )
    ssp_profile: SspProfile = Field(
        default="low_risk_cloud",
        description=(
            "Target SSP profile for control enrichment. "
            "This is a planning instrument — it shows what controls are required "
            "if the system is classified under that profile. "
            "One of: low_risk_cloud, low_risk_onprem, medium_risk_cloud, "
            "high_risk_cloud_cii, generative_ai, digital_services_others, "
            "digital_services_high_impact, sandbox."
        )
    )
    enable_ssp: bool = Field(
        default=True,
        description="Include Singapore Government SSP control context in recommendations"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "include_validation": True,
                "ssp_profile": "medium_risk_cloud",
                "enable_ssp": True,
            }
        }
