from pathlib import Path

import pytest

from workflow.flow import Flow, Meta, Step
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def build_runner(tmp_path: Path) -> Runner:
    runner = Runner(run_id="t", base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    return runner


def test_requires_permission(tmp_path):
    step = Step(id="s", action="click")
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("click", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["desktop.uia"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}

