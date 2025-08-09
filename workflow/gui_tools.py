"""GUI utilities for element spying, coordinate capture and web recording."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .selector import analyze_selectors, normalize_selector

try:  # pragma: no cover - optional GUI dependency
    from PyQt6.QtGui import QCursor
except Exception:  # pragma: no cover - headless environments
    QCursor = None  # type: ignore


# registry for anchors captured during spying
_ANCHOR_REGISTRY: List[str] = []


def highlight_screen(selector: str) -> None:
    """Highlight ``selector`` on screen.

    The real implementation would draw an overlay.  In tests this function can
    be monkeypatched to assert that highlighting was requested.
    """

    # default implementation is a no-op; kept for test monkeypatching
    return None


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


def element_spy(selector: str, text: str | None = None) -> ElementInfo:
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

    return rows


def capture_coordinates(
    basis: str = "Screen",
    origin: Tuple[int, int] | None = None,
    preview: bool = False,
) -> Dict[str, Any]:
    """Return the current mouse coordinates with optional basis.

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
    """

    if QCursor is None:  # pragma: no cover - exercised in headless tests
        x, y = 0, 0
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


def record_web(
    actions: List[Dict[str, Any]], flow: Dict[str, Any] | None = None
) -> List[Dict[str, Any]]:
    """Record a sequence of web actions.

    Selectors for each action are normalised and augmented with suggestions via
    :func:`selector.analyze_selectors`.  When ``flow`` is provided any action
    containing an ``"id"`` field is inserted into the flow using
    :func:`wire_to_flow`.
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
