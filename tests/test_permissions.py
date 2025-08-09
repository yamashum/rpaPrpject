import pytest
from pathlib import Path

from workflow.flow import Flow, Meta, Step, VarDef
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def build_runner(tmp_path: Path) -> Runner:
    runner = Runner(run_id="t", base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    return runner


def test_type_error_on_assignment(tmp_path):
    step = Step(id="s", action="set", params={"name": "x", "value": "'a'"})
    flow = Flow(version="1", meta=Meta(name="t"), variables={"x": VarDef(type="int", value=0)}, steps=[step])
    runner = build_runner(tmp_path)
    with pytest.raises(TypeError):
        runner.run_flow(flow, {})


def test_permission_violation(tmp_path):
    step = Step(id="s", action="set", params={"name": "x", "value": 1})
    flow = Flow(
        version="1",
        meta=Meta(name="t"),
        variables={"x": VarDef(type="int", value=0)},
        permissions={"x": ["read"]},
        steps=[step],
    )
    runner = build_runner(tmp_path)
    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})


def test_read_permission_violation(tmp_path):
    step = Step(id="s", action="set", params={"name": "y", "value": "vars['secret']"})
    flow = Flow(
        version="1",
        meta=Meta(name="t"),
        variables={"secret": VarDef(type="int", value=1)},
        permissions={"secret": ["write"]},
        steps=[step],
    )
    runner = build_runner(tmp_path)
    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})
