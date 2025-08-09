import types
import pytest

from workflow.flow import Step
from workflow import config
from workflow import actions_web


class DummyElement:
    def __init__(self, visible=True, value=""):
        self._visible = visible
        self._value = value

    def is_visible(self):
        return self._visible

    def get_value(self):
        return self._value


class DummyPage:
    def __init__(self):
        self.calls = []

    def wait_for_load_state(self, state, timeout=None):
        self.calls.append(("state", state, timeout))

    def wait_for_url(self, url, timeout=None):
        self.calls.append(("url", url, timeout))


def test_spinner_disappear(monkeypatch):
    step = Step(id="s", selector={"uia": {}}, params={})

    monkeypatch.setattr(config, "resolve_selector", lambda sel: {"target": DummyElement(True)})
    assert config.WAIT_PRESETS["spinner_disappear"](step, None) is False

    monkeypatch.setattr(config, "resolve_selector", lambda sel: {"target": DummyElement(False)})
    assert config.WAIT_PRESETS["spinner_disappear"](step, None) is True


def test_overlay_disappear(monkeypatch):
    class Elem:
        def __init__(self, overlay=True):
            self._overlay = overlay

        def has_overlay(self):
            return self._overlay

    step = Step(id="o", selector={"uia": {}}, params={})
    elem = Elem(True)
    monkeypatch.setattr(config, "resolve_selector", lambda sel: {"target": elem})
    assert config.WAIT_PRESETS["overlay_disappear"](step, None) is False
    elem._overlay = False
    assert config.WAIT_PRESETS["overlay_disappear"](step, None) is True


def test_value_equals(monkeypatch):
    step = Step(id="s", selector={"uia": {}}, params={"value": "ok"})

    monkeypatch.setattr(config, "resolve_selector", lambda sel: {"target": DummyElement(value="ok")})
    assert config.WAIT_PRESETS["valueEquals"](step, None) is True

    monkeypatch.setattr(config, "resolve_selector", lambda sel: {"target": DummyElement(value="no")})
    assert config.WAIT_PRESETS["valueEquals"](step, None) is False


def test_web_wait_for_networkidle(monkeypatch):
    page = DummyPage()
    monkeypatch.setattr(actions_web, "_get_page", lambda ctx: page)
    step = Step(id="s", params={"preset": "networkidle"})
    assert actions_web.wait_for(step, None) == "networkidle"
    assert ("state", "networkidle", 10000) in page.calls


def test_web_wait_for_url_preset(monkeypatch):
    page = DummyPage()
    monkeypatch.setattr(actions_web, "_get_page", lambda ctx: page)
    step = Step(id="s", params={"preset": "url", "url": "http://example.com", "timeout": 5000})
    assert actions_web.wait_for(step, None) == "http://example.com"
    assert ("url", "http://example.com", 5000) in page.calls
