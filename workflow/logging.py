from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def log_step(
    run_id: str,
    run_dir: Path,
    step_id: str,
    action: str,
    duration: float,
    result: str,
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
    record.update(extra)
    if redact:
        for field in redact:
            if field in record:
                record[field] = "***"
    log_path = run_dir / "log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
