"""GUI utilities for element spying, coordinate capture and web recording."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .selector import analyze_selectors

try:  # pragma: no cover - optional GUI dependency
    from PyQt6.QtGui import QCursor
except Exception:  # pragma: no cover - headless environments
    QCursor = None  # type: ignore


@dataclass
class ElementInfo:
    """Information returned by :func:`element_spy`."""

    selector: str
    text: str | None = None


def element_spy(selector: str, text: str | None = None) -> ElementInfo:
    """Simulate an element spy utility.

    The real application would present a crosshair cursor and allow the user to
    select any UI element on screen.  For the purpose of unit tests and this
    lightweight demo the function simply records the selector and optional text
    label supplied by the caller.
    """

    return ElementInfo(selector=selector, text=text)


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
    else:
        pos = QCursor.pos()
        x, y = pos.x(), pos.y()

    if basis.lower() != "screen" and origin:
        ox, oy = origin
        x -= ox
        y -= oy

    result: Dict[str, Any] = {"x": x, "y": y, "basis": basis}
    if preview:
        result["preview"] = (x, y)
    return result


def record_web(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Record a sequence of web actions.

    Currently the function echoes the supplied actions but augments any
    selectors with stable attribute suggestions via
    :func:`selector.analyze_selectors`.  Returning the list makes it convenient
    to unit test and to directly wire into flow definitions.
    """

    return analyze_selectors(actions)


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
