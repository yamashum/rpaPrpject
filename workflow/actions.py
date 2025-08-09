"""Built-in placeholder actions for the workflow runner."""

from __future__ import annotations

import time
from typing import Any

from .flow import Step
from .runner import ExecutionContext
from .safe_eval import safe_eval


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
        env = ctx.all_vars()
        value = safe_eval(value_expr, {"vars": env, **env})
    ctx.set_var(name, value, scope=scope)
    return value


def wait(step: Step, ctx: ExecutionContext) -> Any:
    """Pause execution for the specified milliseconds."""
    ms = step.params.get("ms", 1000)
    time.sleep(ms / 1000.0)
    return ms


def prompt_input(step: Step, ctx: ExecutionContext) -> Any:
    """Prompt the user for input during execution.

    Parameters
    ----------
    message: str
        Message shown to the user.
    default: Any, optional
        Default value if the user provides empty input.
    """
    message = step.params.get("message", "")
    default = step.params.get("default")
    prompt = f"{message} " if message else ""
    if default is not None:
        prompt += f"[{default}] "
    value = input(prompt)
    if value == "" and default is not None:
        value = default
    return value


def _stub_action(step: Step, ctx: ExecutionContext) -> Any:
    """Placeholder for unimplemented UI actions."""
    print(f"{step.action} not implemented")
    return None


BUILTIN_ACTIONS = {
    "log": log,
    "set": set_var,
    "wait": wait,
    "prompt.input": prompt_input,
}

_UI_ACTIONS = [
    "launch",
    "attach",
    "activate",
    "click",
    "double_click",
    "type_text",
    "set_value",
    "select",
    "check",
    "uncheck",
    "find_image",
    "ocr_read",
    "click_xy",
    "open",
    "write_cell",
    "save",
]

for _name in _UI_ACTIONS:
    BUILTIN_ACTIONS[_name] = _stub_action
