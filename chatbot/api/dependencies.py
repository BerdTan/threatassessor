"""
API Dependencies

Shared dependencies for FastAPI routes (authentication, etc.)
"""

import hmac
import os
from fastapi import Header, HTTPException, status


async def verify_api_key(
    tm_api_key: str = Header(None, alias="TM-API-KEY", description="ThreatAssessor API key for authentication")
) -> str:
    """Verify the TM-API-KEY header.

    Missing header → 401 (not 422) so the response is consistent with a wrong key.

    Returns:
        The validated API key string.

    Raises:
        HTTPException 401: Header absent or value does not match API_KEY.
        HTTPException 500: API_KEY not set in environment.
    """
    if not tm_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing TM-API-KEY header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    expected_key = os.getenv("API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not available",
        )

    if not hmac.compare_digest(tm_api_key.encode(), expected_key.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return tm_api_key
