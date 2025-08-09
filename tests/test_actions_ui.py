import sys
import types
from unittest.mock import Mock

import pytest

from workflow import actions
from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="test"), steps=[])
    return ExecutionContext(flow, {})


def test_launch_activate(monkeypatch):
    ctx = build_ctx()

    mock_proc = Mock(pid=123)
    monkeypatch.setattr(actions.subprocess, "Popen", Mock(return_value=mock_proc))
    pid = actions.launch(Step(id="l", action="launch", params={"path": "app"}), ctx)
    assert pid == 123
    actions.subprocess.Popen.assert_called_once_with(["app"])

    element = Mock()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": element})
    actions.activate(Step(id="a", action="activate", selector={"mock": {}}), ctx)
    element.activate.assert_called_once()


def test_click_set_value(monkeypatch):
    class Elem:
        def __init__(self):
            self.visible_calls = 0
            self.clicked = 0
            self.text = ""

        def is_visible(self):
            self.visible_calls += 1
            return self.visible_calls >= 2

        def is_enabled(self):
            return True

        def click(self):
            self.clicked += 1

        def set_text(self, value):
            self.text = value

    elem = Elem()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": elem})
    monkeypatch.setattr(actions.time, "sleep", lambda x: None)
    ctx = build_ctx()
    actions.click(Step(id="c", action="click", selector={"mock": {}}), ctx)
    assert elem.clicked == 1
    assert elem.visible_calls >= 2
    actions.set_value(
        Step(id="s", action="set_value", selector={"mock": {}}, params={"value": "hi"}),
        ctx,
    )
    assert elem.text == "hi"


def test_find_table_row(monkeypatch):
    class Table:
        def find_row(self, criteria):
            return {"row": 1, **criteria}

    table = Table()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": table})
    ctx = build_ctx()
    row = actions.find_table_row(
        Step(id="t", action="table.find_row", selector={"mock": {}}, params={"criteria": {"name": "Bob"}}),
        ctx,
    )
    assert row["name"] == "Bob"


def test_find_image_ocr(monkeypatch):
    calls = []

    def locate(path, region=None):
        calls.append(1)
        if len(calls) < 2:
            return None
        return (1, 2, 3, 4)

    pa = types.SimpleNamespace(locateOnScreen=locate)
    sys.modules["pyautogui"] = pa
    monkeypatch.setattr(actions.time, "sleep", lambda x: None)
    ctx = build_ctx()
    box = actions.find_image(
        Step(id="f", action="find_image", params={"path": "img.png", "timeout": 100}),
        ctx,
    )
    assert box == (1, 2, 3, 4)
    assert len(calls) >= 2

    pil = types.SimpleNamespace(Image=types.SimpleNamespace(open=lambda p: "img"))
    sys.modules["PIL"] = pil
    sys.modules["PIL.Image"] = pil.Image
    sys.modules["pytesseract"] = types.SimpleNamespace(image_to_string=lambda img, lang=None: "text")
    text = actions.ocr_read(Step(id="o", action="ocr_read", params={"path": "img.png"}), ctx)
    assert text == "text"

