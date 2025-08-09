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
    """Resolve win32 based selectors.

    The dummy implementation mirrors :func:`_resolve_uia` by honouring an
    ``"exists"`` flag.  When ``exists`` is ``False`` a
    :class:`SelectionError` is raised to simulate a lookup failure.  In all
    other cases the supplied data is considered resolved and returned.  The
    behaviour is intentionally small but provides a realistic failure mode so
    that statistics and learning can be exercised in tests.
    """

    if data.get("exists", True):
        return data
    raise SelectionError("win32 element not found")


def _resolve_anchor(data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve an element relative to an anchor.

    The anchor can be specified using text/OCR, an image or explicit
    coordinates.  Offsets may be supplied either as ``{"x": int, "y": int}``
    mapping, a two item sequence or ``offsetX``/``offsetY`` keys.  The function
    returns the final coordinates of the element relative to the anchor.
    ``SelectionError`` is raised when the anchor cannot be resolved.
    """

    anchor_pos: Dict[str, Any]
    if "image" in data:
        anchor_pos = _resolve_image(data["image"])
    elif "text" in data or "ocr" in data:
        # for tests we simply expect coordinates to be provided
        if "x" in data and "y" in data:
            anchor_pos = {"x": data["x"], "y": data["y"]}
        else:
            raise SelectionError("text/OCR anchor requires 'x' and 'y'")
    elif "x" in data and "y" in data:
        anchor_pos = {"x": data["x"], "y": data["y"]}
    else:
        raise SelectionError("Unsupported anchor specification")

    ox = oy = 0
    offset = data.get("offset")
    if isinstance(offset, dict):
        ox = int(offset.get("x", 0))
        oy = int(offset.get("y", 0))
    elif isinstance(offset, (list, tuple)) and len(offset) >= 2:
        ox, oy = int(offset[0]), int(offset[1])
    else:
        ox = int(data.get("offsetX", 0))
        oy = int(data.get("offsetY", 0))

    return {"x": anchor_pos["x"] + ox, "y": anchor_pos["y"] + oy}


def _resolve_image(data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve an element using template image matching.

    The implementation uses :mod:`Pillow` and :mod:`numpy` for a tiny template
    matching routine.  ``data`` must contain ``"path"`` pointing to the template
    image.  A ``"source"`` image can be supplied to search in; when omitted the
    template itself is used.  ``tolerance`` specifies the average per‑pixel
    difference that is accepted.  The function returns the centre coordinates of
    the best match or raises :class:`SelectionError` when no match is found.
    """

    path = data.get("path")
    if not path:
        raise SelectionError("image path missing")

    try:
        from PIL import Image
        import numpy as np  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency issues
        raise SelectionError("image libraries not available") from exc

    try:
        template = Image.open(path)
    except Exception as exc:
        raise SelectionError(f"unable to open image '{path}'") from exc

    source_path = data.get("source", path)
    try:
        source_img = Image.open(source_path)
    except Exception as exc:
        raise SelectionError(f"unable to open image '{source_path}'") from exc

    tmpl = np.asarray(template.convert("RGB"))
    src = np.asarray(source_img.convert("RGB"))
    h, w = tmpl.shape[:2]
    H, W = src.shape[:2]
    if h > H or w > W:
        raise SelectionError("template larger than source image")

    tolerance = float(data.get("tolerance", 0))
    match: Tuple[int, int] | None = None

    for y in range(0, H - h + 1):
        for x in range(0, W - w + 1):
            crop = src[y : y + h, x : x + w]
            diff = np.abs(crop.astype(float) - tmpl.astype(float)).mean()
            if diff <= tolerance:
                match = (x + w // 2, y + h // 2)
                break
        if match:
            break

    if match is None:
        raise SelectionError("image not found")

    return {"x": match[0], "y": match[1]}


def _resolve_coordinate(data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a coordinate based selector.

    ``data`` must contain numeric ``x`` and ``y`` values.  They are returned as
    a mapping.  ``SelectionError`` is raised when either coordinate is missing.
    """

    try:
        x = int(data["x"])
        y = int(data["y"])
    except Exception as exc:
        raise SelectionError("coordinate requires 'x' and 'y'") from exc
    return {"x": x, "y": y}


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

# accepted scope keys for narrowing search
_SCOPE_KEYS = {"process", "name", "class", "activeWindow"}


def _filter_scope(scope: Any) -> Dict[str, Any]:
    """Return a scope dictionary limited to known keys."""

    if not isinstance(scope, dict):
        return {}
    return {k: v for k, v in scope.items() if k in _SCOPE_KEYS}


def _merge_scope(data: Dict[str, Any] | None, scope: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ``scope`` into ``data`` without mutating either."""

    if not scope:
        return data or {}
    merged: Dict[str, Any] = dict(scope)
    if data:
        merged.update(data)
    return merged


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
        ``"image"``.  A ``"scope"`` mapping may be supplied to narrow the
        search using ``process``, ``name``, ``class`` or ``activeWindow``.  A
        selector may also contain an ``"anyOf"`` list of alternative selectors
        which are tried sequentially until one succeeds.
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

    scope = _filter_scope(selector.get("scope"))

    # ``anyOf``: try candidate selectors sequentially
    any_of = selector.get("anyOf")
    if isinstance(any_of, list):
        last_exc: SelectionError | None = None
        for cand in any_of:
            if not isinstance(cand, dict):
                continue
            cand = dict(cand)
            cand_scope = _filter_scope(cand.get("scope"))
            merged_scope = {**scope, **cand_scope}
            if merged_scope:
                cand["scope"] = merged_scope
            try:
                return resolve(cand, run_dir=run_dir)
            except SelectionError as exc:
                last_exc = exc
        if last_exc:
            raise last_exc
        raise SelectionError("No selector strategy could resolve the element")

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
        data = _merge_scope(data, scope)
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
    """Return candidate selectors ordered by stability.

    The function attempts to provide increasingly generic alternatives for a
    recorded selector.  ``data-testid`` is preferred when available, followed
    by element ``id`` selectors, CSS selectors and finally an XPath
    representation.  The original selector is included if it differs from the
    generated fallbacks.
    """

    token = _extract_token(selector)
    result: List[str] = [f'[data-testid="{token}"]']

    id_sel: str | None = None
    css_sel: str | None = None
    xpath_sel: str | None = None

    if selector.strip().startswith("//"):
        # XPath selector - extract id if present
        xpath_sel = selector
        import re
        m = re.search(r"@id=['\"]([^'\"]+)['\"]", selector)
        if m:
            id_sel = f"#{m.group(1)}"
    else:
        css_sel = selector
        import re
        m = re.search(r"#([A-Za-z_][\w\-]*)", selector)
        if m:
            id_sel = f"#{m.group(1)}"
            xpath_sel = f'//*[@id="{m.group(1)}"]'

    for cand in (id_sel, css_sel, xpath_sel):
        if cand and cand not in result:
            result.append(cand)

    if selector not in result:
        result.append(selector)

    return result


def suggest_selector(selector: str) -> str:
    """Suggest a ``data-testid`` based selector for the given input."""

    token = _extract_token(selector)
    return f'[data-testid="{token}"]'


def analyze_selectors(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Augment recorded actions with stable selector suggestions.

    For each action containing a ``"selector"`` key, a new
    ``"selectorSuggestions"`` list is added containing the candidates returned
    by :func:`normalize_selector`.  The input list is mutated and returned for
    convenience.
    """

    for action in actions:
        sel = action.get("selector")
        if isinstance(sel, str):
            action["selectorSuggestions"] = normalize_selector(sel)
    return actions
