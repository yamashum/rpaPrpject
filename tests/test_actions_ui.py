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


def test_click_waits_for_overlay(monkeypatch):
    """_ensure_ready should wait until any overlay disappears before clicking."""

    class Elem:
        def __init__(self):
            self.overlay_calls = 0
            self.clicked = 0

        def is_visible(self):
            return True

        def is_enabled(self):
            return True

        def has_overlay(self):
            self.overlay_calls += 1
            return self.overlay_calls < 2

        def click(self):
            self.clicked += 1

    elem = Elem()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": elem})
    monkeypatch.setattr(actions.time, "sleep", lambda x: None)
    ctx = build_ctx()
    actions.click(Step(id="c", action="click", selector={"mock": {}}), ctx)
    assert elem.clicked == 1
    # has_overlay should have been queried until it returned False
    assert elem.overlay_calls >= 2


def test_click_reports_overlay(monkeypatch):
    class Elem:
        def is_visible(self):
            return True

        def is_enabled(self):
            return True

        def click(self):
            raise Exception("overlay")

    elem = Elem()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": elem})
    ctx = build_ctx()
    with pytest.raises(RuntimeError):
        actions.click(Step(id="c", action="click", selector={"mock": {}}), ctx)


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


def test_row_actions_scroll(monkeypatch):
    class Table:
        def __init__(self):
            self.scroll_calls = 0

        def scroll_to_row(self, row):
            self.scroll_calls += 1
            row.visible = True

    class Row:
        def __init__(self, table):
            self.table = table
            self.visible = False
            self.selected = False
            self.double_clicked = False

        def is_visible(self):
            return self.visible

        def is_enabled(self):
            return True

        def select(self):
            self.selected = True

        def double_click(self):
            self.double_clicked = True

    table = Table()
    row = Row(table)
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": row})
    monkeypatch.setattr(actions.time, "sleep", lambda x: None)
    ctx = build_ctx()

    actions.select_row(Step(id="s", action="row.select", selector={"mock": {}}), ctx)
    assert row.selected
    assert table.scroll_calls == 1

    row.visible = False
    actions.double_click_row(Step(id="d", action="row.double_click", selector={"mock": {}}), ctx)
    assert row.double_clicked
    assert table.scroll_calls == 2


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


def test_attach_double_click_select(monkeypatch):
    class Elem:
        def __init__(self):
            self.double_clicked = 0
            self.selected = None

        def is_visible(self):
            return True

        def is_enabled(self):
            return True

        def double_click(self):
            self.double_clicked += 1

        def select(self, item):
            self.selected = item

    elem = Elem()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": elem})
    ctx = build_ctx()
    attached = actions.attach(Step(id="a", action="attach", selector={"mock": {}}), ctx)
    assert attached["target"] is elem
    actions.double_click(Step(id="d", action="double_click", selector={"mock": {}}), ctx)
    assert elem.double_clicked == 1
    actions.select(
        Step(id="s", action="select", selector={"mock": {}}, params={"item": "foo"}),
        ctx,
    )
    assert elem.selected == "foo"


def test_check_uncheck_click_xy(monkeypatch):
    class Elem:
        def __init__(self, state=False):
            self.state = state
            self.check_calls = 0
            self.uncheck_calls = 0

        def is_visible(self):
            return True

        def is_enabled(self):
            return True

        def is_checked(self):
            return self.state

        def check(self):
            self.state = True
            self.check_calls += 1

        def uncheck(self):
            self.state = False
            self.uncheck_calls += 1

    elem = Elem(state=False)
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": elem})
    ctx = build_ctx()
    actions.check(Step(id="c", action="check", selector={"mock": {}}), ctx)
    assert elem.state is True and elem.check_calls == 1
    elem.state = True
    actions.uncheck(Step(id="u", action="uncheck", selector={"mock": {}}), ctx)
    assert elem.state is False and elem.uncheck_calls == 1

    calls = []

    def click(x, y):
        calls.append((x, y))

    sys.modules["pyautogui"] = types.SimpleNamespace(click=click)
    actions.click_xy(Step(id="xy", action="click_xy", params={"x": 1, "y": 2}), ctx)
    assert calls == [(1, 2)]

