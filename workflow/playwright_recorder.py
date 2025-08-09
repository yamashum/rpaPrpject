"""Utilities for recording browser actions via Playwright.

This module provides a lightweight bridge between Playwright's recording
capabilities and the GUI.  Recorded actions are normalised using
:mod:`workflow.selector` and forwarded to the main UI via a queue.
"""
from __future__ import annotations

from queue import Queue
from typing import Any, Callable, Dict, List

from . import gui_tools

try:  # pragma: no cover - Playwright is optional during tests
    from playwright.sync_api import Page  # type: ignore
except Exception:  # pragma: no cover
    Page = Any  # type: ignore


def record_actions(
    actions: List[Dict[str, Any]],
    flow: Dict[str, Any] | None = None,
    *,
    queue: "Queue[Dict[str, Any]]" | None = None,
    callback: Callable[[Dict[str, Any]], None] | None = None,
) -> List[Dict[str, Any]]:
    """Normalise *actions* recorded via Playwright and emit them to a queue.

    Parameters
    ----------
    actions:
        Raw action dictionaries captured from the browser.
    flow:
        Optional flow definition to update with parameters from actions.
    queue:
        Queue receiving processed actions.  When ``None`` the queue exported by
        :mod:`rpa_main_ui` is used if available.
    callback:
        Optional callback invoked with each processed action.
    """

    if queue is None:
        try:  # pragma: no cover - GUI may not be available
            from rpa_main_ui import recorded_actions_q

            queue = recorded_actions_q
        except Exception:
            queue = None

    return gui_tools.record_web(
        actions,
        flow,
        insert=True,
        callback=callback,
        queue=queue,
    )
