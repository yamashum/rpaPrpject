"""Office automation actions using win32com."""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    import win32com.client as win32
except Exception:  # pragma: no cover - optional dependency
    win32 = None  # type: ignore

from .flow import Step
from .runner import ExecutionContext

# keys for storing excel app and workbook in execution context
_EXCEL_APP = "_excel_app"
_EXCEL_BOOK = "_excel_book"


def excel_open(step: Step, ctx: ExecutionContext) -> Any:
    """Open an Excel workbook."""
    if win32 is None:
        raise RuntimeError("win32com.client is not installed")
    path = step.params["path"]
    visible = step.params.get("visible", False)
    app = ctx.globals.get(_EXCEL_APP)
    if app is None:
        app = win32.Dispatch("Excel.Application")
        ctx.globals[_EXCEL_APP] = app
    app.Visible = visible
    wb = app.Workbooks.Open(path)
    ctx.globals[_EXCEL_BOOK] = wb
    return path


def excel_get(step: Step, ctx: ExecutionContext) -> Any:
    """Get value from a cell."""
    cell = step.params["cell"]
    sheet_name = step.params.get("sheet")
    wb = ctx.globals[_EXCEL_BOOK]
    sheet = wb.Worksheets(sheet_name) if sheet_name else wb.ActiveSheet
    rng = sheet.Range(cell)
    return rng.Value


def excel_set(step: Step, ctx: ExecutionContext) -> Any:
    """Set value of a cell."""
    cell = step.params["cell"]
    value = step.params.get("value")
    sheet_name = step.params.get("sheet")
    wb = ctx.globals[_EXCEL_BOOK]
    sheet = wb.Worksheets(sheet_name) if sheet_name else wb.ActiveSheet
    rng = sheet.Range(cell)
    rng.Value = value
    return value


def excel_save(step: Step, ctx: ExecutionContext) -> Any:
    """Save the workbook."""
    wb = ctx.globals[_EXCEL_BOOK]
    path = step.params.get("path")
    if path:
        wb.SaveAs(path)
        return path
    wb.Save()
    return True


OFFICE_ACTIONS = {
    "excel.open": excel_open,
    "excel.get": excel_get,
    "excel.set": excel_set,
    "excel.save": excel_save,
}
