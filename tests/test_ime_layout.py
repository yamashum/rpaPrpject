import types
import sys

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow import actions


def build_ctx():
    flow = Flow(version="1", meta=Meta(name="test"), steps=[])
    return ExecutionContext(flow, {})


def test_ime_toggle(monkeypatch):
    calls = []
    pa = types.SimpleNamespace(hotkey=lambda *keys: calls.append(keys))
    sys.modules["pyautogui"] = pa
    ctx = build_ctx()
    actions.ime_on(Step(id="i1", action="ime.on"), ctx)
    actions.ime_off(Step(id="i2", action="ime.off"), ctx)
    assert calls == [("ctrl", "space"), ("ctrl", "space")]
    assert ctx.globals["ime_state"] == "off"


def test_layout_switch(monkeypatch):
    calls = []
    pa = types.SimpleNamespace(hotkey=lambda *keys: calls.append(keys))
    sys.modules["pyautogui"] = pa
    ctx = build_ctx()
    actions.switch_layout(
        Step(id="l1", action="layout.switch", params={"layout": "us"}), ctx
    )
    assert calls == [("alt", "shift")]
    assert ctx.globals["keyboard_layout"] == "us"
