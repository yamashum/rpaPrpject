import builtins
from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext
from workflow.actions import prompt_input


def test_prompt_input_returns_default(monkeypatch):
    step = Step(id="p1", action="prompt.input", params={"message": "Enter", "default": "x"})
    flow = Flow(version="1", meta=Meta(name="test"))
    ctx = ExecutionContext(flow, {})
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert prompt_input(step, ctx) == "x"
