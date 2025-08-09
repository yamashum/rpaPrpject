from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
import re


def log_step(
    run_id: str,
    run_dir: Path,
    step_id: str,
    action: str,
    duration: float,
    result: str,
    *,
    host: Optional[str] = None,
    user: Optional[str] = None,
    dpi: Optional[int] = None,
    monitors: Optional[Any] = None,
    selectorUsed: Optional[Any] = None,
    retries: Optional[int] = None,
    fallbackUsed: Optional[bool] = None,
    redact: Optional[Iterable[str]] = None,
    **extra: Any,
) -> None:
    """Append a step execution record to the run log.

    Parameters
    ----------
    run_id: str
        Identifier for the current run.
    run_dir: Path
        Directory for run-specific logs and artifacts.
    step_id: str
        ID of the executed step.
    action: str
        Name of the action performed.
    duration: float
        Duration of the step in milliseconds.
    result: str
        Result of the step (e.g. ``"ok"`` or ``"error"``).
    host: str, optional
        Hostname of the machine executing the step.
    user: str, optional
        User running the workflow.
    dpi: int, optional
        Screen DPI value.
    monitors: list, optional
        List of monitor geometries.
    selectorUsed: any, optional
        Selector that was ultimately used for the step.
    retries: int, optional
        Number of retry attempts before this execution.
    fallbackUsed: bool, optional
        Whether a fallback profile or selector was used.
    redact: Iterable[str], optional
        Names of fields whose values should be redacted in the log.
    extra: dict
        Additional fields to include in the log record.
    """

    record: Dict[str, Any] = {
        "runId": run_id,
        "stepId": step_id,
        "action": action,
        "duration": duration,
        "result": result,
    }
    if host is not None:
        record["host"] = host
    if user is not None:
        record["user"] = user
    if dpi is not None:
        record["dpi"] = dpi
    if monitors is not None:
        record["monitors"] = monitors
    if selectorUsed is not None:
        record["selectorUsed"] = selectorUsed
    if retries is not None:
        record["retries"] = retries
    if fallbackUsed is not None:
        record["fallbackUsed"] = fallbackUsed
    record.update(extra)
    unmasked = {
        "runId",
        "stepId",
        "action",
        "screenshot",
        "uiTree",
        "webTrace",
        "host",
        "user",
    }
    for k, v in list(record.items()):
        if k not in unmasked and isinstance(v, str):
            record[k] = mask_pii(v)
    if redact:
        for field in redact:
            if field in record:
                record[field] = "***"
    log_path = run_dir / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\d{4,}"),
]


def mask_pii(value: str) -> str:
    """Mask obvious PII like email addresses or long digit sequences."""
    masked = value
    for pat in PII_PATTERNS:
        masked = pat.sub("***", masked)
    return masked


__all__ = ["log_step", "mask_pii"]
