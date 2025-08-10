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


def test_flow_requires_run_role():
    step = Step(id="log", action="log", params={"message": "hi"})
    flow = Flow(version="1", meta=Meta(name="t", roles={"run": ["runner"]}), steps=[step])
    runner = Runner()
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})
    runner.run_flow(flow, {"roles": ["runner"]})


def test_flow_other_ops_require_roles():
    flow = Flow(
        version="1",
        meta=Meta(
            name="t",
            roles={
                "view": ["viewer"],
                "edit": ["editor"],
                "publish": ["publisher"],
                "approve": ["approver"],
            },
        ),
        steps=[],
    )
    runner = Runner()
    with pytest.raises(PermissionError):
        runner.view_flow(flow, {})
    runner.view_flow(flow, {"roles": ["viewer"]})
    with pytest.raises(PermissionError):
        runner.edit_flow(flow, {"roles": ["viewer"]})
    runner.edit_flow(flow, {"roles": ["editor"]})
    with pytest.raises(PermissionError):
        runner.publish_flow(flow, {"roles": ["editor"]})
    runner.publish_flow(flow, {"roles": ["publisher"]})
    with pytest.raises(PermissionError):
        runner.approve_flow(flow, {"roles": ["publisher"]})
    runner.approve_flow(flow, {"roles": ["approver"]})
