from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE,
    flow_name TEXT,
    start_time REAL,
    end_time REAL,
    duration REAL,
    success INTEGER,
    failure_reason TEXT,
    selector_hit_rate REAL
);
"""

def init_db(db_path: Union[str, Path]) -> sqlite3.Connection:
    """Initialize the SQLite database and return a connection.

    Parameters
    ----------
    db_path: str or Path
        Location of the SQLite database file. Use ":memory:" for an in-memory DB.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute(SCHEMA)
    conn.commit()
    return conn

def log_run(
    conn: sqlite3.Connection,
    run_id: str,
    flow_name: str,
    start_time: float,
    end_time: float,
    success: bool,
    failure_reason: str | None = None,
    selector_hit_rate: float | None = None,
) -> None:
    """Record the outcome of a workflow run.

    Parameters
    ----------
    conn: sqlite3.Connection
        Database connection obtained from ``init_db``.
    run_id: str
        Identifier for the run.
    flow_name: str
        Name of the executed flow.
    start_time: float
        Start time in seconds since the epoch.
    end_time: float
        End time in seconds since the epoch.
    success: bool
        ``True`` if the run completed successfully, ``False`` otherwise.
    failure_reason: str, optional
        Reason for failure if ``success`` is ``False``.
    selector_hit_rate: float, optional
        Ratio of successful selector resolutions during the run.
    """
    duration = end_time - start_time
    conn.execute(
        "INSERT INTO runs (run_id, flow_name, start_time, end_time, duration, success, failure_reason, selector_hit_rate) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            flow_name,
            start_time,
            end_time,
            duration,
            int(success),
            failure_reason,
            selector_hit_rate,
        ),
    )
    conn.commit()

def get_success_rate(conn: sqlite3.Connection) -> float:
    """Return the success rate of logged runs as a fraction between 0 and 1."""
    cur = conn.execute("SELECT AVG(success) FROM runs")
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0.0

def get_average_duration(conn: sqlite3.Connection) -> float:
    """Return the average duration of logged runs in seconds."""
    cur = conn.execute("SELECT AVG(duration) FROM runs")
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0.0
