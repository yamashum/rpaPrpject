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


def prompt_confirm(step: Step, ctx: ExecutionContext) -> Any:
    """Prompt the user for a yes/no confirmation.

    Parameters
    ----------
    message: str
        Message shown to the user.
    default: bool, optional
        Value returned when the user provides empty input. If ``True`` the
        prompt displays ``[Y/n]``; if ``False`` it displays ``[y/N]``. When
        ``None`` no default hint is shown.
    """

    message = step.params.get("message", "")
    default = step.params.get("default")
    if default is True:
        suffix = " [Y/n] "
    elif default is False:
        suffix = " [y/N] "
    else:
        suffix = " [y/n] "
    prompt = f"{message}{suffix}" if message else suffix
    choice = input(prompt).strip().lower()
    if choice == "" and default is not None:
        return bool(default)
    if choice in {"y", "yes"}:
        return True
    if choice in {"n", "no"}:
        return False
    # fall back to default if provided, otherwise False
    return bool(default) if default is not None else False


def prompt_select(step: Step, ctx: ExecutionContext) -> Any:
    """Prompt the user to select one of the provided options.

    Parameters
    ----------
    message: str
        Message shown to the user before the option list.
    options: list
        List of selectable options. The return value will be the selected
        option itself.
    default: Any, optional
        Default option returned when the user provides empty input. It may be
        either the index (1-based) of the option or the option value.
    """

    options = step.params.get("options") or []
    if not options:
        raise ValueError("prompt.select requires 'options'")
    message = step.params.get("message", "")
    default = step.params.get("default")

    lines = [f"{i + 1}. {opt}" for i, opt in enumerate(options)]
    prompt_lines = []
    if message:
        prompt_lines.append(message)
    prompt_lines.extend(lines)

    default_hint = ""
    if default is not None:
        if isinstance(default, int):
            if 1 <= default <= len(options):
                default_val = options[default - 1]
            elif 0 <= default < len(options):
                default_val = options[default]
            else:
                raise IndexError("default index out of range")
        else:
            default_val = default
        default_hint = f" [{default_val}]"
    else:
        default_val = None

    prompt_lines.append(f"Choice:{default_hint} ")
    prompt = "\n".join(prompt_lines)
    choice = input(prompt).strip()

    if choice == "" and default_val is not None:
        return default_val

    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(options):
            return options[idx - 1]
        raise IndexError("selection index out of range")

    for opt in options:
        if str(opt) == choice:
            return opt

    raise ValueError("invalid selection")


def _stub_action(step: Step, ctx: ExecutionContext) -> Any:
    """Placeholder for unimplemented UI actions."""
    print(f"{step.action} not implemented")
    return None


BUILTIN_ACTIONS = {
    "log": log,
    "set": set_var,
    "wait": wait,
    "prompt.input": prompt_input,
    "prompt.confirm": prompt_confirm,
    "prompt.select": prompt_select,
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

from .actions_web import WEB_ACTIONS
from .actions_office import OFFICE_ACTIONS

BUILTIN_ACTIONS.update(WEB_ACTIONS)
BUILTIN_ACTIONS.update(OFFICE_ACTIONS)
