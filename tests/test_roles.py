import builtins
import pytest
from workflow.flow import Flow, Meta, Step
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def test_runner_requires_role(monkeypatch):
    step = Step(id="p", action="prompt.input", params={"message": "", "default": "x"}, out="ans")
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = Runner()
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")
    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})
    result = runner.run_flow(flow, {"roles": ["user"], "approval_level": 1})
    assert result["ans"] == "y"
