from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Tuple, Union

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

CREATE TABLE IF NOT EXISTS selector_stats (
    selector TEXT PRIMARY KEY,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0
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
    conn.executescript(SCHEMA)
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


# ----- additional statistics helpers -----
def log_selector_result(conn: sqlite3.Connection, selector: str, success: bool) -> None:
    """Accumulate statistics for a selector.

    Each call increments either the success or failure count for the given
    ``selector``. The table keeps running totals, allowing callers to compute
    success rates across multiple runs.
    """

    conn.execute(
        "INSERT INTO selector_stats(selector, success_count, failure_count) VALUES (?, ?, ?) "
        "ON CONFLICT(selector) DO UPDATE SET success_count = success_count + ?, failure_count = failure_count + ?",
        (
            selector,
            1 if success else 0,
            0 if success else 1,
            1 if success else 0,
            0 if success else 1,
        ),
    )
    conn.commit()


def get_selector_success_rates(conn: sqlite3.Connection) -> Dict[str, float]:
    """Return success rate per selector.

    Returns a mapping of selector string to a float between ``0`` and ``1``.
    """

    cur = conn.execute(
        "SELECT selector, success_count, failure_count FROM selector_stats"
    )
    rates: Dict[str, float] = {}
    for selector, s_cnt, f_cnt in cur.fetchall():
        total = s_cnt + f_cnt
        rates[selector] = (s_cnt / total) if total else 0.0
    return rates


def get_failure_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return a mapping of failure reason to occurrence count."""

    cur = conn.execute(
        "SELECT failure_reason, COUNT(*) FROM runs WHERE success = 0 GROUP BY failure_reason"
    )
    return {reason or "unknown": count for reason, count in cur.fetchall()}


def get_run_counts_by_period(
    conn: sqlite3.Connection, period: str
) -> Iterable[Tuple[str, int]]:
    """Return run counts grouped by time period.

    Parameters
    ----------
    period: str
        One of ``'day'``, ``'week'`` or ``'month'``.
    """

    if period == "day":
        expr = "date(start_time, 'unixepoch')"
    elif period == "week":
        expr = "strftime('%Y-%W', start_time, 'unixepoch')"
    elif period == "month":
        expr = "strftime('%Y-%m', start_time, 'unixepoch')"
    else:  # pragma: no cover - defensive programming
        raise ValueError("period must be 'day', 'week' or 'month'")

    cur = conn.execute(
        f"SELECT {expr} AS p, COUNT(*) FROM runs GROUP BY p ORDER BY p"
    )
    return cur.fetchall()
