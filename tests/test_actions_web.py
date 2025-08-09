import pytest
from pathlib import Path

pytest.importorskip("playwright.sync_api")

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow.actions_web import (
    open as web_open,
    click as web_click,
    fill as web_fill,
    wait_for as web_wait_for,
    download as web_download,
)


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="test"), steps=[])
    return ExecutionContext(flow, {})


def test_playwright_actions(tmp_path):
    html = (
        "<html><body>"
        "<input id='name'>"
        "<button id='btn' onclick=\"document.getElementById('result').textContent=document.getElementById('name').value\">Go</button>"
        "<div id='result'></div>"
        "<a id='dl' href='data:text/plain,hello' download='hello.txt'>Download</a>"
        "</body></html>"
    )
    page_file = tmp_path / "index.html"
    page_file.write_text(html)
    ctx = build_ctx()

    web_open(Step(id="open", action="open", params={"url": page_file.as_uri()}), ctx)
    web_fill(Step(id="fill", action="fill", params={"selector": "#name", "value": "Alice"}), ctx)
    page = ctx.globals["_page"]
    assert page.input_value("#name") == "Alice"

    web_click(Step(id="click", action="click", params={"selector": "#btn"}), ctx)
    web_wait_for(Step(id="wait", action="wait_for", params={"selector": "#result:has-text(\"Alice\")"}), ctx)
    assert page.inner_text("#result") == "Alice"

    dl_path = tmp_path / "hello.txt"
    web_download(Step(id="dl", action="download", params={"selector": "#dl", "path": str(dl_path)}), ctx)
    assert dl_path.exists()

    ctx.globals["_browser"].close()
    ctx.globals["_playwright"].stop()


def test_frame_scoping_and_data_testid(tmp_path):
    inner = tmp_path / "inner.html"
    inner.write_text(
        "<body>"
        "<button id='a'>A</button>"
        "<button id='b' data-testid='button' onclick=\"document.body.setAttribute('data-clicked','b')\">B</button>"
        "</body>"
    )
    outer = tmp_path / "outer.html"
    outer.write_text(
        f"<html><body><iframe id='f' src='{inner.as_uri()}'></iframe></body></html>"
    )
    ctx = build_ctx()
    web_open(Step(id="open", action="open", params={"url": outer.as_uri()}), ctx)
    web_click(Step(id="c", action="click", params={"selector": "button", "frame": "#f"}), ctx)
    web_wait_for(
        Step(id="w", action="wait_for", params={"selector": "body[data-clicked='b']", "frame": "#f"}),
        ctx,
    )
    frame_body = ctx.globals["_page"].frame_locator("#f").locator("body")
    assert frame_body.get_attribute("data-clicked") == "b"
    ctx.globals["_browser"].close()
    ctx.globals["_playwright"].stop()


def test_download_verification(tmp_path):
    html = (
        "<html><body>"
        "<a data-testid='dl' href='data:text/plain,hello' download='hello.txt'>Download</a>"
        "</body></html>"
    )
    page_file = tmp_path / "index.html"
    page_file.write_text(html)
    ctx = build_ctx()
    web_open(Step(id="open", action="open", params={"url": page_file.as_uri()}), ctx)
    # Without explicit path
    tmp_path_str = web_download(Step(id="dl1", action="download", params={"selector": "dl"}), ctx)
    tmp_file = Path(tmp_path_str)
    assert tmp_file.exists() and tmp_file.read_text() == "hello"
    # With explicit path
    dest = tmp_path / "hello.txt"
    web_download(
        Step(id="dl2", action="download", params={"selector": "dl", "path": str(dest)}), ctx
    )
    assert dest.exists() and dest.read_text() == "hello"
    ctx.globals["_browser"].close()
    ctx.globals["_playwright"].stop()
