from unittest.mock import MagicMock

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
import workflow.actions_outlook as outlook


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="test"), steps=[])
    return ExecutionContext(flow, {})


def test_outlook_actions(monkeypatch):
    app = MagicMock()
    item = MagicMock()
    session = MagicMock()
    session.OpenSharedItem.return_value = item
    app.Session = session
    app.Application.Run = MagicMock()
    monkeypatch.setattr(outlook, "win32", MagicMock(Dispatch=lambda prog_id: app))

    ctx = build_ctx()

    outlook.outlook_open(Step(id="open", action="outlook.open", params={"path": "mail.msg"}), ctx)
    assert ctx.globals["_outlook_item"] is item

    outlook.outlook_save(Step(id="save", action="outlook.save", params={"path": "saved.msg"}), ctx)
    item.SaveAs.assert_called_once_with("saved.msg")

    outlook.outlook_run_macro(Step(id="macro", action="outlook.run_macro", params={"name": "Macro1"}), ctx)
    app.Application.Run.assert_called_once_with("Macro1")
