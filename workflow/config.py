from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, TYPE_CHECKING

from .selector import resolve as resolve_selector

if TYPE_CHECKING:  # pragma: no cover - only used for type hints
    from .flow import Step
    from .runner import ExecutionContext


@dataclass(frozen=True)
class ProfileConfig:
    """Configuration for a runtime environment profile."""

    timeoutMs: int
    retry: int
    fallback: List[str] = field(default_factory=list)
    selectors: List[str] = field(
        default_factory=lambda: ["uia", "anchor", "image", "coordinate"]
    )


# ---- waiting presets -----------------------------------------------------

WaitFunc = Callable[["Step", "ExecutionContext"], bool]


def _wait_visible(step: "Step", ctx: "ExecutionContext") -> bool:
    selector = step.selector or step.params.get("selector") or {}
    if not selector:
        return True
    try:
        resolved = resolve_selector(selector)
    except Exception:
        return False
    target = resolved.get("target")
    if hasattr(target, "is_visible"):
        try:
            return bool(target.is_visible())
        except Exception:
            return False
    return True


def _wait_clickable(step: "Step", ctx: "ExecutionContext") -> bool:
    selector = step.selector or step.params.get("selector") or {}
    if not selector:
        return True
    try:
        resolved = resolve_selector(selector)
    except Exception:
        return False
    target = resolved.get("target")
    visible = True
    enabled = True
    if hasattr(target, "is_visible"):
        try:
            visible = bool(target.is_visible())
        except Exception:
            visible = False
    if hasattr(target, "is_enabled"):
        try:
            enabled = bool(target.is_enabled())
        except Exception:
            enabled = False
    return visible and enabled


def _wait_spinner_disappear(step: "Step", ctx: "ExecutionContext") -> bool:
    """Return True when the element is not visible or missing.

    The spinner is identified using the step selector or ``params['selector']``.
    If the selector cannot be resolved the condition is considered satisfied.
    """

    selector = step.selector or step.params.get("selector") or {}
    if not selector:
        return True
    try:
        resolved = resolve_selector(selector)
    except Exception:
        # If the element can't be resolved it likely disappeared already
        return True
    target = resolved.get("target")
    if hasattr(target, "is_visible"):
        try:
            return not bool(target.is_visible())
        except Exception:
            return True
    return True


def _wait_value_equals(step: "Step", ctx: "ExecutionContext") -> bool:
    """Return True when the element's value equals ``params['value']``."""

    selector = step.selector or step.params.get("selector") or {}
    expected = step.params.get("value")
    if not selector or expected is None:
        return True
    try:
        resolved = resolve_selector(selector)
    except Exception:
        return False
    target = resolved.get("target")

    value: Any = None
    if hasattr(target, "get_value"):
        try:
            value = target.get_value()
        except Exception:
            return False
    elif hasattr(target, "window_text"):
        try:
            value = target.window_text()
        except Exception:
            return False
    elif hasattr(target, "inner_text"):
        try:
            value = target.inner_text()
        except Exception:
            return False
    elif hasattr(target, "value"):
        attr = target.value
        try:
            value = attr() if callable(attr) else attr
        except Exception:
            return False
    return value == expected


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


def _wait_overlay_disappear(step: "Step", ctx: "ExecutionContext") -> bool:
    """Return True when the element is not covered by an overlay.

    The element is identified using the step selector or ``params['selector']``.
    If the selector cannot be resolved the condition is considered satisfied.
    """

    selector = step.selector or step.params.get("selector") or {}
    if not selector:
        return True
    try:
        resolved = resolve_selector(selector)
    except Exception:
        return True
    target = resolved.get("target")
    if target is None:
        return True
    return not _element_has_overlay(target)


WAIT_PRESETS: Dict[str, WaitFunc] = {
    "visible": _wait_visible,
    "clickable": _wait_clickable,
    "spinner_disappear": _wait_spinner_disappear,
    "valueEquals": _wait_value_equals,
    "overlay_disappear": _wait_overlay_disappear,
}


DEFAULT_PROFILE = "physical"

# Default profile definitions. These are intentionally small so tests run quickly.
PROFILES: Dict[str, ProfileConfig] = {
    "physical": ProfileConfig(
        timeoutMs=1000,
        retry=0,
        fallback=["vdi"],
        selectors=["uia", "anchor", "image", "coordinate"],
    ),
    "vdi": ProfileConfig(
        timeoutMs=2000,
        retry=0,
        fallback=[],
        selectors=["image", "coordinate", "uia", "anchor"],
    ),
}


def get_profile_chain(start: str | None) -> List[str]:
    """Return the list of profiles to try starting with ``start``.

    Fallbacks are resolved recursively while preserving the order declared in
    :data:`PROFILES`. Unknown profiles default to :data:`DEFAULT_PROFILE`.
    """

    seen: set[str] = set()
    order: List[str] = []

    def _add(name: str) -> None:
        if name in seen:
            return
        profile = PROFILES.get(name)
        if profile is None:
            return
        seen.add(name)
        order.append(name)
        for fb in profile.fallback:
            _add(fb)

    start_name = start if start in PROFILES else DEFAULT_PROFILE
    _add(start_name)
    return order
