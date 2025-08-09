from __future__ import annotations

import fcntl
import json
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, List, Optional


def _match_field(field: str, value: int) -> bool:
    if field == "*":
        return True
    if field.startswith("*/"):
        step = int(field[2:])
        return value % step == 0
    for part in field.split(","):
        if part and int(part) == value:
            return True
    return False


def _cron_match(expr: str, dt: datetime) -> bool:
    fields = expr.split()
    if len(fields) == 5:
        fields = ["0"] + fields
    if len(fields) != 6:
        raise ValueError("Cron expression must have 5 or 6 fields")
    second, minute, hour, day, month, weekday = fields
    checks = [
        (second, dt.second),
        (minute, dt.minute),
        (hour, dt.hour),
        (day, dt.day),
        (month, dt.month),
        (weekday, dt.weekday()),
    ]
    return all(_match_field(f, v) for f, v in checks)


def capture_crash(exc: Exception, log_file: Optional[Path], report_dir: Path) -> Path:
    """Write a crash report with log and environment data."""
    report_dir.mkdir(parents=True, exist_ok=True)
    log_content = ""
    if log_file and log_file.exists():
        log_content = log_file.read_text()
    data = {
        "error": str(exc),
        "env": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "log": log_content,
    }
    path = report_dir / f"crash_{int(time.time() * 1000)}.json"
    path.write_text(json.dumps(data))
    return path


@dataclass
class ScheduledJob:
    cron: str
    func: Callable[[], None]
    lock_file: Path
    log_file: Optional[Path] = None
    report_dir: Path = Path("reports")
    conditions: List[Callable[[], bool]] = field(default_factory=list)


class CronScheduler:
    """Simple cron-like scheduler with file locking."""

    def __init__(self) -> None:
        self.jobs: List[ScheduledJob] = []

    def add_job(
        self,
        cron: str,
        func: Callable[[], None],
        lock_file: Path | str,
        log_file: Optional[Path | str] = None,
        report_dir: Path | str = Path("reports"),
        conditions: Optional[Iterable[Callable[[], bool]]] = None,
    ) -> None:
        """Register a scheduled job.

        Parameters
        ----------
        cron:
            Cron expression specifying when the job should run.
        func:
            Callback executed when the schedule matches.
        lock_file:
            File used for obtaining an exclusive lock.
        log_file:
            Optional path to a log file collected on crashes.
        report_dir:
            Directory where crash reports are written.
        conditions:
            Iterable of callables executed before the job. If any
            callable returns ``False`` the job is skipped.
        """
        job = ScheduledJob(
            cron,
            func,
            Path(lock_file),
            Path(log_file) if log_file else None,
            Path(report_dir),
            list(conditions) if conditions else [],
        )
        self.jobs.append(job)

    def run_pending(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        for job in self.jobs:
            if not _cron_match(job.cron, now):
                continue
            if any(not cond() for cond in job.conditions):
                continue
            job.lock_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(job.lock_file, os.O_RDWR | os.O_CREAT)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                continue
            try:
                job.func()
            except Exception as exc:  # pragma: no cover - defensive
                capture_crash(exc, job.log_file, job.report_dir)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
