"""Word automation actions using win32com."""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    import win32com.client as win32
except Exception:  # pragma: no cover - optional dependency
    win32 = None  # type: ignore

from .flow import Step
from .runner import ExecutionContext

# keys for storing word app and document in execution context
_WORD_APP = "_word_app"
_WORD_DOC = "_word_doc"


def word_open(step: Step, ctx: ExecutionContext) -> Any:
    """Open a Word document."""
    if win32 is None:
        raise RuntimeError("win32com.client is not installed")
    path = step.params["path"]
    visible = step.params.get("visible", False)
    app = ctx.globals.get(_WORD_APP)
    if app is None:
        app = win32.Dispatch("Word.Application")
        ctx.globals[_WORD_APP] = app
    app.Visible = visible
    doc = app.Documents.Open(path)
    ctx.globals[_WORD_DOC] = doc
    return path


def word_save(step: Step, ctx: ExecutionContext) -> Any:
    """Save the active Word document."""
    doc = ctx.globals[_WORD_DOC]
    path = step.params.get("path")
    if path:
        doc.SaveAs(path)
        return path
    doc.Save()
    return True


def word_run_macro(step: Step, ctx: ExecutionContext) -> Any:
    """Run a macro in the Word application."""
    macro = step.params["name"]
    app = ctx.globals[_WORD_APP]
    return app.Run(macro)


def word_bookmark_set(step: Step, ctx: ExecutionContext) -> Any:
    """Set the text of a bookmark."""
    name = step.params["name"]
    value = step.params.get("value", "")
    doc = ctx.globals[_WORD_DOC]
    if not doc.Bookmarks.Exists(name):  # type: ignore[attr-defined]
        raise KeyError(name)
    rng = doc.Bookmarks(name).Range
    rng.Text = value
    doc.Bookmarks.Add(name, rng)
    return value


def word_replace_all(step: Step, ctx: ExecutionContext) -> Any:
    """Replace all occurrences of text in the document."""
    find_text = step.params["find"]
    replace_text = step.params.get("replace", "")
    doc = ctx.globals[_WORD_DOC]
    rng = doc.Content
    find = rng.Find
    find.Text = find_text
    find.Replacement.Text = replace_text
    find.Execute(Replace=2, Forward=True, Wrap=1)
    return True


def word_export_pdf(step: Step, ctx: ExecutionContext) -> Any:
    """Export the document as a PDF file."""
    path = step.params["path"]
    doc = ctx.globals[_WORD_DOC]
    doc.ExportAsFixedFormat(path, 17)
    return path


WORD_ACTIONS = {
    "word.open": word_open,
    "word.save": word_save,
    "word.run_macro": word_run_macro,
    "word.bookmark.set": word_bookmark_set,
    "word.replace_all": word_replace_all,
    "word.export_pdf": word_export_pdf,
}
