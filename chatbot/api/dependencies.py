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


def spend_gate(entry_point: str):
    """Dependency factory: fail-closed spend gate for a route (Entry 264).

    Attach with ``dependencies=[Depends(spend_gate("name"))]`` on every route
    that can spend LLM tokens. ``chatbot.harness.spend_gate.SPEND_ROUTES`` lists
    them and a test fails if one is missing the gate.
    """
    import logging

    from fastapi import Request

    from chatbot.harness import spend_gate as _gate
    from chatbot.harness.caller_context import build_caller_context

    async def spend_gate(request: Request) -> None:  # name is asserted by tests
        caller = build_caller_context(
            request.headers, request.client.host if request.client else None, "rest"
        )
        verdict = _gate.check(
            entry_point,
            architecture=request.path_params.get("architecture_name", ""),
            caller_id=caller["caller_id"],
        )
        if not verdict.allowed:
            logging.getLogger(__name__).warning(
                "spend_gate %s entry=%s caller=%s session=%s reason=%s",
                verdict.action, entry_point, caller["caller_id"], caller["session_id"], verdict.reason,
            )
            raise HTTPException(
                status_code=(
                    status.HTTP_503_SERVICE_UNAVAILABLE
                    if verdict.action == "kill"
                    else status.HTTP_429_TOO_MANY_REQUESTS
                    if verdict.action == "throttle"
                    else status.HTTP_403_FORBIDDEN
                ),
                detail={"blocked": True, "action": verdict.action, "reason": verdict.reason},
            )
        from chatbot.harness.spend_ledger import LEDGER

        LEDGER.record(caller["caller_id"], requests=1)

    return spend_gate
