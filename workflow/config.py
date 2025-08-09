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


WAIT_PRESETS: Dict[str, WaitFunc] = {
    "visible": _wait_visible,
    "clickable": _wait_clickable,
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
