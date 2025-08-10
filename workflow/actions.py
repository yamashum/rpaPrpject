"""Built-in placeholder actions for the workflow runner."""

from __future__ import annotations

import subprocess
import time
import getpass
import random
from typing import Any, Callable, Dict

try:
    import psutil
except Exception:  # pragma: no cover - psutil may be missing in minimal envs
    psutil = None

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


def _wait_for_idle(
    cpu_threshold: float = 10.0,
    disk_threshold: float = 1024 * 1024,
    timeout_ms: int = 3000,
) -> bool:
    """Wait until system CPU and disk usage fall below thresholds."""

    if psutil is None:
        raise RuntimeError("psutil is required for idle waiting")

    end = time.time() + timeout_ms / 1000.0
    prev = psutil.disk_io_counters()
    prev_time = time.time()
    while time.time() < end:
        cpu = psutil.cpu_percent(interval=0.1)
        now = time.time()
        io = psutil.disk_io_counters()
        elapsed = now - prev_time
        delta = (io.read_bytes + io.write_bytes) - (
            prev.read_bytes + prev.write_bytes
        )
        rate = delta / elapsed if elapsed else float("inf")
        if cpu < cpu_threshold and rate < disk_threshold:
            return True
        prev, prev_time = io, now
    raise TimeoutError("system busy")


def _wait_splash_gone(selector: Dict[str, Any], timeout_ms: int) -> bool:
    """Wait until ``selector`` cannot be resolved anymore."""

    def _gone() -> bool:
        try:
            resolve_selector(selector)
            return False
        except Exception:
            return True

    if not _wait_until(_gone, timeout_ms):
        raise TimeoutError("splash still visible")
    return True


def launch(step: Step, ctx: ExecutionContext) -> Any:
    """Launch an application specified by ``path`` and optional ``args``."""

    path = step.params.get("path") or step.params.get("cmd")
    if not path:
        raise ValueError("launch requires 'path'")
    args = step.params.get("args", [])
    if isinstance(args, str):
        args = [args]
    proc = subprocess.Popen([path, *args])
    selector = (
        step.params.get("window") or step.selector or step.params.get("selector")
    )
    if selector:
        wait_params: Dict[str, Any] = {
            "selector": selector,
            "timeout": step.params.get("timeout", 3000),
        }
        for key in ("splash", "cpu_threshold", "disk_threshold", "idle_timeout"):
            if key in step.params:
                wait_params[key] = step.params[key]
        wait_step = Step(id="wait.open", params=wait_params)
        wait_open(wait_step, ctx)
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
    splash = step.params.get("splash") or step.params.get("spinner")
    if splash:
        _wait_splash_gone(splash, timeout)

    cpu_th = step.params.get("cpu_threshold")
    disk_th = step.params.get("disk_threshold")
    idle_timeout = step.params.get("idle_timeout", timeout)
    if cpu_th is not None or disk_th is not None:
        _wait_for_idle(
            cpu_th if cpu_th is not None else 10.0,
            disk_th if disk_th is not None else 1024 * 1024,
            idle_timeout,
        )
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


def _element_has_overlay(target: Any) -> bool:
    """Return True if ``target`` appears to be covered by an overlay."""

    keywords = ("overlay", "obscur", "cover", "block")
    for name in dir(target):
        if name.startswith("_"):
            continue
        lname = name.lower()
        if any(key in lname for key in keywords):
            attr = getattr(target, name)
            try:
                value = attr() if callable(attr) else attr
            except TypeError:
                return False
            except Exception:
                return True
            return bool(value)
    return False


def _ensure_ready(target: Any, timeout: int) -> None:
    """Wait until the element is visible, enabled and unobstructed."""

    start = time.time()
    while True:
        if hasattr(target, "is_visible"):
            if not _wait_until(lambda: target.is_visible(), timeout):
                raise TimeoutError("element not visible")
        if hasattr(target, "is_enabled"):
            if not _wait_until(lambda: target.is_enabled(), timeout):
                raise TimeoutError("element not enabled")

        if _element_has_overlay(target):
            elapsed = int((time.time() - start) * 1000)
            remaining = max(0, timeout - elapsed)
            if remaining <= 0 or not _wait_until(lambda: not _element_has_overlay(target), remaining):
                raise RuntimeError("element obscured")
            # Overlay disappeared, re-check visibility/enabled
            continue
        break

    # Verify the element can be interacted with using hit-testing or pixel checks.
    if hasattr(target, "hit_test"):
        def _hit() -> bool:
            try:
                return bool(target.hit_test())
            except Exception:
                return False
        if not _wait_until(_hit, timeout):
            raise RuntimeError("element not hit-testable")
    elif hasattr(target, "hit_testable"):
        attr = target.hit_testable
        def _hit_attr() -> bool:
            try:
                return bool(attr() if callable(attr) else attr)
            except Exception:
                return False
        if not _wait_until(_hit_attr, timeout):
            raise RuntimeError("element not hit-testable")
    else:
        coords = None
        if hasattr(target, "clickable_point"):
            cp = target.clickable_point
            try:
                coords = cp() if callable(cp) else cp
            except Exception:
                coords = None
        elif hasattr(target, "rect"):
            rect_attr = target.rect
            try:
                rect = rect_attr() if callable(rect_attr) else rect_attr
                if rect and len(rect) >= 4:
                    x = int((rect[0] + rect[2]) / 2)
                    y = int((rect[1] + rect[3]) / 2)
                    coords = (x, y)
            except Exception:
                coords = None
        if coords:
            x, y = coords
            try:
                import pyautogui as pag  # type: ignore
            except Exception:
                pass
            else:
                def _pixel_visible() -> bool:
                    try:
                        pag.pixel(x, y)
                        return True
                    except Exception:
                        return False
                if not _wait_until(_pixel_visible, timeout):
                    raise RuntimeError("element not hit-testable")


def _scroll_row_into_view(row: Any, timeout: int) -> None:
    """Attempt to bring a table row into view by scrolling."""

    def _is_visible() -> bool:
        if hasattr(row, "is_visible"):
            try:
                return bool(row.is_visible())
            except Exception:
                return True
        return True

    def _is_offscreen() -> bool:
        if hasattr(row, "is_offscreen"):
            try:
                return bool(row.is_offscreen())
            except Exception:
                return False
        return False

    if _is_visible() and not _is_offscreen():
        return

    start = time.time()
    max_scrolls = 10

    for _ in range(max_scrolls):
        remaining = timeout - int((time.time() - start) * 1000)
        if remaining <= 0:
            break

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

        if hasattr(row, "is_visible") or hasattr(row, "is_offscreen"):
            if _wait_until(lambda: _is_visible() and not _is_offscreen(), remaining):
                return
        else:
            time.sleep(0.1)

    if hasattr(row, "is_visible"):
        _wait_until(lambda: bool(row.is_visible()), max(0, timeout - int((time.time() - start) * 1000)))


def _element_center(target: Any) -> tuple[int, int]:
    """Return the centre coordinates of ``target``."""

    x = getattr(target, "left", getattr(target, "x", 0))
    y = getattr(target, "top", getattr(target, "y", 0))
    w = getattr(target, "width", getattr(target, "w", 0))
    h = getattr(target, "height", getattr(target, "h", 0))
    return int(x + w / 2), int(y + h / 2)


def _human_path(
    sx: int,
    sy: int,
    dx: int,
    dy: int,
    steps: int = 20,
    curve: bool = False,
    humanize: bool = False,
):
    """Yield intermediate points between ``(sx, sy)`` and ``(dx, dy)``.

    When ``curve`` is ``True`` a random control point is introduced so the path
    follows a quadratic Bézier curve.  When ``humanize`` is ``True`` small
    random offsets are added to each point."""

    if curve:
        mx, my = (sx + dx) / 2.0, (sy + dy) / 2.0
        offset = random.uniform(-0.25, 0.25)
        cx = mx + (dy - sy) * offset
        cy = my - (dx - sx) * offset
    for i in range(1, steps + 1):
        t = i / steps
        if curve:
            x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t**2 * dx
            y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t**2 * dy
        else:
            x = sx + (dx - sx) * t
            y = sy + (dy - sy) * t
        if humanize:
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)
        yield int(x), int(y)


def _move_mouse_to(
    x: int,
    y: int,
    duration: float = 0.0,
    curve: bool = False,
    humanize: bool = False,
    pag=None,
) -> None:
    """Move the mouse cursor to ``(x, y)`` using optional path tweaks."""

    if pag is None:  # pragma: no cover - optional dependency
        try:
            import pyautogui as pag  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("pyautogui not installed") from exc
    if hasattr(pag, "position"):
        sx, sy = pag.position()
    else:
        sx, sy = 0, 0
    steps = max(int(duration * 60), 1)
    interval = duration / steps if duration else 0
    for px, py in _human_path(sx, sy, x, y, steps, curve, humanize):
        try:
            pag.moveTo(px, py, duration=interval)
        except TypeError:  # pragma: no cover - simple stubs in tests
            pag.moveTo(px, py)
            if interval:
                time.sleep(interval)


def _drag_mouse(
    sx: int,
    sy: int,
    dx: int,
    dy: int,
    duration: float = 0.5,
    curve: bool = False,
    humanize: bool = False,
    pag=None,
) -> None:
    """Drag from ``(sx, sy)`` to ``(dx, dy)`` with optional humanisation."""

    if pag is None:  # pragma: no cover - optional dependency
        try:
            import pyautogui as pag  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("pyautogui not installed") from exc
    pag.moveTo(sx, sy)
    pag.mouseDown(button="left")
    steps = max(int(duration * 60), 1)
    interval = duration / steps if duration else 0
    for px, py in _human_path(sx, sy, dx, dy, steps, curve, humanize):
        try:
            pag.moveTo(px, py, duration=interval)
        except TypeError:  # pragma: no cover - simple stubs in tests
            pag.moveTo(px, py)
            if interval:
                time.sleep(interval)
    pag.mouseUp(button="left")


def click(step: Step, ctx: ExecutionContext) -> Any:
    """Click an element resolved from ``selector`` with retries.

    Parameters ``curve`` and ``humanize`` (both optional) control whether the
    mouse cursor moves to the element following a curved path and with small
    random jitters before clicking via ``pyautogui``.  When unset the element's
    native ``click`` method is used instead."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    curve = step.params.get("curve", False)
    humanize = step.params.get("humanize", False)
    duration = step.params.get("duration", 0.0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            if curve or humanize or duration:
                x, y = _element_center(target)
                try:  # pragma: no cover - optional dependency
                    import pyautogui as pag  # type: ignore
                except Exception as exc:  # pragma: no cover - optional dependency
                    raise RuntimeError("pyautogui not installed") from exc
                _move_mouse_to(x, y, duration, curve, humanize, pag)
                pag.click()
                return True
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
    """Perform a double click on the resolved element.

    Supports the same ``curve``/``humanize`` parameters as :func:`click` when
    ``pyautogui`` is used to perform the double click."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    curve = step.params.get("curve", False)
    humanize = step.params.get("humanize", False)
    duration = step.params.get("duration", 0.0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            if curve or humanize or duration:
                x, y = _element_center(target)
                try:  # pragma: no cover - optional dependency
                    import pyautogui as pag  # type: ignore
                except Exception as exc:  # pragma: no cover - optional dependency
                    raise RuntimeError("pyautogui not installed") from exc
                _move_mouse_to(x, y, duration, curve, humanize, pag)
                pag.doubleClick()
            elif hasattr(target, "double_click"):
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
    """Perform a right click on the resolved element.

    Optional ``curve``/``humanize`` parameters influence how the cursor moves to
    the element before the click."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    curve = step.params.get("curve", False)
    humanize = step.params.get("humanize", False)
    duration = step.params.get("duration", 0.0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            x, y = _element_center(target)
            try:  # pragma: no cover - optional dependency
                import pyautogui as pag  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            if curve or humanize or duration:
                _move_mouse_to(x, y, duration, curve, humanize, pag)
                if hasattr(pag, "click"):
                    pag.click(button="right")
                else:
                    pag.rightClick(x, y)
            else:
                pag.rightClick(x, y)
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
    """Move the mouse cursor over the resolved element.

    ``curve`` and ``humanize`` options modify the cursor path."""

    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    curve = step.params.get("curve", False)
    humanize = step.params.get("humanize", False)
    duration = step.params.get("duration", 0.0)
    x = y = 0
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            x, y = _element_center(target)
            try:  # pragma: no cover - optional dependency
                import pyautogui as pag  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            _move_mouse_to(x, y, duration, curve, humanize, pag)
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
    """Scroll over the resolved element using ``pyautogui``.

    ``curve`` and ``humanize`` affect the cursor movement before scrolling."""

    selector = step.selector or step.params.get("selector") or {}
    clicks = step.params.get("clicks")
    if clicks is None:
        raise ValueError("scroll requires 'clicks'")
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    curve = step.params.get("curve", False)
    humanize = step.params.get("humanize", False)
    duration = step.params.get("duration", 0.0)
    for attempt in range(retries + 1):
        resolved = _resolve_with_wait(selector, timeout)
        target = resolved["target"]
        try:
            _ensure_ready(target, timeout)
            x, y = _element_center(target)
            try:  # pragma: no cover - optional dependency
                import pyautogui as pag  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            _move_mouse_to(x, y, duration, curve, humanize, pag)
            pag.scroll(clicks)
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
    """Drag the source element onto the target element.

    ``curve`` and ``humanize`` parameters alter the mouse path during the drag
    operation."""

    source_selector = step.selector or step.params.get("source")
    target_selector = step.params.get("target") or step.params.get("destination")
    if not source_selector or not target_selector:
        raise ValueError("drag_drop requires 'source' and 'target'")
    timeout = step.params.get("timeout", 3000)
    retries = step.params.get("retry", 0)
    duration = step.params.get("duration", 0.5)
    curve = step.params.get("curve", False)
    humanize = step.params.get("humanize", False)
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
                import pyautogui as pag  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dependency
                raise RuntimeError("pyautogui not installed") from exc
            if curve or humanize:
                _drag_mouse(sx, sy, dx, dy, duration, curve, humanize, pag)
            else:
                pag.moveTo(sx, sy)
                pag.dragTo(dx, dy, duration=duration, button="left")
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


def menu_select(step: Step, ctx: ExecutionContext) -> Any:
    """Select a menu item following the given path."""

    selector = step.selector or step.params.get("selector") or {}
    path = step.params.get("path") or step.params.get("menu")
    if path is None:
        raise ValueError("menu.select requires 'path'")
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    target = resolved["target"]
    if isinstance(path, str):
        delimiter = step.params.get("delimiter", ">")
        parts = [p.strip() for p in path.split(delimiter) if p.strip()]
    elif isinstance(path, (list, tuple)):
        parts = [str(p).strip() for p in path]
    else:
        raise TypeError("path must be a string or list")
    menu_path = "->".join(parts)
    if hasattr(target, "menu_select"):
        target.menu_select(menu_path)
    elif hasattr(target, "select_menu"):
        target.select_menu(menu_path)
    else:
        raise AttributeError("target has no menu_select")
    strategies = ctx.globals.setdefault("learned_selectors", [])
    strategies.append(resolved["strategy"])
    return True


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


def table_wizard(step: Step, ctx: ExecutionContext) -> Any:
    """Parse simple column queries and delegate to :func:`find_table_row`.

    Parameters
    ----------
    query: dict | str
        Either a mapping of column specifiers to values or a comma separated
        string of ``column=value`` pairs.  Column specifiers may be header names
        or zero-based indices.  Only equality checks are supported by the
        wizard.  The generated criteria are forwarded to
        :func:`find_table_row`.
    select: bool, optional
        When ``True`` and the matched row exposes a ``select`` method it will be
        invoked after locating the row.
    """

    query = step.params.get("query")
    if not query:
        raise ValueError("table.wizard requires 'query'")

    criteria: Dict[Any, Dict[str, Any]] = {}
    if isinstance(query, str):
        parts = [p.strip() for p in query.split(",") if p.strip()]
        for part in parts:
            if "=" not in part:
                raise ValueError(f"invalid query segment: {part}")
            col, val = [x.strip() for x in part.split("=", 1)]
            if col.isdigit():
                col = int(col)
            criteria[col] = {"equals": val}
    elif isinstance(query, dict):
        for col, val in query.items():
            if isinstance(col, str) and col.isdigit():
                col = int(col)
            criteria[col] = {"equals": val}
    else:
        raise TypeError("query must be str or dict")

    timeout = step.params.get("timeout", 3000)
    find_step = Step(
        id=step.id,
        action="table.find_row",
        selector=step.selector,
        params={"criteria": criteria, "timeout": timeout},
    )
    row = find_table_row(find_step, ctx)

    if step.params.get("select") and hasattr(row, "select"):
        row.select()

    return row


def find_table_row(step: Step, ctx: ExecutionContext) -> Any:
    """Return the first table row matching ``criteria``.

    ``criteria`` may be either a mapping of column specifiers to condition or a
    list of condition dictionaries.  A column can be referenced by header name
    or zero-based index.  Each condition supports one of ``equals``,
    ``contains`` or ``regex``.  A plain mapping ``{"Name": "Bob"}`` is treated
    as ``{"column": "Name", "equals": "Bob"}``.

    Examples
    --------
    >>> criteria = {"Name": {"equals": "Bob"}}
    >>> criteria = [
    ...     {"column": 0, "contains": "2023"},
    ...     {"column": "Status", "regex": r"^ok$"},
    ... ]
    """

    import re

    def _normalize(criteria: Any) -> list[dict[str, Any]]:
        if isinstance(criteria, dict):
            result: list[dict[str, Any]] = []
            for col, cond in criteria.items():
                if isinstance(cond, dict):
                    item = {"column": col}
                    item.update(cond)
                else:
                    item = {"column": col, "equals": cond}
                result.append(item)
            return result
        if isinstance(criteria, list):
            result = []
            for cond in criteria:
                if not isinstance(cond, dict) or "column" not in cond:
                    raise ValueError("criteria items must be dicts with 'column'")
                result.append(cond)
            return result
        raise TypeError("criteria must be dict or list")

    def _get_rows(tbl: Any) -> list[Any]:
        rows = getattr(tbl, "rows", None)
        if callable(rows):
            rows = rows()
        if rows is None:
            raise AttributeError("table has no rows")
        return list(rows)

    def _get_headers(tbl: Any) -> list[str]:
        headers = getattr(tbl, "headers", None)
        if callable(headers):
            headers = headers()
        if headers is None:
            headers = []
        return list(headers)

    def _cell_value(row: Any, column: Any, headers: list[str]) -> Any:
        if isinstance(column, str) and column.isdigit():
            column = int(column)
        if isinstance(column, int):
            if isinstance(row, (list, tuple)):
                return row[column]
            if isinstance(row, dict):
                if headers and column < len(headers):
                    return row.get(headers[column])
                return list(row.values())[column]
        else:  # column specified by header
            if isinstance(row, dict):
                if column in row:
                    return row[column]
            if isinstance(row, (list, tuple)) and column in headers:
                idx = headers.index(column)
                return row[idx]
        raise KeyError(f"column {column} not found")

    def _matches(value: Any, cond: dict[str, Any]) -> bool:
        if "equals" in cond:
            return str(value) == str(cond["equals"])
        if "contains" in cond:
            return str(cond["contains"]) in str(value)
        if "regex" in cond:
            return re.search(cond["regex"], str(value)) is not None
        raise ValueError("unknown condition")

    selector = step.selector or step.params.get("selector") or {}
    criteria = step.params.get("criteria", {})
    timeout = step.params.get("timeout", 3000)
    resolved = _resolve_with_wait(selector, timeout)
    table = resolved["target"]

    try:
        rows = _get_rows(table)
        headers = _get_headers(table)
    except AttributeError:
        if hasattr(table, "find_row"):
            return table.find_row(criteria)
        raise

    normalized = _normalize(criteria)
    for row in rows:
        try:
            if all(_matches(_cell_value(row, c["column"], headers), c) for c in normalized):
                return row
        except Exception:
            continue
    raise LookupError("row not found")


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


def _get_cell_ref(row: Any, column: Any, headers: list[str] | None = None) -> tuple[Any, Any]:
    """Return container and key/index for a cell within ``row``.

    When the cell itself is an object, the container is the cell and the
    second element is ``None``.  ``column`` may be a header name or zero-based
    index.  ``headers`` provides an optional mapping of column indices to
    names.
    """

    if isinstance(column, str) and column.isdigit():
        column = int(column)

    if isinstance(row, dict):
        if isinstance(column, int):
            keys = list(row.keys())
            if headers and column < len(headers):
                key = headers[column]
            else:
                key = keys[column]
        else:
            key = column
        return row, key

    if isinstance(row, list):
        if not isinstance(column, int):
            if headers and column in headers:
                column = headers.index(column)
            else:
                raise KeyError(f"column {column} not found")
        return row, column

    if hasattr(row, "cells"):
        cells = getattr(row, "cells")
        cells = cells() if callable(cells) else cells
        if isinstance(column, int):
            return list(cells)[column], None
        if isinstance(cells, dict) and column in cells:
            return cells[column], None
        headers_attr = getattr(row, "headers", None)
        headers_attr = headers_attr() if callable(headers_attr) else headers_attr
        if headers_attr and column in headers_attr:
            idx = headers_attr.index(column)
            return list(cells)[idx], None

    if hasattr(row, "cell") and column is not None:
        try:
            return row.cell(column), None
        except Exception:
            pass

    raise KeyError(f"column {column} not found")


def _cell_value_from_obj(cell: Any) -> Any:
    """Extract a textual/value representation from ``cell``."""

    for attr in ("get_value", "get_text", "value", "text"):
        if hasattr(cell, attr):
            val = getattr(cell, attr)
            try:
                return val() if callable(val) else val
            except Exception:
                continue
    return cell


def cell_get(step: Step, ctx: ExecutionContext) -> Any:
    """Retrieve a cell value either from a row or via ``selector``."""

    row = step.params.get("row")
    column = step.params.get("column")
    headers = step.params.get("headers") or []
    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)

    if row is not None and column is not None:
        container, key = _get_cell_ref(row, column, headers)
        if key is None:
            return _cell_value_from_obj(container)
        value = container[key]
        return _cell_value_from_obj(value)

    if selector:
        resolved = _resolve_with_wait(selector, timeout)
        cell = resolved["target"]
        return _cell_value_from_obj(cell)

    raise ValueError("cell.get requires 'row' and 'column' or 'selector'")


def _set_cell_value(cell: Any, value: Any) -> None:
    """Set a value on ``cell`` attempting common setter styles."""

    for attr in ("set_value", "set_text", "type_text"):
        if hasattr(cell, attr):
            getattr(cell, attr)(value)
            return
    for attr in ("value", "text"):
        if hasattr(cell, attr):
            attr_obj = getattr(cell, attr)
            if callable(attr_obj):
                attr_obj(value)
            else:
                try:
                    setattr(cell, attr, value)
                except Exception:
                    continue
            return
    raise AttributeError("cell not writable")


def cell_set(step: Step, ctx: ExecutionContext) -> Any:
    """Set a cell value on a row or element resolved by ``selector``."""

    row = step.params.get("row")
    column = step.params.get("column")
    value = step.params.get("value")
    headers = step.params.get("headers") or []
    selector = step.selector or step.params.get("selector") or {}
    timeout = step.params.get("timeout", 3000)

    if row is not None and column is not None:
        container, key = _get_cell_ref(row, column, headers)
        if key is None:
            _set_cell_value(container, value)
        else:
            container[key] = value
        return value

    if selector:
        resolved = _resolve_with_wait(selector, timeout)
        cell = resolved["target"]
        _set_cell_value(cell, value)
        return value

    raise ValueError("cell.set requires 'row' and 'column' or 'selector'")


def _locate_image(
    path: str,
    *,
    region=None,
    scale=None,
    tolerance=None,
    dpi=None,
):
    """Locate an image on screen using ``pyautogui``.

    This helper centralizes the actual call so different actions can share the
    same lookup logic and optional dependencies are handled consistently.
    """

    try:  # pragma: no cover - optional dependency
        import pyautogui  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pyautogui not installed") from exc
    return pyautogui.locateOnScreen(
        path, region=region, scale=scale, tolerance=tolerance, dpi=dpi
    )


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
    end = time.time() + timeout / 1000.0
    while time.time() < end:
        box = _locate_image(
            path,
            region=region,
            scale=scale,
            tolerance=tolerance,
            dpi=dpi,
        )
        if box:
            return box
        time.sleep(interval)
    raise TimeoutError("image not found")


def wait_image_disappear(step: Step, ctx: ExecutionContext) -> Any:
    """Wait until ``path`` is no longer visible on screen."""

    path = step.params.get("path") or step.params.get("image")
    if not path:
        raise ValueError("wait_image_disappear requires 'path'")
    region = step.params.get("region")
    timeout = step.params.get("timeout", 3000)
    interval = step.params.get("interval", 0.5)
    scale = step.params.get("scale")
    tolerance = step.params.get("tolerance")
    dpi = step.params.get("dpi")
    end = time.time() + timeout / 1000.0
    while time.time() < end:
        box = _locate_image(
            path,
            region=region,
            scale=scale,
            tolerance=tolerance,
            dpi=dpi,
        )
        if not box:
            return True
        time.sleep(interval)
    raise TimeoutError("image still present")


def ocr_read(step: Step, ctx: ExecutionContext) -> Any:
    """Run OCR on an image at ``path`` using ``pytesseract``.

    Parameters
    ----------
    path: str
        Path to the image file.
    lang: str, optional
        Language(s) passed to Tesseract. Defaults to ``"eng"``.
    region: sequence or dict, optional
        When provided, defines the ``(x, y, width, height)`` region to crop
        before running OCR.
    """

    path = step.params.get("path")
    if not path:
        raise ValueError("ocr_read requires 'path'")
    lang = step.params.get("lang", "eng")
    region = step.params.get("region")
    try:  # pragma: no cover - optional dependency
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("pytesseract not installed") from exc

    if lang and "jpn" in lang.split("+"):
        available = pytesseract.get_languages(config="")
        if "jpn" not in available:
            raise RuntimeError("Japanese language data ('jpn') not installed for Tesseract")

    img = Image.open(path)
    if region is not None:
        if isinstance(region, dict):
            x = region.get("x")
            y = region.get("y")
            width = region.get("width")
            height = region.get("height")
        else:
            try:
                x, y, width, height = region
            except Exception as exc:
                raise ValueError("region must be (x, y, width, height)") from exc
        if None in (x, y, width, height):
            raise ValueError("region must include x, y, width, height")
        img = img.crop((x, y, x + width, y + height))

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


def tab_switch(step: Step, ctx: ExecutionContext) -> Any:
    """Switch to the next tab using the ``Ctrl+Tab`` hotkey."""

    _send_hotkey("ctrl", "tab")
    return True


def alt_selector(step: Step, ctx: ExecutionContext) -> Any:
    """Replace the selector of another step with an alternative."""

    target_step = step.params.get("step")
    new_selector = step.params.get("selector")
    if not isinstance(target_step, Step):
        raise ValueError("alt_selector requires 'step'")
    if not isinstance(new_selector, dict):
        raise ValueError("alt_selector requires 'selector'")
    target_step.selector = new_selector
    return new_selector


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
    "menu.select",
    "check",
    "uncheck",
    "find_image",
    "wait_image_disappear",
    "ocr_read",
    "click_xy",
    "table.wizard",
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
        "menu.select": menu_select,
        "check": check,
        "uncheck": uncheck,
        "set_value": set_value,
        "type_text": type_text,
        "click_xy": click_xy,
        "find_image": find_image,
        "wait_image_disappear": wait_image_disappear,
        "ocr_read": ocr_read,
        "table.wizard": table_wizard,
        "table.find_row": find_table_row,
        "row.select": select_row,
        "row.double_click": double_click_row,
        "cell.get": cell_get,
        "cell.set": cell_set,
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
from .actions_access import ACCESS_ACTIONS
from .actions_http import HTTP_ACTIONS
from .actions_files import FILES_ACTIONS

BUILTIN_ACTIONS.update(WEB_ACTIONS)
BUILTIN_ACTIONS.update(OFFICE_ACTIONS)
BUILTIN_ACTIONS.update(WORD_ACTIONS)
BUILTIN_ACTIONS.update(OUTLOOK_ACTIONS)
BUILTIN_ACTIONS.update(ACCESS_ACTIONS)
BUILTIN_ACTIONS.update(HTTP_ACTIONS)
BUILTIN_ACTIONS.update(FILES_ACTIONS)

BUILTIN_ACTIONS.update(
    {
        "ime.on": ime_on,
        "ime.off": ime_off,
        "layout.switch": switch_layout,
        "tab_switch": tab_switch,
        "alt_selector": alt_selector,
    }
)
