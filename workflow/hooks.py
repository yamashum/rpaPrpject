"""Common hooks for the workflow runtime.

Currently only provides a screenshot masking hook that allows callers to
anonymise screenshots before they are written to disk.
"""

from __future__ import annotations

from typing import Callable, Optional


ScreenshotMaskHook = Callable[[bytes], bytes]
"""Callable type for screenshot masking."""

# Global hook that can be set by applications to mask screenshot bytes before
# they are persisted. When ``None`` no masking is performed.
screenshot_mask_hook: Optional[ScreenshotMaskHook] = None


def apply_screenshot_mask(data: bytes) -> bytes:
    """Return ``data`` after applying :data:`screenshot_mask_hook`.

    If the hook raises an exception the original data is returned unchanged.
    """
    if screenshot_mask_hook is None:
        return data
    try:
        return screenshot_mask_hook(data)
    except Exception:
        return data


__all__ = ["screenshot_mask_hook", "apply_screenshot_mask"]
