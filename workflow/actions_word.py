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


WORD_ACTIONS = {
    "word.open": word_open,
    "word.save": word_save,
    "word.run_macro": word_run_macro,
}
