"""Web automation actions implemented using Playwright."""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    from playwright.sync_api import Page, sync_playwright
except Exception:  # pragma: no cover - optional dependency
    Page = Any  # type: ignore
    sync_playwright = None

from .flow import Step
from .runner import ExecutionContext

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
    page.goto(url)
    return url


def click(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    page = _get_page(ctx)
    page.click(selector)
    return selector


def fill(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    value = step.params.get("value", "")
    page = _get_page(ctx)
    page.fill(selector, value)
    return value


def wait_for(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    timeout = step.params.get("timeout", 10000)
    page = _get_page(ctx)
    page.wait_for_selector(selector, timeout=timeout)
    return selector


def download(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    path = step.params.get("path")
    page = _get_page(ctx)
    with page.expect_download() as dl_info:
        page.click(selector)
    download = dl_info.value
    if path:
        download.save_as(path)
        return path
    tmp = download.path()
    return str(tmp)


WEB_ACTIONS = {
    "open": open,
    "click": click,
    "fill": fill,
    "wait_for": wait_for,
    "download": download,
}
