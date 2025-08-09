"""Access automation actions using win32com."""
from __future__ import annotations

from typing import Any, Dict, List

try:  # pragma: no cover - optional dependency
    import win32com.client as win32
except Exception:  # pragma: no cover - optional dependency
    win32 = None  # type: ignore

from .flow import Step
from .runner import ExecutionContext

# keys for storing Access application and database in execution context
_ACCESS_APP = "_access_app"
_ACCESS_DB = "_access_db"


def access_open(step: Step, ctx: ExecutionContext) -> Any:
    """Open a Microsoft Access database."""
    if win32 is None:
        raise RuntimeError("win32com.client is not installed")
    path = step.params["path"]
    visible = step.params.get("visible", False)
    app = ctx.globals.get(_ACCESS_APP)
    if app is None:
        app = win32.Dispatch("Access.Application")
        ctx.globals[_ACCESS_APP] = app
    app.Visible = visible
    app.OpenCurrentDatabase(path)
    ctx.globals[_ACCESS_DB] = app.CurrentDb()
    return path


def access_query(step: Step, ctx: ExecutionContext) -> Any:
    """Execute a SQL query and return rows as a list of dictionaries."""
    sql = step.params["sql"]
    db = ctx.globals[_ACCESS_DB]
    rs = db.OpenRecordset(sql)
    fields = [field.Name for field in rs.Fields]
    rows: List[Dict[str, Any]] = []
    while not rs.EOF:
        row = {name: rs.Fields(name).Value for name in fields}
        rows.append(row)
        rs.MoveNext()
    rs.Close()
    return rows


def access_export_report(step: Step, ctx: ExecutionContext) -> Any:
    """Export a report to a file (e.g. PDF)."""
    report = step.params["name"]
    path = step.params["path"]
    fmt = step.params.get("format", "PDF")
    app = ctx.globals[_ACCESS_APP]
    # acOutputReport = 3
    app.DoCmd.OutputTo(3, report, fmt, path)
    return path


ACCESS_ACTIONS = {
    "access.open": access_open,
    "access.query": access_query,
    "access.export_report": access_export_report,
}
