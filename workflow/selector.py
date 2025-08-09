from __future__ import annotations

"""Simple selector resolver with multiple strategies."""

from typing import Any, Dict, Tuple, List


class SelectionError(Exception):
    """Raised when a selector cannot be resolved."""


def _resolve_uia(data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve UIA based selectors.

    The implementation is intentionally lightweight for testing.  When the
    supplied data contains ``{"exists": False}`` a :class:`SelectionError`
    is raised to simulate a failed lookup; otherwise the data is returned.
    """

    if data.get("exists", True):
        return data
    raise SelectionError("UIA element not found")


def _resolve_win32(data: Dict[str, Any]) -> Dict[str, Any]:
    return data


def _resolve_anchor(data: Dict[str, Any]) -> Dict[str, Any]:
    return data


def _resolve_image(data: Dict[str, Any]) -> Dict[str, Any]:
    return data


def _resolve_coordinate(data: Dict[str, Any]) -> Dict[str, Any]:
    return data


_STRATEGIES = {
    "uia": _resolve_uia,
    "win32": _resolve_win32,
    "anchor": _resolve_anchor,
    "image": _resolve_image,
    "coordinate": _resolve_coordinate,
}


def resolve(selector: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a selector using the available strategies.

    Parameters
    ----------
    selector:
        Mapping containing zero or more strategy entries such as ``"uia"`` or
        ``"image"``.  Strategies are attempted in the order UIA, Win32, anchor,
        image and finally coordinate.  The first successful resolution is
        returned in the form ``{"strategy": name, "target": data}``.

    Raises
    ------
    SelectionError
        If none of the strategies succeed.
    """

    for name in ["uia", "win32", "anchor", "image", "coordinate"]:
        data = selector.get(name)
        if not data:
            continue
        resolver = _STRATEGIES[name]
        try:
            resolved = resolver(data)
        except SelectionError:
            continue
        return {"strategy": name, "target": resolved}
    raise SelectionError("No selector strategy could resolve the element")


def _extract_token(selector: str) -> str:
    """Extract a token suitable for ``data-testid`` from a selector."""

    for sep in ["#", ".", " "]:
        if sep in selector:
            selector = selector.split(sep)[-1]
    return selector


def normalize_selector(selector: str) -> List[str]:
    """Return candidate selectors prioritising ``data-testid``.

    The returned list always contains a selector targeting ``data-testid``
    followed by the original selector as a fallback.
    """

    token = _extract_token(selector)
    return [f'[data-testid="{token}"]', selector]


def suggest_selector(selector: str) -> str:
    """Suggest a ``data-testid`` based selector for the given input."""

    token = _extract_token(selector)
    return f'[data-testid="{token}"]'
