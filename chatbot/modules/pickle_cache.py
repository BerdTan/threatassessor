"""
Signed pickle cache utility.

Saves and loads pickle payloads protected by HMAC-SHA256.
pickle.loads() is only reached if the MAC passes — a tampered file raises
ValueError before any deserialization occurs, preventing deserialization attacks.

File format:
    b"TMCACHE\x01"          — 8-byte magic + version
    hmac_digest             — 32 bytes (SHA-256)
    pickle_payload          — variable

Signing key (in order of preference):
    1. TM_PICKLE_KEY env var — set this in .env for production
    2. Stable app-level fallback — weaker, but still blocks opportunistic attacks
       from attackers who cannot read the process environment or .env file

Usage:
    from chatbot.modules.pickle_cache import dump, load

    dump(state_dict, "/path/to/cache.pkl")
    state = load("/path/to/cache.pkl")   # raises ValueError on tamper/corruption
"""

import hashlib
import hmac
import io
import logging
import os
import pickle
import sys

logger = logging.getLogger(__name__)

_MAGIC = b"TMCACHE\x01"
_MAC_LEN = 32  # SHA-256 digest size


def _signing_key() -> bytes:
    """
    Return the HMAC signing key as 32 raw bytes.

    Reads TM_PICKLE_KEY from the environment. If not set, falls back to a
    deterministic app-specific constant — weaker than a secret env var, but
    still prevents an attacker who can only write to the data directory from
    crafting a valid signed pickle without also reading the application source.
    """
    raw = os.environ.get("TM_PICKLE_KEY", "")
    if not raw:
        # Fallback: stable constant tied to this application + Python ABI.
        # Not secret, but raises the bar over unsigned pickle.
        raw = f"threatassessor-pkl-cache-v1-{sys.version_info.major}.{sys.version_info.minor}"
    return hashlib.sha256(raw.encode("utf-8")).digest()


def dump(state: object, path: str) -> None:
    """
    Serialize *state* to *path* with an HMAC-SHA256 signature.

    Writes atomically via a temp file to avoid leaving a partially-written
    (and therefore corrupt) cache file on disk.
    """
    pickle_bytes = pickle.dumps(state, protocol=pickle.HIGHEST_PROTOCOL)
    mac = hmac.new(_signing_key(), pickle_bytes, hashlib.sha256).digest()

    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "wb") as f:
            f.write(_MAGIC)
            f.write(mac)
            f.write(pickle_bytes)
        os.replace(tmp_path, path)  # atomic on POSIX; best-effort on Windows
    except Exception:
        # Clean up temp file if anything went wrong
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load(path: str) -> object:
    """
    Load and verify a signed pickle cache from *path*.

    Raises:
        FileNotFoundError: if *path* does not exist.
        ValueError: if the magic header is wrong, the MAC fails, or the
                    payload cannot be unpickled.  The caller should treat any
                    ValueError as "cache invalid — regenerate from source".
    """
    with open(path, "rb") as f:
        raw = f.read()

    if len(raw) < len(_MAGIC) + _MAC_LEN:
        raise ValueError(f"Cache file too short to be valid: {path}")

    if not raw.startswith(_MAGIC):
        raise ValueError(f"Cache file has wrong magic header (not a ThreatAssessor cache): {path}")

    stored_mac   = raw[len(_MAGIC): len(_MAGIC) + _MAC_LEN]
    pickle_bytes = raw[len(_MAGIC) + _MAC_LEN:]

    expected_mac = hmac.new(_signing_key(), pickle_bytes, hashlib.sha256).digest()

    if not hmac.compare_digest(stored_mac, expected_mac):
        raise ValueError(
            f"Pickle cache MAC verification failed — file may have been tampered with: {path}"
        )

    # MAC passed — safe to deserialize
    try:
        return pickle.loads(pickle_bytes)
    except Exception as exc:
        raise ValueError(f"Pickle deserialization failed after MAC pass: {exc}") from exc
