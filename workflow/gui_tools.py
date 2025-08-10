"""GUI utilities for element spying, coordinate capture and web recording."""
from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from typing import Any, Callable, Dict, List, Tuple
import re
import time


from .selector import analyze_selectors, normalize_selector

try:  # pragma: no cover - optional GUI dependency
    from PyQt6.QtGui import QCursor
except Exception:  # pragma: no cover - headless environments
    QCursor = None  # type: ignore


# registry for anchors captured during spying
_ANCHOR_REGISTRY: List[str] = []


def highlight_screen(selector: str, duration: float = 0.5) -> None:
    """Highlight ``selector`` on screen.

    When Qt is available and ``selector`` represents coordinates in the form
    ``"@x,y"`` a small red rectangle is shown around that point for
    ``duration`` seconds.  In headless environments the function quietly does
    nothing so tests can monkeypatch it freely.
    """

    if QCursor is None:
        return
    m = re.match(r"@(?P<x>\d+),(?P<y>\d+)", selector)
    if not m:
        return
    try:  # pragma: no cover - optional GUI dependency
        from PyQt6.QtWidgets import QApplication, QWidget
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPainter, QPen

        app = QApplication.instance() or QApplication([])

        class Overlay(QWidget):
            def paintEvent(self, event):  # type: ignore[override]
                painter = QPainter(self)
                pen = QPen(Qt.GlobalColor.red)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        size = 20
        x, y = int(m.group("x")), int(m.group("y"))
        w = Overlay()
        w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        w.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        w.setGeometry(x - size // 2, y - size // 2, size, size)
        w.show()
        app.processEvents()
        time.sleep(duration)
        w.close()
        app.processEvents()
    except Exception:
        return


def register_anchor(selector: str) -> None:
    """Register ``selector`` as an anchor for later use."""

    _ANCHOR_REGISTRY.append(selector)


def _screen_dpi() -> int:
    """Return the logical DPI of the primary screen.

    Falls back to ``96`` when Qt is unavailable or does not expose the value.
    A dedicated helper makes it easy to monkeypatch in unit tests.
    """

    if QCursor is None:  # pragma: no cover - exercised in headless tests
        return 96
    try:  # pragma: no cover - optional GUI dependency
        from PyQt6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen:
            return int(screen.logicalDotsPerInch())
    except Exception:
        pass
    return 96


def _grab_preview(x: int, y: int) -> Any:
    """Return a small screenshot around ``(x, y)`` encoded as base64.

    When capturing an image is not possible (e.g. in headless tests) the
    coordinate tuple itself is returned instead.
    """

    if QCursor is None:  # pragma: no cover - exercised in headless tests
        return (x, y)
    try:  # pragma: no cover - optional GUI dependency
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtCore import QBuffer, QIODevice
        import base64

        screen = QGuiApplication.primaryScreen()
        if screen:
            pixmap = screen.grabWindow(0, x - 10, y - 10, 20, 20)
            if not pixmap.isNull():
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                pixmap.save(buffer, "PNG")
                data = bytes(buffer.data())
                return base64.b64encode(data).decode("ascii")
    except Exception:
        pass
    return (x, y)


@dataclass
class ElementInfo:
    """Information returned by :func:`element_spy`."""

    selector: str
    text: str | None = None
    automation_id: str | None = None
    name: str | None = None
    control_type: str | None = None
    class_name: str | None = None
    hierarchy: List[Dict[str, str]] | None = None
    x: int | None = None
    y: int | None = None


def element_spy(
    selector: str,
    text: str | None = None,
    *,
    x: int | None = None,
    y: int | None = None,
) -> ElementInfo:
    """Simulate an element spy utility collecting basic UIA data.

    In addition to recording the selector, the function highlights the element
    on screen and registers it as an anchor.  ``AutomationId``, ``Name``,
    ``ControlType`` and ``ClassName`` are synthesised for test purposes.  A
    simple parent hierarchy is also returned so that GUI components can present
    the element in context.  Real implementations would query these details
    from the accessibility framework.
    """

    highlight_screen(selector)
    register_anchor(selector)

    # placeholder data allowing callers to exercise the structure of the
    # returned information.  In unit tests this can be monkeypatched to provide
    # deterministic values.
    automation_id = f"{selector}-auto"
    name = text or selector
    control_type = "Control"
    class_name = "Generic"
    hierarchy = [
        {
            "automation_id": automation_id,
            "name": name,
            "control_type": control_type,
            "class_name": class_name,
        }
    ]

    return ElementInfo(
        selector=selector,
        text=text,
        automation_id=automation_id,
        name=name,
        control_type=control_type,
        class_name=class_name,
        hierarchy=hierarchy,
        x=x,
        y=y,
    )


def format_spy_result(info: ElementInfo) -> List[Tuple[str, str]]:
    """Return ``info`` formatted for presentation in a GUI table.

    The function converts the dataclass into a list of ``(label, value)`` tuples
    which can be easily rendered by GUI toolkits without understanding the
    dataclass structure.  It also flattens the hierarchy into a single string to
    keep the representation simple.
    """

    rows: List[Tuple[str, str]] = [
        ("Selector", info.selector),
        ("AutomationId", info.automation_id or ""),
        ("Name", info.name or ""),
        ("ControlType", info.control_type or ""),
        ("ClassName", info.class_name or ""),
    ]

    if info.text is not None:
        rows.append(("Text", info.text))

    if info.hierarchy:
        chain = " > ".join(
            h.get("name") or h.get("automation_id") or "?" for h in info.hierarchy
        )
        rows.append(("Hierarchy", chain))

    if info.x is not None and info.y is not None:
        rows.append(("Coordinates", f"{info.x}, {info.y}"))

    return rows


def capture_coordinates(
    basis: str = "Screen",
    origin: Tuple[int, int] | None = None,
    preview: bool = False,
    wait: bool = False,
) -> Dict[str, Any]:
    """Return the mouse coordinates with optional basis.

    Parameters
    ----------
    basis:
        ``"Element"``, ``"Window"`` or ``"Screen"``. When ``Element`` or
        ``Window`` the provided ``origin`` is subtracted from the cursor
        position to yield relative coordinates.
    origin:
        Top-left coordinate of the reference element or window.
    preview:
        When ``True`` include a copy of the computed coordinates under the
        ``"preview"`` key.  This is primarily useful for GUI tooling that wants
        to display the result without performing an action.
    wait:
        When ``True`` the function waits for the user to click before
        obtaining the coordinates.  This requires a running Qt event loop.
    """

    if QCursor is None:  # pragma: no cover - exercised in headless tests
        x, y = 0, 0
    elif wait:  # pragma: no cover - optional GUI dependency
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QObject, QEvent, QEventLoop

            app = QApplication.instance() or QApplication([])
            clicked: Dict[str, int] = {}

            class Listener(QObject):
                def eventFilter(self, obj, event):  # type: ignore[override]
                    if event.type() == QEvent.Type.MouseButtonPress:
                        gp = event.globalPosition()
                        clicked["x"], clicked["y"] = int(gp.x()), int(gp.y())
                        loop.quit()
                    return False

            listener = Listener()
            app.installEventFilter(listener)
            loop = QEventLoop()
            loop.exec()
            app.removeEventFilter(listener)
            x = clicked.get("x", 0)
            y = clicked.get("y", 0)
        except Exception:
            pos = QCursor.pos()
            x, y = pos.x(), pos.y()
    else:  # pragma: no cover - optional GUI dependency
        pos = QCursor.pos()
        x, y = pos.x(), pos.y()

    if basis.lower() != "screen" and origin:
        ox, oy = origin
        x -= ox
        y -= oy

    dpi = _screen_dpi()
    result: Dict[str, Any] = {"x": x, "y": y, "basis": basis, "dpi": dpi}
    if preview:
        result["preview"] = _grab_preview(x, y)
    return result


def countdown_capture_coordinates(seconds: int = 10) -> Dict[str, Any]:
    """Return cursor coordinates after a simple countdown.

    The function sleeps for ``seconds`` allowing the user to position the
    cursor and then delegates to :func:`capture_coordinates`.  ``time.sleep``
    is used for the countdown which may be monkeypatched in tests to avoid
    delays.  When Qt is available the remaining time is shown in a temporary
    window so the user receives visual feedback.
    """
    if QCursor is not None:
        try:  # pragma: no cover - optional GUI dependency
            from PyQt6.QtWidgets import QApplication, QLabel
            from PyQt6.QtCore import Qt

            app = QApplication.instance() or QApplication([])
            label = QLabel()
            label.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setStyleSheet(
                "color: red; font-size: 48px; background: transparent"
            )
            label.resize(100, 60)
            label.show()
            for remaining in range(seconds, 0, -1):
                label.setText(str(remaining))
                app.processEvents()
                time.sleep(1)
            label.close()
            app.processEvents()
        except Exception:
            for _ in range(seconds, 0, -1):
                time.sleep(1)
    else:
        for _ in range(seconds, 0, -1):
            time.sleep(1)
    return capture_coordinates()


def spy_on_click() -> ElementInfo:
    """Wait for a user click and return an :class:`ElementInfo` for it.

    The click coordinates are captured via :func:`capture_coordinates` and fed
    back into :func:`element_spy` using an ``@x,y`` selector.
    """

    coords = capture_coordinates(wait=True)
    selector = f"@{coords['x']},{coords['y']}"
    return element_spy(selector, x=coords["x"], y=coords["y"])




def desktop_spy() -> ElementInfo:
    """Convenience wrapper emulating a desktop element spy.

    It simply forwards to :func:`spy_on_click` which waits for the user to
    click and returns information about the element at that position.
    """
    return spy_on_click()


def capture_web_click(url: str) -> Dict[str, Any]:
    """Open ``url`` and return the bounding box of the first element clicked.

    A minimal helper that uses Playwright to load the page.  When the user
    clicks an element it is outlined in red and the element's bounding box is
    returned.  If Playwright is unavailable the function returns an empty
    dictionary.
    """
    try:  # pragma: no cover - Playwright optional in tests
        from playwright.sync_api import sync_playwright
    except Exception:
        return {}
    with sync_playwright() as pw:  # pragma: no cover - requires browser
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        box = page.evaluate(
            """
            () => new Promise(resolve => {
                document.addEventListener('click', e => {
                    e.preventDefault();
                    const r = e.target.getBoundingClientRect();
                    e.target.style.outline = '2px solid red';
                    resolve({x: r.left, y: r.top, width: r.width, height: r.height});
                }, {once: true});
            })
            """
        )
        browser.close()
        return box
def record_web(
    actions: List[Dict[str, Any]],
    flow: Dict[str, Any] | None = None,
    *,
    insert: bool = False,
    callback: Callable[[Dict[str, Any]], None] | None = None,
    queue: "Queue[Dict[str, Any]]" | None = None,
) -> List[Dict[str, Any]]:
    """Record a sequence of web actions.

    Selectors for each action are normalised and augmented with suggestions via
    :func:`selector.analyze_selectors`.  When ``flow`` is provided any action
    containing an ``"id"`` field is inserted into the flow using
    :func:`wire_to_flow`.

    Parameters
    ----------
    actions:
        List of action dictionaries recorded from the browser.
    flow:
        Optional flow definition to update in-place.
    insert:
        When ``True`` each processed action is also emitted to ``callback`` or
        ``queue`` allowing other components (such as a GUI) to receive
        incremental updates.
    callback:
        Function invoked with each processed action when ``insert`` is
        ``True``.
    queue:
        Queue receiving each processed action when ``insert`` is ``True``.

    Returns
    -------
    List[Dict[str, Any]]
        The processed actions with normalised selectors.
    """

    analyze_selectors(actions)
    for action in actions:
        sel = action.get("selector")
        if isinstance(sel, str):
            suggestions = action.get("selectorSuggestions") or normalize_selector(sel)
            action["selector"] = suggestions[0]
            action["selectorSuggestions"] = suggestions
        if flow is not None and action.get("id"):
            params = {k: v for k, v in action.items() if k != "id"}
            wire_to_flow(flow, action["id"], params)
        if insert:
            if callback is not None:
                callback(action)
            if queue is not None:
                queue.put(action)
            elif callback is None:
                try:  # pragma: no cover - rpa_main_ui optional in tests
                    from rpa_main_ui import recorded_actions_q

                    recorded_actions_q.put(action)
                except Exception:
                    pass
    return actions


def wire_to_flow(flow: Dict[str, Any], step_id: str, params: Dict[str, Any]) -> None:
    """Insert captured parameters into a flow definition.

    Parameters
    ----------
    flow:
        The flow dictionary to modify.
    step_id:
        Identifier of the step to update.
    params:
        Parameters obtained from one of the capture utilities.
    """

    for step in flow.get("steps", []):
        if step.get("id") == step_id:
            step.setdefault("params", {}).update(params)
            return
    raise KeyError(f"Step {step_id} not found")
