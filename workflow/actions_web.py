"""Web automation actions implemented using Playwright.

Available actions: ``open``, ``click``, ``dblclick``, ``right_click``,
``fill``, ``select``, ``upload``, ``wait_for``, ``download``, ``evaluate``
and ``screenshot``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import time

try:  # pragma: no cover - optional dependency
    from playwright.sync_api import Page, sync_playwright
except Exception:  # pragma: no cover - optional dependency
    Page = Any  # type: ignore
    sync_playwright = None

from .flow import Step
from .runner import ExecutionContext
from .selector import normalize_selector
from .hooks import apply_screenshot_mask

_PW_KEY = "_playwright"
_BROWSER_KEY = "_browser"
_PAGE_KEY = "_page"


def _get_page(
    ctx: ExecutionContext,
    *,
    profile: str | None = None,
    headless: bool | None = True,
    proxy: str | None = None,
) -> Page:
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
        # Persist launch options so subsequent calls don't need to provide them
        opts = ctx.globals.get("_browser_opts") or {}
        if profile is not None or headless is not None or proxy is not None:
            opts = {"profile": profile, "headless": headless, "proxy": proxy}
            ctx.globals["_browser_opts"] = opts
        else:
            profile = opts.get("profile")
            headless = opts.get("headless", True)
            proxy = opts.get("proxy")

        launch_kwargs: dict[str, Any] = {}
        if headless is not None:
            launch_kwargs["headless"] = headless
        if proxy:
            launch_kwargs["proxy"] = {"server": proxy}

        if profile:
            browser = pw.chromium.launch_persistent_context(profile, **launch_kwargs)
        else:
            browser = pw.chromium.launch(**launch_kwargs)
        ctx.globals[_BROWSER_KEY] = browser

    # ``launch_persistent_context`` returns a BrowserContext directly which may
    # already contain a page.  Otherwise create a new one.
    if hasattr(browser, "pages") and browser.pages:
        page = browser.pages[0]
    else:
        page = browser.new_page()
    ctx.globals[_PAGE_KEY] = page
    return page


def open(step: Step, ctx: ExecutionContext) -> Any:
    url = step.params["url"]
    profile = step.params.get("profile")
    headless = step.params.get("headless", True)
    proxy = step.params.get("proxy")
    page = _get_page(ctx, profile=profile, headless=headless, proxy=proxy)
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


def dblclick(step: Step, ctx: ExecutionContext) -> Any:
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
            loc.dblclick()
            return sel
        except Exception as exc:  # pragma: no cover - overlay or stale element
            last_exc = exc
            continue
    try:
        target.locator(selector).dblclick()
        return selector
    except Exception as exc:  # pragma: no cover - all selectors failed
        raise RuntimeError("Element obscured") from (last_exc or exc)


def right_click(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    frame = step.params.get("frame")
    page = _get_page(ctx)
    target = page.frame_locator(frame) if frame else page
    for sel in normalize_selector(selector):
        loc = target.locator(sel)
        if not loc.count():
            continue
        try:
            loc.click(button="right")
            return sel
        except Exception:
            continue
    target.locator(selector).click(button="right")
    return selector


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


def select(step: Step, ctx: ExecutionContext) -> Any:
    """Select option(s) in a ``<select>`` element."""
    selector = step.params["selector"]
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

    if "option" in step.params:
        option = step.params["option"]
        result = chosen.select_option(option)
    elif "options" in step.params:
        option = step.params["options"]
        result = chosen.select_option(option)
    else:
        kwargs: dict[str, Any] = {}
        for key in ("value", "label", "index"):
            if key in step.params:
                kwargs[key] = step.params[key]
        if not kwargs:
            raise RuntimeError("No option specified")
        result = chosen.select_option(**kwargs)
    return result


def upload(step: Step, ctx: ExecutionContext) -> Any:
    """Upload files using ``set_input_files``."""
    selector = step.params["selector"]
    files = step.params.get("files") or step.params.get("file") or step.params.get("path")
    if not files:
        raise RuntimeError("No files specified")
    frame = step.params.get("frame")
    page = _get_page(ctx)
    target = page.frame_locator(frame) if frame else page
    for sel in normalize_selector(selector):
        loc = target.locator(sel)
        if loc.count():
            chosen = loc
            break
    else:
        chosen = target.locator(selector)
    chosen.set_input_files(files)
    return files


def wait_for(step: Step, ctx: ExecutionContext) -> Any:
    timeout = step.params.get("timeout", 10000)
    frame = step.params.get("frame")
    page = _get_page(ctx)

    preset = step.params.get("preset")
    target = page.frame_locator(frame) if frame else page
    if preset == "networkidle":
        page.wait_for_load_state("networkidle", timeout=timeout)
        return "networkidle"
    if preset == "url":
        url = step.params.get("url")
        if not url:
            raise RuntimeError("No url provided for preset 'url'")
        page.wait_for_url(url, timeout=timeout)
        return url
    if preset == "enabled":
        selector = step.params.get("selector")
        if not selector:
            raise RuntimeError("No selector provided for preset 'enabled'")
        for sel in normalize_selector(selector):
            loc = target.locator(sel)
            try:
                loc.wait_for(state="editable", timeout=timeout)
                return sel
            except Exception:
                continue
        target.locator(selector).wait_for(state="editable", timeout=timeout)
        return selector
    if preset == "response":
        url = step.params.get("url")
        if not url:
            raise RuntimeError("No url provided for preset 'response'")
        page.wait_for_response(url, timeout=timeout)
        return url

    # Wait for selector
    selector = step.params.get("selector")
    if selector:
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

    # Wait for page load state
    state = step.params.get("state")
    if state:
        page.wait_for_load_state(state, timeout=timeout)
        return state

    # Wait for URL match
    url = step.params.get("url")
    if url:
        page.wait_for_url(url, timeout=timeout)
        return url

    # Wait for expression evaluation
    expr = step.params.get("expr") or step.params.get("script")
    if expr:
        page.wait_for_function(expr, timeout=timeout)
        return True

    raise RuntimeError("No wait condition specified")


def download(step: Step, ctx: ExecutionContext) -> Any:
    selector = step.params["selector"]
    path = step.params.get("path")
    pattern = step.params.get("pattern")
    frame = step.params.get("frame")
    timeout = step.params.get("timeout", 30000)
    stable = step.params.get("stable", 1000)

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

    with page.expect_download(timeout=timeout) as dl_info:
        chosen.click()
    download = dl_info.value

    if pattern:
        dest_dir = Path(path) if path else Path.cwd()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / download.suggested_filename
        download.save_as(str(dest_file))
        deadline = time.time() + timeout / 1000
        last_size = -1
        stable_start: float | None = None
        saved: Path | None = None
        while True:
            matches = list(dest_dir.glob(pattern))
            if not matches:
                if time.time() > deadline:
                    raise TimeoutError("Download timeout")
                time.sleep(0.05)
                continue
            candidate = max(matches, key=lambda p: p.stat().st_mtime)
            size = candidate.stat().st_size
            if saved is None or candidate != saved:
                saved = candidate
                last_size = -1
                stable_start = None
            if size == last_size:
                if stable_start is None:
                    stable_start = time.time()
                elif (time.time() - stable_start) * 1000 >= stable:
                    break
            else:
                stable_start = None
                last_size = size
            if time.time() > deadline:
                raise TimeoutError("Download timeout")
            time.sleep(0.1)
        if size == 0:
            raise RuntimeError("Download failed")
        return str(saved)
    else:
        if path:
            download.save_as(path)
            saved = Path(path)
        else:
            saved = Path(download.path())

        # Wait until file size stabilizes
        deadline = time.time() + timeout / 1000
        last_size = -1
        stable_start: float | None = None
        while True:
            if not saved.exists():
                if time.time() > deadline:
                    raise TimeoutError("Download timeout")
                time.sleep(0.05)
                continue

            size = saved.stat().st_size
            if size == last_size:
                if stable_start is None:
                    stable_start = time.time()
                elif (time.time() - stable_start) * 1000 >= stable:
                    break
            else:
                stable_start = None
                last_size = size

            if time.time() > deadline:
                raise TimeoutError("Download timeout")
            time.sleep(0.1)

        if size == 0:
            raise RuntimeError("Download failed")
        return str(saved)


def evaluate(step: Step, ctx: ExecutionContext) -> Any:
    script = step.params["script"]
    arg = step.params.get("arg")
    page = _get_page(ctx)
    try:
        return page.evaluate(script, arg)
    except Exception as exc:
        raise RuntimeError(f"Evaluation failed: {exc}") from exc


def screenshot(step: Step, ctx: ExecutionContext) -> Any:
    path = step.params.get("path")
    selector = step.params.get("selector")
    full_page = step.params.get("fullPage", False)
    page = _get_page(ctx)

    if selector:
        for sel in normalize_selector(selector):
            loc = page.locator(sel)
            if loc.count():
                target = loc
                break
        else:
            target = page.locator(selector)
        img = target.screenshot()
    else:
        img = page.screenshot(full_page=full_page)

    img = apply_screenshot_mask(img)

    if path:
        Path(path).write_bytes(img)
        return path
    # When no path is provided return the size of the screenshot in bytes to
    # avoid sending large binary data through the workflow output.
    return len(img)


WEB_ACTIONS = {
    "open": open,
    "click": click,
    "dblclick": dblclick,
    "right_click": right_click,
    "fill": fill,
    "select": select,
    "upload": upload,
    "wait_for": wait_for,
    "download": download,
    "evaluate": evaluate,
    "screenshot": screenshot,
}
