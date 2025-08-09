"""Built-in placeholder actions for the workflow runner."""

from __future__ import annotations

import subprocess
import time
import getpass
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
    mask: bool, optional
        When ``True``, the user's input is not echoed back to the console.
    """
    message = step.params.get("message", "")
    default = step.params.get("default")
    mask = step.params.get("mask", False)
    prompt = f"{message} " if message else ""
    if default is not None:
        prompt += f"[{default}] "
    if mask:
        value = getpass.getpass(prompt)
    else:
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


def move(step: Step, ctx: ExecutionContext) -> Any:
    """Move a window to the specified coordinates."""

    selector = step.params.get("window") or step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    target = resolved["target"]
    x = step.params.get("x")
    y = step.params.get("y")
    if hasattr(target, "move") and x is not None and y is not None:
        try:
            target.move(x, y)
        except Exception:
            pass
    strategies = ctx.globals.setdefault("learned_selectors", [])
    strategies.append(resolved["strategy"])
    return True


def resize(step: Step, ctx: ExecutionContext) -> Any:
    """Resize a window to the specified width and height."""

    selector = step.params.get("window") or step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    target = resolved["target"]
    width = step.params.get("width")
    height = step.params.get("height")
    if hasattr(target, "resize") and width is not None and height is not None:
        try:
            target.resize(width, height)
        except Exception:
            pass
    strategies = ctx.globals.setdefault("learned_selectors", [])
    strategies.append(resolved["strategy"])
    return True


def wait_open(step: Step, ctx: ExecutionContext) -> Any:
    """Wait until a window matching ``selector`` becomes available."""

    selector = step.params.get("window") or step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    strategies = ctx.globals.setdefault("learned_selectors", [])
    strategies.append(resolved["strategy"])
    return resolved


def wait_close(step: Step, ctx: ExecutionContext) -> Any:
    """Wait until the window matching ``selector`` is closed."""

    selector = step.params.get("window") or step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    strategies = ctx.globals.setdefault("learned_selectors", [])
    strategies.append(resolved["strategy"])

    def _closed() -> bool:
        try:
            resolve_selector(selector)
            return False
        except Exception:
            return True

    if not _wait_until(_closed, timeout):
        raise TimeoutError("window still open")
    return True


def modal_wait_open(step: Step, ctx: ExecutionContext) -> Any:
    """Wait until a modal window opens and return the resolution."""

    selector = step.params.get("window") or step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    strategies = ctx.globals.setdefault("learned_selectors", [])
    strategies.append(resolved["strategy"])
    return resolved


def _ensure_ready(target: Any, timeout: int) -> None:
    """Wait until the element is visible, enabled and unobstructed."""

    if hasattr(target, "is_visible"):
        if not _wait_until(lambda: target.is_visible(), timeout):
            raise TimeoutError("element not visible")
    if hasattr(target, "is_enabled"):
        if not _wait_until(lambda: target.is_enabled(), timeout):
            raise TimeoutError("element not enabled")

    # Heuristic overlay detection.  Some UI frameworks expose properties like
    # ``has_overlay`` or ``is_obscured``.  We introspect for any attribute whose
    # name hints at the element being obscured and wait until it evaluates to
    # ``False``.  When such attribute stays truthy past the timeout a
    # ``RuntimeError`` is raised signalling that the element is covered by an
    # overlay.
    keywords = ("overlay", "obscur", "cover", "block")
    overlay_attr = None
    for name in dir(target):
        if name.startswith("_"):
            continue
        lname = name.lower()
        if any(key in lname for key in keywords):
            overlay_attr = name
            break

    if overlay_attr:
        attr = getattr(target, overlay_attr)

        def _has_overlay() -> bool:
            try:
                value = attr() if callable(attr) else attr
            except TypeError:
                return False
            except Exception:
                return True
            return bool(value)

        if not _wait_until(lambda: not _has_overlay(), timeout):
            raise RuntimeError("element obscured")


def _scroll_row_into_view(row: Any, timeout: int) -> None:
    """Attempt to bring a table row into view by scrolling."""

    visible = True
    if hasattr(row, "is_visible"):
        try:
            visible = bool(row.is_visible())
        except Exception:
            visible = True
    if visible:
        return

    if hasattr(row, "scroll_into_view"):
        try:
            row.scroll_into_view()
        except Exception:
            pass
    elif hasattr(row, "table") and hasattr(row.table, "scroll_to_row"):
        try:
            row.table.scroll_to_row(row)
        except Exception:
            pass

    if hasattr(row, "is_visible"):
        _wait_until(lambda: bool(row.is_visible()), timeout)


def _element_center(target: Any) -> tuple[int, int]:
    """Return the centre coordinates of ``target``."""

    x = getattr(target, "left", getattr(target, "x", 0))
    y = getattr(target, "top", getattr(target, "y", 0))
    w = getattr(target, "width", getattr(target, "w", 0))
    h = getattr(target, "height", getattr(target, "h", 0))
    return int(x + w / 2), int(y + h / 2)


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
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
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
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def right_click(step: Step, ctx: ExecutionContext) -> Any:
    """Perform a right click on the resolved element."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            x, y = _element_center(target)
            try:  # pragma: no cover - optional dependency
                import pyautogui  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            pyautogui.rightClick(x, y)
            return True
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def hover(step: Step, ctx: ExecutionContext) -> Any:
    """Move the mouse cursor over the resolved element."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    x = y = 0
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            x, y = _element_center(target)
            try:  # pragma: no cover - optional dependency
                import pyautogui  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            pyautogui.moveTo(x, y)
            return (x, y)
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return (x, y)


def scroll(step: Step, ctx: ExecutionContext) -> Any:
    """Scroll over the resolved element using ``pyautogui``."""

    selector = step.selector or step.params.get("selector") or {}
    clicks = step.params.get("clicks")
    if clicks is None:
        raise ValueError("scroll requires 'clicks'")
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            x, y = _element_center(target)
            try:  # pragma: no cover - optional dependency
                import pyautogui  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            pyautogui.moveTo(x, y)
            pyautogui.scroll(clicks)
            return clicks
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return clicks


def drag_drop(step: Step, ctx: ExecutionContext) -> Any:
    """Drag the source element onto the target element."""

    source_selector = step.selector or step.params.get("source")
    target_selector = step.params.get("target") or step.params.get("destination")
    if not source_selector or not target_selector:
        raise ValueError("drag_drop requires 'source' and 'target'")
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    duration = step.params.get("duration", 0.5)
    for attempt in range(retries + 1):
        source_resolved = _resolve_with_wait(source_selector, timeout)
        target_resolved = _resolve_with_wait(target_selector, timeout)
        src = source_resolved["target"]
        dst = target_resolved["target"]
        try:
            _ensure_ready(src, timeout)
            _ensure_ready(dst, timeout)
            sx, sy = _element_center(src)
            dx, dy = _element_center(dst)
            try:  # pragma: no cover - optional dependency
                import pyautogui  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            pyautogui.moveTo(sx, sy)
            pyautogui.dragTo(dx, dy, duration=duration, button="left")
            return True
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
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
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
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
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
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
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def click_xy(step: Step, ctx: ExecutionContext) -> Any:
    """Click at coordinates using ``pyautogui`` with optional basis.

    Parameters ``x`` and ``y`` specify the coordinates. When ``basis`` is
    ``"Element"`` or ``"Window"`` the coordinates are treated as relative to the
    respective origin and translated to screen coordinates before the click.
    When ``preview`` is truthy, the translated coordinates are returned without
    performing the click.
    """

    x = step.params.get("x")
    y = step.params.get("y")
    if x is None or y is None:
        raise ValueError("click_xy requires 'x' and 'y'")

    basis = (step.params.get("basis") or "Screen").lower()
    preview = step.params.get("preview", False)

    if basis == "element":
        selector = step.selector or step.params.get("selector") or {}
        timeout = step.params.get("timeout", 3000)
        if selector:
            resolved = _resolve_with_wait(selector, timeout)
            target = resolved["target"]
            origin_x = getattr(target, "left", getattr(target, "x", 0))
            origin_y = getattr(target, "top", getattr(target, "y", 0))
            x += origin_x
            y += origin_y
    elif basis == "window":
        window = ctx.globals.get("window")
        if window is not None:
            origin_x = getattr(window, "left", getattr(window, "x", 0))
            origin_y = getattr(window, "top", getattr(window, "y", 0))
            x += origin_x
            y += origin_y

    if preview:
        return (x, y)

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
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
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


def select_row(step: Step, ctx: ExecutionContext) -> Any:
    """Select a table row, scrolling it into view if necessary."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        row = resolved["target"]
        try:
            _scroll_row_into_view(row, timeout)
            _ensure_ready(row, timeout)
            if hasattr(row, "select"):
                row.select()
            elif hasattr(row, "click"):
                row.click()
            else:
                raise AttributeError("row not selectable")
            return True
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def double_click_row(step: Step, ctx: ExecutionContext) -> Any:
    """Double-click a table row, scrolling it into view if necessary."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        row = resolved["target"]
        try:
            _scroll_row_into_view(row, timeout)
            _ensure_ready(row, timeout)
            if hasattr(row, "double_click"):
                row.double_click()
            elif hasattr(row, "click"):
                row.click()
                row.click()
            else:
                raise AttributeError("row not double clickable")
            return True
        except Exception as exc:
            msg = str(exc).lower()
            if "overlay" in msg or "obscur" in msg or "cover" in msg or "block" in msg:
                raise RuntimeError("Element obscured") from exc
            if attempt >= retries:
                raise
            time.sleep(0.1)
    return True


def find_image(step: Step, ctx: ExecutionContext) -> Any:
    """Locate ``path`` on screen using ``pyautogui``."""

    path = step.params.get("path") or step.params.get("image")
    if not path:
        raise ValueError("find_image requires 'path'")
    region = step.params.get("region")
    timeout = step.params.get("timeout", 3000)
    interval = step.params.get("interval", 0.5)
    scale = step.params.get("scale")
    tolerance = step.params.get("tolerance")
    dpi = step.params.get("dpi")
    try:  # pragma: no cover - optional dependency
        import pyautogui  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyautogui not installed") from exc
    end = time.time() + timeout / 1000.0
    while time.time() < end:
        box = pyautogui.locateOnScreen(
            path, region=region, scale=scale, tolerance=tolerance, dpi=dpi
        )
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


def _send_hotkey(*keys: str) -> None:
    """Send a hotkey combination using ``pyautogui``.

    This helper centralises the optional dependency handling so callers only
    need to provide the key sequence.  A :class:`RuntimeError` is raised when
    ``pyautogui`` is unavailable which mirrors the behaviour of other helper
    functions in this module.
    """

    try:  # pragma: no cover - optional dependency
        import pyautogui  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyautogui not installed") from exc
    pyautogui.hotkey(*keys)


def ime_on(step: Step, ctx: ExecutionContext) -> Any:
    """Turn the Input Method Editor on.

    The operation is simulated by emitting the ``Ctrl+Space`` hotkey which is a
    common toggle for IME on many platforms.  The current state is stored under
    ``ctx.globals['ime_state']`` for testability.  When ``layout`` is provided it
    is forwarded to :func:`switch_layout` to change the keyboard layout prior to
    enabling the IME.
    """

    layout = step.params.get("layout")
    if layout:
        switch_layout(Step(id=step.id, action="layout.switch", params={"layout": layout}), ctx)
    _send_hotkey("ctrl", "space")
    ctx.globals["ime_state"] = "on"
    return True


def ime_off(step: Step, ctx: ExecutionContext) -> Any:
    """Turn the Input Method Editor off via ``Ctrl+Space`` hotkey."""

    _send_hotkey("ctrl", "space")
    ctx.globals["ime_state"] = "off"
    return True


def switch_layout(step: Step, ctx: ExecutionContext) -> Any:
    """Switch the keyboard layout using ``Alt+Shift`` hotkey."""

    layout = step.params.get("layout")
    if not layout:
        raise ValueError("layout.switch requires 'layout'")
    _send_hotkey("alt", "shift")
    ctx.globals["keyboard_layout"] = layout
    return layout


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
    "right_click",
    "hover",
    "scroll",
    "drag_drop",
    "type_text",
    "set_value",
    "select",
    "check",
    "uncheck",
    "find_image",
    "ocr_read",
    "click_xy",
    "table.find_row",
    "row.select",
    "row.double_click",
    "move",
    "resize",
    "wait_open",
    "wait_close",
    "modal_wait_open",
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
        "right_click": right_click,
        "hover": hover,
        "scroll": scroll,
        "drag_drop": drag_drop,
        "select": select,
        "check": check,
        "uncheck": uncheck,
        "set_value": set_value,
        "type_text": type_text,
        "click_xy": click_xy,
        "find_image": find_image,
        "ocr_read": ocr_read,
        "table.find_row": find_table_row,
        "row.select": select_row,
        "row.double_click": double_click_row,
        "move": move,
        "resize": resize,
        "wait_open": wait_open,
        "wait_close": wait_close,
        "modal_wait_open": modal_wait_open,
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

BUILTIN_ACTIONS.update(
    {
        "ime.on": ime_on,
        "ime.off": ime_off,
        "layout.switch": switch_layout,
    }
)
