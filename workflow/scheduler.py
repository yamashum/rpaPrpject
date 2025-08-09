from __future__ import annotations

import fcntl
import json
import os
import platform
import time
import re
import subprocess
import sys
import ctypes
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, List, Optional

_POWER_SUPPLY_BASE = Path("/sys/class/power_supply")


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


def is_vpn_connected() -> bool:
    """Return True if a VPN network interface appears to be active.

    The check looks for common interface names such as ``tun``, ``tap`` or
    ``ppp`` using platform specific commands. The result is heuristic and
    ``False`` is returned when the status cannot be determined.
    """
    try:
        if sys.platform.startswith("win"):
            output = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, check=False
            ).stdout.lower()
            tokens = ("vpn", "ppp adapter", "tun", "tap")
            return any(tok in output for tok in tokens)
        else:
            output = ""
            for cmd in (["ip", "addr"], ["ifconfig"]):
                try:
                    output = subprocess.run(
                        cmd, capture_output=True, text=True, check=False
                    ).stdout
                    break
                except FileNotFoundError:
                    continue
            return bool(re.search(r"\b(tun|tap|ppp)\d", output))
    except Exception:
        return False


def is_ac_powered() -> bool:
    """Return True if the system is running on AC power.

    Attempts to query platform specific APIs and falls back to ``False`` when
    the status cannot be determined.
    """
    try:
        if sys.platform.startswith("win"):
            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [
                    ("ACLineStatus", ctypes.c_byte),
                    ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte),
                    ("Reserved1", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong),
                    ("BatteryFullLifeTime", ctypes.c_ulong),
                ]

            status = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
                return status.ACLineStatus == 1
            return False
        elif sys.platform == "darwin":
            output = subprocess.run(
                ["pmset", "-g", "ps"], capture_output=True, text=True, check=False
            ).stdout
            return "AC Power" in output
        else:
            base = _POWER_SUPPLY_BASE
            if not base.exists():
                return False
            for path in base.glob("*"):
                try:
                    if (path / "online").read_text().strip() == "1":
                        return True
                except FileNotFoundError:
                    continue
            return False
    except Exception:
        return False


def is_screen_locked() -> bool:
    """Return True if the current desktop session is locked.

    The detection is best-effort and returns ``False`` when unsupported on the
    current platform.
    """
    try:
        if sys.platform.startswith("win"):
            user32 = ctypes.windll.user32
            DESKTOP_SWITCHDESKTOP = 0x0100
            handle = user32.OpenDesktopW("Default", 0, False, DESKTOP_SWITCHDESKTOP)
            if not handle:
                return False
            try:
                return not user32.SwitchDesktop(handle)
            finally:
                user32.CloseDesktop(handle)
        elif sys.platform == "darwin":
            output = subprocess.run(
                [
                    "python3",
                    "-c",
                    "import Quartz,sys;"
                    "d=Quartz.CGSessionCopyCurrentDictionary();"
                    "print(d.get('CGSSessionScreenIsLocked',0))",
                ],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            return output == "1"
        else:
            try:
                output = subprocess.run(
                    ["gnome-screensaver-command", "-q"],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout
                if "is active" in output:
                    return True
            except FileNotFoundError:
                pass
            return False
    except Exception:
        return False


def _get_display_info() -> dict:
    """Return basic display information such as DPI and monitor sizes."""
    dpi = 96
    monitors: List[dict] = []
    try:
        from .gui_tools import _screen_dpi  # type: ignore

        dpi = int(_screen_dpi())
    except Exception:
        pass

    try:
        if sys.platform.startswith("win"):
            user32 = ctypes.windll.user32
            try:
                user32.SetProcessDPIAware()  # type: ignore[attr-defined]
            except Exception:
                pass
            width = int(user32.GetSystemMetrics(0))
            height = int(user32.GetSystemMetrics(1))
            monitors.append({"width": width, "height": height})
    except Exception:
        pass

    return {"dpi": dpi, "monitors": monitors}


def _is_admin() -> bool:
    """Return True if the current process has administrative privileges."""
    try:
        if os.name == "nt":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def capture_crash(exc: Exception, log_file: Optional[Path], report_dir: Path) -> Path:
    """Write a crash report with log and environment data."""
    report_dir.mkdir(parents=True, exist_ok=True)
    log_content = ""
    if log_file and log_file.exists():
        try:
            with log_file.open("r", encoding="utf-8", errors="replace") as fh:
                log_content = "".join(deque(fh, maxlen=1000))
        except Exception:
            log_content = log_file.read_text()
    data = {
        "error": str(exc),
        "env": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "display": _get_display_info(),
            "is_admin": _is_admin(),
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
