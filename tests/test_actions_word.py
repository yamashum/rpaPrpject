from unittest.mock import MagicMock

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
import workflow.actions_word as word


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="test"), steps=[])
    return ExecutionContext(flow, {})


def test_word_actions(monkeypatch):
    app = MagicMock()
    doc = MagicMock()
    app.Documents.Open.return_value = doc
    monkeypatch.setattr(word, "win32", MagicMock(Dispatch=lambda prog_id: app))

    ctx = build_ctx()

    word.word_open(Step(id="open", action="word.open", params={"path": "file.docx"}), ctx)
    assert ctx.globals["_word_doc"] is doc

    word.word_save(Step(id="save", action="word.save", params={}), ctx)
    doc.Save.assert_called_once()

    word.word_run_macro(Step(id="macro", action="word.run_macro", params={"name": "Macro1"}), ctx)
    app.Run.assert_called_once_with("Macro1")
