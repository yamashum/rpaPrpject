from unittest.mock import MagicMock

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
import workflow.actions_office as office


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="test"), steps=[])
    return ExecutionContext(flow, {})


def test_excel_actions(monkeypatch):
    app = MagicMock()
    wb = MagicMock()
    sheet = MagicMock()
    rng = MagicMock()
    rng.Value = "old"
    sheet.Range.return_value = rng
    cells = MagicMock()
    sheet.Cells = cells
    wb.ActiveSheet = sheet
    app.Workbooks.Open.return_value = wb

    monkeypatch.setattr(office, "win32", MagicMock(Dispatch=lambda prog_id: app))

    ctx = build_ctx()

    office.excel_open(Step(id="open", action="excel.open", params={"path": "file.xlsx"}), ctx)
    assert ctx.globals["_excel_book"] is wb

    office.excel_set(Step(id="set", action="excel.set", params={"cell": "A1", "value": 123}), ctx)
    assert rng.Value == 123

    value = office.excel_get(Step(id="get", action="excel.get", params={"cell": "A1"}), ctx)
    assert value == 123

    office.excel_save(Step(id="save", action="excel.save", params={}), ctx)
    wb.Save.assert_called_once()

    office.excel_run_macro(
        Step(id="macro", action="excel.run_macro", params={"name": "Macro1"}), ctx
    )
    app.Run.assert_called_once_with("Macro1")

    office.excel_export(
        Step(id="export", action="excel.export", params={"path": "out.pdf", "format": 0}), ctx
    )
    wb.ExportAsFixedFormat.assert_called_once_with(0, "out.pdf")

    office.excel_find_replace(
        Step(id="fr", action="excel.find_replace", params={"find": "old", "replace": "new"}),
        ctx,
    )
    cells.Replace.assert_called_once_with("old", "new")

    wb2 = MagicMock()
    app.Workbooks.return_value = wb2
    office.excel_activate(
        Step(id="act", action="excel.activate", params={"name": "Book2"}), ctx
    )
    app.Workbooks.assert_called_once_with("Book2")
    wb2.Activate.assert_called_once()
    assert ctx.globals["_excel_book"] is wb2

    office.excel_close(
        Step(id="close", action="excel.close", params={"save": False}), ctx
    )
    wb2.Close.assert_called_once_with(SaveChanges=False)
    app.Quit.assert_called_once()
    assert "_excel_book" not in ctx.globals
    assert "_excel_app" not in ctx.globals
