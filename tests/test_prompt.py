import builtins
from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow.actions import prompt_input, prompt_confirm, prompt_select


def test_prompt_input_returns_default(monkeypatch):
    step = Step(id="p1", action="prompt.input", params={"message": "Enter", "default": "x"})
    flow = Flow(version="1", meta=Meta(name="test"))
    ctx = ExecutionContext(flow, {})
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert prompt_input(step, ctx) == "x"


def test_prompt_confirm_default(monkeypatch):
    step = Step(id="c1", action="prompt.confirm", params={"message": "Continue?", "default": True})
    flow = Flow(version="1", meta=Meta(name="test"))
    ctx = ExecutionContext(flow, {})
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert prompt_confirm(step, ctx) is True


def test_prompt_select_by_index(monkeypatch):
    step = Step(
        id="s1",
        action="prompt.select",
        params={"message": "Pick", "options": ["a", "b", "c"]},
    )
    flow = Flow(version="1", meta=Meta(name="test"))
    ctx = ExecutionContext(flow, {})
    monkeypatch.setattr(builtins, "input", lambda prompt="": "2")
    assert prompt_select(step, ctx) == "b"
