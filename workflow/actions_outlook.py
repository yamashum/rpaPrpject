"""Outlook automation actions using win32com."""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    import win32com.client as win32
except Exception:  # pragma: no cover - optional dependency
    win32 = None  # type: ignore

from .flow import Step
from .runner import ExecutionContext

# keys for storing outlook app and item in execution context
_OUTLOOK_APP = "_outlook_app"
_OUTLOOK_ITEM = "_outlook_item"


def outlook_open(step: Step, ctx: ExecutionContext) -> Any:
    """Open an Outlook item from a file."""
    if win32 is None:
        raise RuntimeError("win32com.client is not installed")
    path = step.params["path"]
    app = ctx.globals.get(_OUTLOOK_APP)
    if app is None:
        app = win32.Dispatch("Outlook.Application")
        ctx.globals[_OUTLOOK_APP] = app
    item = app.Session.OpenSharedItem(path)
    ctx.globals[_OUTLOOK_ITEM] = item
    return path


def outlook_save(step: Step, ctx: ExecutionContext) -> Any:
    """Save the currently opened Outlook item."""
    item = ctx.globals[_OUTLOOK_ITEM]
    path = step.params.get("path")
    if path:
        item.SaveAs(path)
        return path
    item.Save()
    return True


def outlook_run_macro(step: Step, ctx: ExecutionContext) -> Any:
    """Run a macro in the Outlook application."""
    macro = step.params["name"]
    app = ctx.globals[_OUTLOOK_APP]
    return app.Application.Run(macro)


OUTLOOK_ACTIONS = {
    "outlook.open": outlook_open,
    "outlook.save": outlook_save,
    "outlook.run_macro": outlook_run_macro,
}
