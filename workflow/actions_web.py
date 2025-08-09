"""Web automation actions implemented using Playwright."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:  # pragma: no cover - optional dependency
    from playwright.sync_api import Page, sync_playwright
except Exception:  # pragma: no cover - optional dependency
    Page = Any  # type: ignore
    sync_playwright = None

from .flow import Step
from .runner import ExecutionContext
from .selector import normalize_selector

_PW_KEY = "_playwright"
_BROWSER_KEY = "_browser"
_PAGE_KEY = "_page"


def _get_page(ctx: ExecutionContext) -> Page:
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed")
    page = ctx.globals.get(_PAGE_KEY)
    if page:
        return page
    pw = ctx.globals.get(_PW_KEY)
    if pw is None:
        pw = sync_playwright().start()
        ctx.globals[_PW_KEY] = pw
    browser = ctx.globals.get(_BROWSER_KEY)
    if browser is None:
        browser = pw.chromium.launch()
        ctx.globals[_BROWSER_KEY] = browser
    page = browser.new_page()
    ctx.globals[_PAGE_KEY] = page
    return page


def open(step: Step, ctx: ExecutionContext) -> Any:
    url = step.params["url"]
    page = _get_page(ctx)
    try:
        page.goto(url)
    except Exception as exc:  # pragma: no cover - network errors
        raise RuntimeError(f"Network failure: {exc}") from exc
    return url


def click(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    frame = step.params.get("frame")
    page = _get_page(ctx)
    target = page.frame_locator(frame) if frame else page
    last_exc: Exception | None = None
    for sel in normalize_selector(selector):
        loc = target.locator(sel)
        if not loc.count():
            continue
        try:
            loc.click()
            return sel
        except Exception as exc:  # pragma: no cover - overlay or stale element
            last_exc = exc
            continue
    try:
        target.locator(selector).click()
        return selector
    except Exception as exc:  # pragma: no cover - all selectors failed
        raise RuntimeError("Element obscured") from (last_exc or exc)


def fill(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    value = step.params.get("value", "")
    frame = step.params.get("frame")
    page = _get_page(ctx)
    target = page.frame_locator(frame) if frame else page
    for sel in normalize_selector(selector):
        loc = target.locator(sel)
        if loc.count():
            loc.fill(value)
            return value
    target.locator(selector).fill(value)
    return value


def wait_for(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    timeout = step.params.get("timeout", 10000)
    frame = step.params.get("frame")
    page = _get_page(ctx)
    target = page.frame_locator(frame) if frame else page
    for sel in normalize_selector(selector):
        loc = target.locator(sel)
        try:
            loc.wait_for(timeout=timeout)
            return sel
        except Exception:
            continue
    target.locator(selector).wait_for(timeout=timeout)
    return selector


def download(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    path = step.params.get("path")
    frame = step.params.get("frame")
    page = _get_page(ctx)
    target = page.frame_locator(frame) if frame else page
    # Locate element prioritizing data-testid
    for sel in normalize_selector(selector):
        loc = target.locator(sel)
        if loc.count():
            chosen = loc
            break
    else:
        chosen = target.locator(selector)

    with page.expect_download() as dl_info:
        chosen.click()
    download = dl_info.value
    if path:
        download.save_as(path)
        saved = Path(path)
    else:
        saved = Path(download.path())
    if not saved.exists() or saved.stat().st_size == 0:
        raise RuntimeError("Download failed")
    return str(saved)


WEB_ACTIONS = {
    "open": open,
    "click": click,
    "fill": fill,
    "wait_for": wait_for,
    "download": download,
}
