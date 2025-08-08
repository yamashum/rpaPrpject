"""Built-in placeholder actions for the workflow runner."""

from __future__ import annotations

import time
from typing import Any

from .flow import Step
from .runner import ExecutionContext
from .evaluator import safe_eval


def log(step: Step, ctx: ExecutionContext) -> Any:
    """Simple logging action."""
    message = step.params.get("message", "")
    print(message)
    return message


def set_var(step: Step, ctx: ExecutionContext) -> Any:
    """Assign a value to a variable in the requested scope."""
    name = step.params["name"]
    value_expr = step.params.get("value")
    scope = step.params.get("scope", "flow")
    value = value_expr
    if isinstance(value_expr, str):
        value = safe_eval(value_expr, ctx.all_vars())
    ctx.set_var(name, value, scope=scope)
    return value


def wait(step: Step, ctx: ExecutionContext) -> Any:
    """Pause execution for the specified milliseconds."""
    ms = step.params.get("ms", 1000)
    time.sleep(ms / 1000.0)
    return ms


BUILTIN_ACTIONS = {
    "log": log,
    "set": set_var,
    "wait": wait,
}
