import pytest

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
