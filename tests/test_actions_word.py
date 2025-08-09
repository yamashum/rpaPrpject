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

    bookmarks = MagicMock()
    bookmark = MagicMock()
    rng = MagicMock()
    bookmarks.Exists.return_value = True
    bookmarks.return_value = bookmark
    bookmark.Range = rng
    doc.Bookmarks = bookmarks

    content = MagicMock()
    find = MagicMock()
    find.Replacement = MagicMock()
    content.Find = find
    doc.Content = content

    ctx = build_ctx()

    word.word_open(Step(id="open", action="word.open", params={"path": "file.docx"}), ctx)
    assert ctx.globals["_word_doc"] is doc

    word.word_save(Step(id="save", action="word.save", params={}), ctx)
    doc.Save.assert_called_once()

    word.word_run_macro(Step(id="macro", action="word.run_macro", params={"name": "Macro1"}), ctx)
    app.Run.assert_called_once_with("Macro1")

    word.word_bookmark_set(
        Step(id="bm", action="word.bookmark.set", params={"name": "BM1", "value": "text"}),
        ctx,
    )
    assert rng.Text == "text"
    doc.Bookmarks.Add.assert_called_once_with("BM1", rng)

    word.word_replace_all(
        Step(id="rep", action="word.replace_all", params={"find": "old", "replace": "new"}),
        ctx,
    )
    assert find.Text == "old"
    assert find.Replacement.Text == "new"
    find.Execute.assert_called_once()

    word.word_export_pdf(
        Step(id="pdf", action="word.export_pdf", params={"path": "out.pdf"}), ctx
    )
    doc.ExportAsFixedFormat.assert_called_once_with("out.pdf", 17)
