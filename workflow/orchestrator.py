from __future__ import annotations

"""Simple in-memory orchestration layer for dispatching jobs to multiple
hosts.

This module provides a minimal orchestration engine that can be used by the
scheduler and runner to coordinate job execution across a fleet of hosts.  It
is intentionally lightweight and does not persist state; callers are expected
to keep the process alive for the lifetime of the orchestration session.
"""

from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Dict, Optional, List
import uuid


@dataclass
class Job:
    """Represents a single scheduled job."""

    flow: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    host: Optional[str] = None
    status: str = "queued"  # queued -> running -> finished/failed/stopped
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    result: Optional[str] = None


class Orchestrator:
    """In-memory orchestration engine.

    The orchestrator keeps track of submitted jobs and their execution state
    across multiple hosts.  Each host polls for work using :meth:`assign_job`
    and reports progress back via :meth:`update_status`.
    """

    def __init__(self) -> None:
        self.jobs: Dict[str, Job] = {}
        self.lock = Lock()

    # ------------------------------------------------------------------
    # Job submission and assignment
    # ------------------------------------------------------------------
    def submit(self, flow: str) -> Job:
        """Create a new job for the given flow and return it."""
        job = Job(flow=flow)
        with self.lock:
            self.jobs[job.id] = job
        return job

    def assign_job(self, host: str) -> Optional[Job]:
        """Assign the next queued job to ``host`` and mark it running.

        Returns the job or ``None`` if no work is available.
        """
        with self.lock:
            for job in self.jobs.values():
                if job.status == "queued":
                    job.status = "running"
                    job.host = host
                    job.started = datetime.utcnow()
                    return job
        return None

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------
    def update_status(
        self, job_id: str, status: str, *, result: Optional[str] = None
    ) -> None:
        """Update status for ``job_id``.

        ``status`` should be one of ``running``, ``finished``, ``failed`` or
        ``stopped``.
        """
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job.status = status
            if status in {"finished", "failed", "stopped"}:
                job.finished = datetime.utcnow()
                job.result = result

    # ------------------------------------------------------------------
    # Control operations
    # ------------------------------------------------------------------
    def stop(self, job_id: str) -> None:
        """Mark ``job_id`` as stopped."""
        self.update_status(job_id, "stopped")

    def rerun(self, job_id: str) -> Optional[Job]:
        """Requeue the given job with a new identifier."""
        with self.lock:
            old = self.jobs.get(job_id)
            if not old:
                return None
            job = Job(flow=old.flow)
            self.jobs[job.id] = job
            return job

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def get_state(self) -> Dict[str, Dict[str, str]]:
        """Return a serialisable snapshot of all jobs."""
        with self.lock:
            return {
                jid: {
                    "flow": j.flow,
                    "host": j.host or "",
                    "status": j.status,
                    "started": j.started.isoformat() if j.started else "",
                    "finished": j.finished.isoformat() if j.finished else "",
                    "result": j.result or "",
                }
                for jid, j in self.jobs.items()
            }


# A module level orchestrator instance can be imported elsewhere
orchestrator = Orchestrator()
