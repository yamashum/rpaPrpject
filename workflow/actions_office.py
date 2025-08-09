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


def excel_run_macro(step: Step, ctx: ExecutionContext) -> Any:
    """Run a macro in the Excel application."""
    macro = step.params["name"]
    app = ctx.globals[_EXCEL_APP]
    return app.Run(macro)


def excel_export(step: Step, ctx: ExecutionContext) -> Any:
    """Export the workbook to a fixed format (e.g. PDF)."""
    wb = ctx.globals[_EXCEL_BOOK]
    path = step.params["path"]
    fmt = step.params.get("format", 0)
    wb.ExportAsFixedFormat(fmt, path)
    return path


def excel_find_replace(step: Step, ctx: ExecutionContext) -> Any:
    """Find and replace text in the active sheet."""
    find = step.params["find"]
    replace = step.params.get("replace", "")
    sheet_name = step.params.get("sheet")
    wb = ctx.globals[_EXCEL_BOOK]
    sheet = wb.Worksheets(sheet_name) if sheet_name else wb.ActiveSheet
    sheet.Cells.Replace(find, replace)
    return replace


def excel_close(step: Step, ctx: ExecutionContext) -> Any:
    """Close the active workbook and quit the Excel application."""
    save = step.params.get("save", False)
    wb = ctx.globals.pop(_EXCEL_BOOK, None)
    if wb is not None:
        wb.Close(SaveChanges=save)
    app = ctx.globals.pop(_EXCEL_APP, None)
    if app is not None:
        app.Quit()
    return True


def excel_activate(step: Step, ctx: ExecutionContext) -> Any:
    """Activate an open workbook by name."""
    name = step.params["name"]
    app = ctx.globals[_EXCEL_APP]
    wb = app.Workbooks(name)
    wb.Activate()
    ctx.globals[_EXCEL_BOOK] = wb
    return name


OFFICE_ACTIONS = {
    "excel.open": excel_open,
    "excel.get": excel_get,
    "excel.set": excel_set,
    "excel.save": excel_save,
    "excel.run_macro": excel_run_macro,
    "excel.export": excel_export,
    "excel.find_replace": excel_find_replace,
    "excel.close": excel_close,
    "excel.activate": excel_activate,
}
