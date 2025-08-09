import pytest
from pathlib import Path

pytest.importorskip("playwright.sync_api")

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow.actions_web import (
    open as web_open,
    click as web_click,
    fill as web_fill,
    select as web_select,
    upload as web_upload,
    wait_for as web_wait_for,
    download as web_download,
    evaluate as web_evaluate,
    screenshot as web_screenshot,
)


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="test"), steps=[])
    return ExecutionContext(flow, {})


def test_playwright_actions(tmp_path):
    html = (
        "<html><body>"
        "<input id='name'>"
        "<select id='sel'><option value='a'>A</option><option value='b'>B</option></select>"
        "<input id='file' type='file'>"
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

    web_select(
        Step(id="sel", action="select", params={"selector": "#sel", "value": "b"}),
        ctx,
    )
    assert page.input_value("#sel") == "b"

    upload_file = tmp_path / "file.txt"
    upload_file.write_text("data")
    web_upload(
        Step(
            id="up",
            action="upload",
            params={"selector": "#file", "files": [str(upload_file)]},
        ),
        ctx,
    )
    assert (
        page.evaluate("() => document.getElementById('file').files[0].name")
        == "file.txt"
    )

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


def test_evaluate_and_screenshot(tmp_path):
    html = "<html><body><div id='v'>1</div></body></html>"
    page_file = tmp_path / "index.html"
    page_file.write_text(html)
    ctx = build_ctx()
    web_open(Step(id="open", action="open", params={"url": page_file.as_uri()}), ctx)
    result = web_evaluate(
        Step(
            id="eval",
            action="evaluate",
            params={"script": "() => document.getElementById('v').textContent"},
        ),
        ctx,
    )
    assert result == "1"

    shot = tmp_path / "shot.png"
    web_screenshot(
        Step(id="ss", action="screenshot", params={"path": str(shot)}), ctx
    )
    assert shot.exists()

    ctx.globals["_browser"].close()
    ctx.globals["_playwright"].stop()


def test_wait_for_conditions(tmp_path):
    html = (
        "<html><head>"
        "<script>setTimeout(()=>{document.body.dataset.ready='1';},100);</script>"
        "</head><body></body></html>"
    )
    page_file = tmp_path / "index.html"
    page_file.write_text(html)
    ctx = build_ctx()
    web_open(Step(id="open", action="open", params={"url": page_file.as_uri()}), ctx)
    web_wait_for(Step(id="state", action="wait_for", params={"state": "load"}), ctx)
    web_wait_for(
        Step(id="url", action="wait_for", params={"url": page_file.as_uri()}), ctx
    )
    web_wait_for(
        Step(
            id="expr",
            action="wait_for",
            params={"expr": "() => document.body.dataset.ready === '1'"},
        ),
        ctx,
    )
    ctx.globals["_browser"].close()
    ctx.globals["_playwright"].stop()
