from __future__ import annotations

"""Simple selector resolver with multiple strategies."""

from typing import Any, Dict, Tuple, List
from pathlib import Path
import json
import os


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

# in-memory statistics of attempts and successes per strategy
_HIT_STATS: Dict[str, Dict[str, int]] = {
    name: {"attempts": 0, "success": 0} for name in _STRATEGIES
}
_STATS_PATH: Path | None = None


def _load_stats(path: Path) -> None:
    """Load selector statistics from ``path`` if it exists."""

    global _HIT_STATS
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except Exception:
        return
    for name, info in data.items():
        stats = _HIT_STATS.setdefault(name, {"attempts": 0, "success": 0})
        stats["attempts"] = int(info.get("attempts", 0))
        stats["success"] = int(info.get("success", 0))


def _save_stats() -> None:
    """Persist statistics to ``_STATS_PATH`` if configured."""

    if _STATS_PATH is None:
        return
    try:
        _STATS_PATH.write_text(json.dumps(_HIT_STATS))
    except Exception:
        pass


def resolve(selector: Dict[str, Any], run_dir: Path | str | None = None) -> Dict[str, Any]:
    """Resolve a selector using the available strategies.

    Parameters
    ----------
    selector:
        Mapping containing zero or more strategy entries such as ``"uia"`` or
        ``"image"``. Strategies are attempted based on historical success rate.
    run_dir:
        Directory where hit statistics should be saved. When ``None`` the
        environment variables ``RUN_DIR`` or ``RPA_RUN_DIR`` are used if
        available.

    Raises
    ------
    SelectionError
        If none of the strategies succeed.
    """

    global _STATS_PATH

    if run_dir is None:
        run_dir = os.getenv("RUN_DIR") or os.getenv("RPA_RUN_DIR")
    if run_dir is not None:
        path = Path(run_dir) / "selector_stats.json"
        if _STATS_PATH != path:
            _STATS_PATH = path
            global _HIT_STATS
            _HIT_STATS = {name: {"attempts": 0, "success": 0} for name in _STRATEGIES}
            _load_stats(path)

    strategies = [name for name in selector if name in _STRATEGIES]
    base_order = ["uia", "win32", "anchor", "image", "coordinate"]
    if os.getenv("RPA_VDI") or os.getenv("VDI") or os.getenv("VDI_MODE"):
        base_order = ["image", "coordinate", "uia", "win32", "anchor"]

    def rate(name: str) -> float:
        stats = _HIT_STATS.get(name, {"attempts": 0, "success": 0})
        attempts = stats["attempts"]
        return (stats["success"] / attempts) if attempts else 0.0

    strategies.sort(key=lambda n: (-rate(n), base_order.index(n)))

    last_exc: SelectionError | None = None
    for name in strategies:
        data = selector.get(name)
        if not data:
            continue
        _HIT_STATS.setdefault(name, {"attempts": 0, "success": 0})
        _HIT_STATS[name]["attempts"] += 1
        resolver = _STRATEGIES[name]
        try:
            resolved = resolver(data)
        except SelectionError as exc:
            last_exc = exc
            continue
        _HIT_STATS[name]["success"] += 1
        _save_stats()
        return {"strategy": name, "target": resolved}

    _save_stats()
    if last_exc:
        raise last_exc
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
