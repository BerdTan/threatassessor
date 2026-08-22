"""
Shared slowapi limiter instance.

Import `limiter` here rather than instantiating it in each route module —
slowapi's state tracking is per-limiter-instance, so a single shared object
ensures limits accumulate correctly across all requests.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
