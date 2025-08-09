import pytest

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow import actions_web
from workflow.gui_tools import element_spy, wire_to_flow


class DummyLocator:
    def __init__(self, found=True, raise_click=False):
        self._found = found
        self._raise = raise_click
        self.clicked = False

    def count(self):
        return 1 if self._found else 0

    def click(self):
        if self._raise:
            raise Exception("overlay")
        self.clicked = True


class DummyPage:
    def __init__(self, selectors=None, fail_goto=False):
        self.selectors = selectors or {}
        self.fail_goto = fail_goto

    def locator(self, sel):
        return self.selectors.get(sel, DummyLocator(False))

    def frame_locator(self, frame):
        return self

    def goto(self, url):
        if self.fail_goto:
            raise Exception("network down")
        self.url = url


def _ctx():
    flow = Flow(version="1.0", meta=Meta(name="t"))
    return ExecutionContext(flow, {})


def test_click_handles_dom_change(monkeypatch):
    selectors = {
        '[data-testid="save"]': DummyLocator(found=False),
        '#save': DummyLocator(found=True),
    }
    page = DummyPage(selectors)
    monkeypatch.setattr(actions_web, "_get_page", lambda ctx: page)
    step = Step(id="s", action="click", params={"selector": "#save"})
    result = actions_web.click(step, _ctx())
    assert result == "#save"


def test_open_network_failure(monkeypatch):
    page = DummyPage(fail_goto=True)
    monkeypatch.setattr(actions_web, "_get_page", lambda ctx: page)
    step = Step(id="s", action="open", params={"url": "http://example.com"})
    with pytest.raises(RuntimeError):
        actions_web.open(step, _ctx())


def test_click_reports_overlay(monkeypatch):
    selectors = {
        '[data-testid="save"]': DummyLocator(found=True, raise_click=True),
        '#save': DummyLocator(found=True, raise_click=True),
    }
    page = DummyPage(selectors)
    monkeypatch.setattr(actions_web, "_get_page", lambda ctx: page)
    step = Step(id="s", action="click", params={"selector": "#save"})
    with pytest.raises(RuntimeError):
        actions_web.click(step, _ctx())


def test_wiring_spy_results_to_flow():
    flow = {"steps": [{"id": "a", "action": "click"}]}
    info = element_spy("#login")
    wire_to_flow(flow, "a", {"selector": info.selector})
    assert flow["steps"][0]["params"]["selector"] == "#login"
