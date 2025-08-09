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
        headers = ["id", "name", "dept"]

        def __init__(self):
            self.rows = [
                {"id": "1", "name": "Bob", "dept": "IT"},
                {"id": "2", "name": "Alice", "dept": "HR"},
            ]

    table = Table()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": table})
    ctx = build_ctx()

    row = actions.find_table_row(
        Step(id="t1", action="table.find_row", selector={"mock": {}}, params={"criteria": {"name": "Bob"}}),
        ctx,
    )
    assert row["id"] == "1"

    row = actions.find_table_row(
        Step(id="t2", action="table.find_row", selector={"mock": {}}, params={"criteria": {1: {"contains": "lic"}}}),
        ctx,
    )
    assert row["name"] == "Alice"

    row = actions.find_table_row(
        Step(id="t3", action="table.find_row", selector={"mock": {}}, params={"criteria": {"dept": {"regex": "^I"}}}),
        ctx,
    )
    assert row["dept"] == "IT"


def test_click_hit_testing_uia(monkeypatch):
    class Elem:
        def __init__(self):
            self.hit_testable = False
            self.clicked = 0

        def is_visible(self):
            return True

        def is_enabled(self):
            return True

        def hit_test(self):
            return self.hit_testable

        def click(self):
            self.clicked += 1

    elem = Elem()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "uia", "target": elem})
    monkeypatch.setattr(actions.time, "sleep", lambda x: None)
    ctx = build_ctx()

    with pytest.raises(RuntimeError):
        actions.click(Step(id="c", action="click", selector={"uia": {}}), ctx)

    elem.hit_testable = True
    actions.click(Step(id="c2", action="click", selector={"uia": {}}), ctx)
    assert elem.clicked == 1


def test_click_hit_testing_win32(monkeypatch):
    class Elem:
        def __init__(self):
            self.hit_testable = False
            self.clicked = 0

        def is_visible(self):
            return True

        def is_enabled(self):
            return True

        def click(self):
            self.clicked += 1

    elem = Elem()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "win32", "target": elem})
    monkeypatch.setattr(actions.time, "sleep", lambda x: None)
    ctx = build_ctx()

    with pytest.raises(RuntimeError):
        actions.click(Step(id="c", action="click", selector={"win32": {}}), ctx)

    elem.hit_testable = True
    actions.click(Step(id="c2", action="click", selector={"win32": {}}), ctx)
    assert elem.clicked == 1


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
    calls = {}

    def locate(path, region=None, scale=None, tolerance=None, dpi=None):
        calls.setdefault("params", []).append((scale, tolerance, dpi))
        if len(calls["params"]) < 2:
            return None
        return (1, 2, 3, 4)

    pa = types.SimpleNamespace(locateOnScreen=locate)
    sys.modules["pyautogui"] = pa
    monkeypatch.setattr(actions.time, "sleep", lambda x: None)
    ctx = build_ctx()
    box = actions.find_image(
        Step(
            id="f",
            action="find_image",
            params={"path": "img.png", "timeout": 100, "scale": 2, "tolerance": 5, "dpi": 96},
        ),
        ctx,
    )
    assert box == (1, 2, 3, 4)
    # ensure custom parameters were forwarded
    assert calls["params"][-1] == (2, 5, 96)

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


def test_click_xy_basis_preview(monkeypatch):
    ctx = build_ctx()

    calls: list[tuple[int, int]] = []

    def click(x, y):
        calls.append((x, y))

    sys.modules["pyautogui"] = types.SimpleNamespace(click=click)

    elem = types.SimpleNamespace(left=10, top=20)
    monkeypatch.setattr(
        actions, "resolve_selector", lambda s: {"strategy": "mock", "target": elem}
    )
    actions.click_xy(
        Step(
            id="e",
            action="click_xy",
            params={"x": 1, "y": 2, "basis": "Element"},
            selector={"mock": {}},
        ),
        ctx,
    )
    assert calls == [(11, 22)]

    ctx.globals["window"] = types.SimpleNamespace(left=5, top=6)
    calls.clear()
    actions.click_xy(
        Step(id="w", action="click_xy", params={"x": 1, "y": 2, "basis": "Window"}),
        ctx,
    )
    assert calls == [(6, 8)]

    calls.clear()
    coords = actions.click_xy(
        Step(id="p", action="click_xy", params={"x": 3, "y": 4, "preview": True}),
        ctx,
    )
    assert coords == (3, 4)
    assert calls == []


def test_right_click_hover_scroll_drag_drop(monkeypatch):
    ctx = build_ctx()

    class Elem:
        def __init__(self, left=10, top=20, width=30, height=40):
            self.left = left
            self.top = top
            self.width = width
            self.height = height

        def is_visible(self):
            return True

        def is_enabled(self):
            return True

    elem = Elem()
    monkeypatch.setattr(actions, "resolve_selector", lambda s: {"strategy": "mock", "target": elem})

    calls = []

    def rightClick(x, y):
        calls.append(("rc", x, y))

    def moveTo(x, y):
        calls.append(("mv", x, y))

    def scroll(amount):
        calls.append(("sc", amount))

    def dragTo(x, y, duration=0, button="left"):
        calls.append(("dd", x, y, duration, button))

    sys.modules["pyautogui"] = types.SimpleNamespace(
        rightClick=rightClick, moveTo=moveTo, scroll=scroll, dragTo=dragTo
    )

    # right_click uses element centre
    actions.right_click(Step(id="r", action="right_click", selector={"mock": {}}), ctx)
    assert calls == [("rc", 25, 40)]

    # hover moves cursor to centre
    calls.clear()
    actions.hover(Step(id="h", action="hover", selector={"mock": {}}), ctx)
    assert calls == [("mv", 25, 40)]

    # scroll moves then scrolls
    calls.clear()
    actions.scroll(
        Step(id="s", action="scroll", selector={"mock": {}}, params={"clicks": 5}),
        ctx,
    )
    assert calls == [("mv", 25, 40), ("sc", 5)]

    # drag_drop from source to destination
    src = Elem()
    dst = Elem(left=100, top=200)

    def mock_resolve(sel):
        if "src" in sel:
            return {"strategy": "mock", "target": src}
        return {"strategy": "mock", "target": dst}

    monkeypatch.setattr(actions, "resolve_selector", mock_resolve)
    calls.clear()
    actions.drag_drop(
        Step(
            id="d",
            action="drag_drop",
            selector={"src": {}},
            params={"target": {"dst": {}}, "duration": 0},
        ),
        ctx,
    )
    assert calls[0] == ("mv", 25, 40)
    assert calls[1] == ("dd", 115, 220, 0, "left")


def test_menu_select_list(monkeypatch):
    class Win:
        def __init__(self):
            self.called = None

        def menu_select(self, path):
            self.called = path

    win = Win()
    monkeypatch.setattr(
        actions, "_resolve_with_wait", lambda s, t: {"strategy": "mock", "target": win}
    )
    ctx = build_ctx()
    actions.menu_select(
        Step(id="m", action="menu.select", selector={"mock": {}}, params={"path": ["File", "Open"]}),
        ctx,
    )
    assert win.called == "File->Open"
    assert ctx.globals["learned_selectors"] == ["mock"]


def test_menu_select_string(monkeypatch):
    class Win:
        def __init__(self):
            self.called = None

        def menu_select(self, path):
            self.called = path

    win = Win()
    monkeypatch.setattr(
        actions, "_resolve_with_wait", lambda s, t: {"strategy": "mock", "target": win}
    )
    ctx = build_ctx()
    actions.menu_select(
        Step(id="m", action="menu.select", selector={"mock": {}}, params={"path": "File/Open", "delimiter": "/"}),
        ctx,
    )
    assert win.called == "File->Open"

