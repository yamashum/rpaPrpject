"""GUI utilities for element spying, coordinate capture and web recording."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

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


def capture_coordinates() -> Tuple[int, int]:
    """Return the current mouse coordinates.

    When the Qt GUI stack is not available (e.g. during headless test runs),
    the origin ``(0, 0)`` is returned so that calling code can still operate.
    """

    if QCursor is None:  # pragma: no cover - exercised in headless tests
        return 0, 0
    pos = QCursor.pos()
    return pos.x(), pos.y()


def record_web(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Record a sequence of web actions.

    The function merely echoes the actions and serves as an integration point
    for a future browser recorder.  Returning the list makes it convenient to
    unit test and to directly wire into flow definitions.
    """

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
