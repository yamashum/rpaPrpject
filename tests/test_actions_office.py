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
