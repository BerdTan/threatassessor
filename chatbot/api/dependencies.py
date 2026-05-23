"""
API Dependencies

Shared dependencies for FastAPI routes (authentication, etc.)
"""

import os
from fastapi import Header, HTTPException, status


async def verify_api_key(tm_api_key: str = Header(..., alias="TM-API-KEY", description="ThreatAssessor API key for authentication")) -> str:
    """
    Verify API key from TM-API-KEY header.

    Args:
        tm_api_key: ThreatAssessor API key from header

    Returns:
        API key if valid

    Raises:
        HTTPException: 401 if key is missing or invalid
    """
    expected_key = os.getenv("API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_KEY not configured in .env file"
        )

    if tm_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    return tm_api_key
