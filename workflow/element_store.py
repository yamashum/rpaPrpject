"""Simple in-memory registry for captured elements."""
from __future__ import annotations

from typing import List

from .gui_tools import ElementInfo

# internal list storing captured elements
_ELEMENTS: List[ElementInfo] = []


def add_element(info: ElementInfo) -> None:
    """Add ``info`` to the registry."""
    _ELEMENTS.append(info)


def remove_element(info: ElementInfo) -> None:
    """Remove ``info`` from the registry if present."""
    try:
        _ELEMENTS.remove(info)
    except ValueError:
        pass


def list_elements() -> List[ElementInfo]:
    """Return all captured elements."""
    return list(_ELEMENTS)
