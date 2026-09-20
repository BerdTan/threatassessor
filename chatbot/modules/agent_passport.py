"""
Agent Passport — HMAC-SHA256 signed identity token for TAclaw jobs.

Minted at TAclaw job creation. Validates caller identity across the pipeline
boundary. Invalid or expired passports fire DETECT-AGT-001.

Fields in export bundle: provenance.agent_passport (no secret included).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple

_DEFAULT_TTL = 300  # seconds — longer than any normal TAclaw run


@dataclass
class AgentPassport:
    caller: str       # "taclaw" | MCP tool | user-agent string
    target: str       # arch_name being assessed
    job_id: str
    issued_at: float  # unix timestamp
    ttl: int = _DEFAULT_TTL

    def passport_id(self) -> str:
        return f"PP-{self.job_id[:12]}"

    def is_expired(self) -> bool:
        return (time.time() - self.issued_at) > self.ttl

    def _payload_bytes(self) -> bytes:
        return json.dumps(
            {
                "caller": self.caller,
                "target": self.target,
                "job_id": self.job_id,
                "issued_at": self.issued_at,
                "ttl": self.ttl,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()

    def encode(self, secret: str) -> str:
        """Return base64url(payload).hmac_sha256(payload)."""
        b64 = base64.urlsafe_b64encode(self._payload_bytes()).rstrip(b"=").decode()
        sig = hmac.new(secret.encode(), self._payload_bytes(), hashlib.sha256).hexdigest()
        return f"{b64}.{sig}"

    def to_provenance(self) -> dict:
        """Safe subset for export bundle — no secret, no token."""
        return {
            "passport_id": self.passport_id(),
            "caller": self.caller,
            "target": self.target,
            "job_id": self.job_id,
            "issued_at": self.issued_at,
        }


def _secret() -> str:
    return os.environ.get("API_KEY", "")


def mint_passport(
    caller: str,
    target: str,
    job_id: str,
    ttl: int = _DEFAULT_TTL,
) -> Tuple[AgentPassport, str]:
    """Mint a signed passport. Returns (passport, encoded_token)."""
    p = AgentPassport(caller=caller, target=target, job_id=job_id, issued_at=time.time(), ttl=ttl)
    return p, p.encode(_secret())


def validate_token(token: str) -> Tuple[bool, str, Optional[AgentPassport]]:
    """
    Validate a signed passport token.

    Returns (is_valid, reason, passport_or_None).
    reason ∈ {"ok", "malformed_token", "decode_error", "invalid_signature", "expired"}
    """
    if not token or "." not in token:
        return False, "malformed_token", None

    b64_part, sig_part = token.rsplit(".", 1)
    try:
        padded = b64_part + "=" * (-len(b64_part) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return False, "decode_error", None

    p = AgentPassport(
        caller=data.get("caller", ""),
        target=data.get("target", ""),
        job_id=data.get("job_id", ""),
        issued_at=float(data.get("issued_at", 0)),
        ttl=int(data.get("ttl", _DEFAULT_TTL)),
    )

    expected = hmac.new(_secret().encode(), p._payload_bytes(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_part):
        return False, "invalid_signature", None

    if p.is_expired():
        return False, "expired", p

    return True, "ok", p
