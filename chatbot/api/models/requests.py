"""
API Request Models

Pydantic schemas for API requests.
"""

from pydantic import BaseModel, Field
from typing import List, Literal, Optional

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


# ---------------------------------------------------------------------------
# Workspace models
# ---------------------------------------------------------------------------

class WorkspaceCreate(BaseModel):
    """Create a new workspace grouping architectures into a named mega-system."""
    name: str = Field(..., pattern=r'^[a-zA-Z0-9_\-]+$', max_length=80,
                      description="URL-safe workspace name (letters, digits, _ and - only).")
    description: str = Field(default="", max_length=300)
    domain: str = Field(default="", max_length=80,
                        description="Domain tag for EventBroker sink routing (e.g. financial, healthcare).")
    architectures: List[str] = Field(..., min_length=1, max_length=50,
                                     description="Architecture names that belong to this workspace.")


class WorkspaceUpdate(BaseModel):
    """Partial update for an existing workspace."""
    description: Optional[str] = Field(default=None, max_length=300)
    domain: Optional[str] = Field(default=None, max_length=80)
    architectures: Optional[List[str]] = Field(default=None, max_length=50)


# ---------------------------------------------------------------------------
# TA-Wiz chat models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """Single turn in a TA-Wiz conversation."""
    role: Literal["user", "assistant"]
    content: str


class TAWizAskRequest(BaseModel):
    """Request body for POST /api/v1/ta-wiz/ask."""
    workspace_name: str = Field(..., min_length=1, max_length=80)
    question: str = Field(..., min_length=1, max_length=4000)
    selected_architectures: Optional[List[str]] = Field(
        default=None, max_length=50,
        description="Subset of workspace architectures to include in context. "
                    "Defaults to all workspace members if omitted.",
    )
    history: List[ChatMessage] = Field(
        default_factory=list, max_length=12,
        description="Prior conversation turns (sliding window, oldest dropped after 12).",
    )
