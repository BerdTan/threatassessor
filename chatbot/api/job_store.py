"""
In-memory job store for async pipeline jobs (expert review).

Thread-safe. Jobs expire after JOB_TTL_SECONDS (1 hour by default).
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

JOB_TTL_SECONDS = 3600


@dataclass
class Job:
    job_id:    str
    status:    str          # queued | running | completed | failed | blocked
    progress:  int = 0      # 0-100
    message:   str = ""
    result:    Optional[Dict[str, Any]] = None
    error:     Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobStore:
    """Thread-safe in-memory job store with TTL expiry."""

    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self) -> Job:
        job = Job(job_id=str(uuid.uuid4()), status="queued")
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        self._evict()
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in kwargs.items():
                setattr(job, k, v)
            job.updated_at = time.time()

    def list_all(self) -> list:
        self._evict()
        with self._lock:
            return list(self._jobs.values())

    def _evict(self) -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        with self._lock:
            expired = [jid for jid, j in self._jobs.items() if j.created_at < cutoff]
            for jid in expired:
                del self._jobs[jid]


# Module-level singleton shared across all routes
_store = JobStore()


def get_job_store() -> JobStore:
    return _store
