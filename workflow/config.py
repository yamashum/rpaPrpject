from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ProfileConfig:
    """Configuration for a runtime environment profile."""

    timeoutMs: int
    retry: int
    fallback: List[str] = field(default_factory=list)


DEFAULT_PROFILE = "physical"

# Default profile definitions. These are intentionally small so tests run quickly.
PROFILES: Dict[str, ProfileConfig] = {
    "physical": ProfileConfig(timeoutMs=1000, retry=0, fallback=["vdi"]),
    "vdi": ProfileConfig(timeoutMs=2000, retry=0, fallback=[]),
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
