"""Built-in placeholder actions for the workflow runner."""

from __future__ import annotations

import subprocess
import time
from typing import Any, Callable, Dict

from .flow import Step
from .runner import ExecutionContext
from .safe_eval import safe_eval
from .selector import resolve as resolve_selector


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
        value = safe_eval(value_expr, env)
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


# ----- UI helpers and actions -------------------------------------------------


def _wait_until(predicate: Callable[[], bool], timeout_ms: int, interval: float = 0.1) -> bool:
    """Poll ``predicate`` until it returns True or timeout expires."""

    end = time.time() + timeout_ms / 1000.0
    while time.time() < end:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _resolve_with_wait(selector: Dict[str, Any], timeout_ms: int) -> Dict[str, Any]:
    """Resolve a selector retrying until it succeeds or times out."""

    end = time.time() + timeout_ms / 1000.0
    last_exc: Exception | None = None
    while time.time() < end:
        try:
            return resolve_selector(selector)
        except Exception as exc:
            last_exc = exc
            time.sleep(0.1)
    if last_exc:
        raise last_exc
    raise TimeoutError("element not found")


def launch(step: Step, ctx: ExecutionContext) -> Any:
    """Launch an application specified by ``path`` and optional ``args``."""

    path = step.params.get("path") or step.params.get("cmd")
    if not path:
        raise ValueError("launch requires 'path'")
    args = step.params.get("args", [])
    if isinstance(args, str):
        args = [args]
    proc = subprocess.Popen([path, *args])
    return proc.pid


def activate(step: Step, ctx: ExecutionContext) -> Any:
    """Bring a window matching ``selector`` to the foreground."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    target = resolved["target"]
    if hasattr(target, "activate"):
        target.activate()
    return True


def _ensure_ready(target: Any, timeout: int) -> None:
    """Wait until the element is visible and enabled."""

    if hasattr(target, "is_visible"):
        if not _wait_until(lambda: target.is_visible(), timeout):
            raise TimeoutError("element not visible")
    if hasattr(target, "is_enabled"):
        if not _wait_until(lambda: target.is_enabled(), timeout):
            raise TimeoutError("element not enabled")


def click(step: Step, ctx: ExecutionContext) -> Any:
    """Click an element resolved from ``selector`` with retries."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            if hasattr(target, "click"):
                target.click()
                return True
            raise AttributeError("target not clickable")
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def attach(step: Step, ctx: ExecutionContext) -> Any:
    """Resolve ``selector`` recording the strategy used.

    The resolved element and strategy are returned in the same shape as
    :func:`resolve_selector`.  The chosen strategy is appended to
    ``ctx.globals['learned_selectors']`` mirroring the behaviour of the
    previous stub implementation so tests can inspect the resolution path.
    """

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    strategies = ctx.globals.setdefault("learned_selectors", [])
    strategies.append(resolved["strategy"])
    return resolved


def double_click(step: Step, ctx: ExecutionContext) -> Any:
    """Perform a double click on the resolved element."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            if hasattr(target, "double_click"):
                target.double_click()
            elif hasattr(target, "click"):
                target.click()
                target.click()
            else:
                raise AttributeError("target not double clickable")
            return True
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def select(step: Step, ctx: ExecutionContext) -> Any:
    """Select an item on a UI element."""

    selector = step.selector or step.params.get("selector") or {}
    item = step.params.get("item") or step.params.get("value")
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            if hasattr(target, "select"):
                target.select(item)
            elif hasattr(target, "select_item"):
                target.select_item(item)
            else:
                raise AttributeError("target not selectable")
            return item
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return item


def _set_checked(target: Any, desired: bool) -> None:
    """Helper to set checkbox state."""

    def _state() -> bool | None:
        if hasattr(target, "is_checked"):
            try:
                return bool(target.is_checked())
            except Exception:
                return None
        if hasattr(target, "get_toggle_state"):
            try:
                return bool(target.get_toggle_state())
            except Exception:
                return None
        if hasattr(target, "checked"):
            try:
                return bool(getattr(target, "checked"))
            except Exception:
                return None
        return None

    current = _state()
    if current is not None and current == desired:
        return
    if desired:
        if hasattr(target, "check"):
            target.check()
        elif hasattr(target, "set_state"):
            target.set_state(True)
        elif hasattr(target, "toggle"):
            target.toggle()
        elif hasattr(target, "click"):
            target.click()
        else:
            raise AttributeError("target not checkable")
    else:
        if hasattr(target, "uncheck"):
            target.uncheck()
        elif hasattr(target, "set_state"):
            target.set_state(False)
        elif hasattr(target, "toggle"):
            target.toggle()
        elif hasattr(target, "click"):
            target.click()
        else:
            raise AttributeError("target not checkable")


def check(step: Step, ctx: ExecutionContext) -> Any:
    """Ensure the element represented by ``selector`` is checked."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            _set_checked(target, True)
            return True
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def uncheck(step: Step, ctx: ExecutionContext) -> Any:
    """Ensure the element represented by ``selector`` is unchecked."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            _set_checked(target, False)
            return True
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def click_xy(step: Step, ctx: ExecutionContext) -> Any:
    """Click at absolute coordinates using ``pyautogui``."""

    x = step.params.get("x")
    y = step.params.get("y")
    if x is None or y is None:
        raise ValueError("click_xy requires 'x' and 'y'")
    try:  # pragma: no cover - optional dependency
        import pyautogui  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyautogui not installed") from exc
    pyautogui.click(x, y)
    return (x, y)


def set_value(step: Step, ctx: ExecutionContext) -> Any:
    """Set text/value on an element specified by ``selector``."""

    selector = step.selector or step.params.get("selector") or {}
    value = step.params.get("value", "")
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            if hasattr(target, "set_text"):
                target.set_text(value)
            elif hasattr(target, "type_text"):
                target.type_text(value)
            else:
                raise AttributeError("target not editable")
            return value
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return value


def type_text(step: Step, ctx: ExecutionContext) -> Any:
    """Alias for :func:`set_value`."""

    return set_value(step, ctx)


def find_table_row(step: Step, ctx: ExecutionContext) -> Any:
    """Return the first table row matching ``criteria``."""

    selector = step.selector or step.params.get("selector") or {}
    criteria = step.params.get("criteria", {})
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    table = resolved["target"]
    if not hasattr(table, "find_row"):
        raise AttributeError("target has no find_row")
    return table.find_row(criteria)


def find_image(step: Step, ctx: ExecutionContext) -> Any:
    """Locate ``path`` on screen using ``pyautogui``."""

    path = step.params.get("path") or step.params.get("image")
    if not path:
        raise ValueError("find_image requires 'path'")
    region = step.params.get("region")
    timeout = step.params.get("timeout", 3000)
    interval = step.params.get("interval", 0.5)
    try:  # pragma: no cover - optional dependency
        import pyautogui  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyautogui not installed") from exc
    end = time.time() + timeout / 1000.0
    while time.time() < end:
        box = pyautogui.locateOnScreen(path, region=region)
        if box:
            return box
        time.sleep(interval)
    raise TimeoutError("image not found")


def ocr_read(step: Step, ctx: ExecutionContext) -> Any:
    """Run OCR on an image at ``path`` using ``pytesseract``."""

    path = step.params.get("path")
    if not path:
        raise ValueError("ocr_read requires 'path'")
    lang = step.params.get("lang", "eng")
    try:  # pragma: no cover - optional dependency
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pytesseract not installed") from exc
    img = Image.open(path)
    text = pytesseract.image_to_string(img, lang=lang)
    return text.strip()


def _stub_action(step: Step, ctx: ExecutionContext) -> Any:
    """Placeholder for unimplemented UI actions.

    The stub uses :func:`resolve_selector` to attempt element resolution based on
    the step's ``selector`` definition.  Successful resolutions are recorded on
    the execution context under ``ctx.globals['learned_selectors']`` so tests can
    verify which strategy was ultimately used.
    """

    selector = step.selector or step.params.get("selector")
    if isinstance(selector, dict):
        result = resolve_selector(selector)
        strategies = ctx.globals.setdefault("learned_selectors", [])
        strategies.append(result["strategy"])
        return result
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

# Concrete implementations overriding stubs
BUILTIN_ACTIONS.update(
    {
        "launch": launch,
        "attach": attach,
        "activate": activate,
        "click": click,
        "double_click": double_click,
        "select": select,
        "check": check,
        "uncheck": uncheck,
        "set_value": set_value,
        "type_text": type_text,
        "click_xy": click_xy,
        "find_image": find_image,
        "ocr_read": ocr_read,
        "table.find_row": find_table_row,
    }
)

from .actions_web import WEB_ACTIONS
from .actions_office import OFFICE_ACTIONS
from .actions_word import WORD_ACTIONS
from .actions_outlook import OUTLOOK_ACTIONS

BUILTIN_ACTIONS.update(WEB_ACTIONS)
BUILTIN_ACTIONS.update(OFFICE_ACTIONS)
BUILTIN_ACTIONS.update(WORD_ACTIONS)
BUILTIN_ACTIONS.update(OUTLOOK_ACTIONS)
