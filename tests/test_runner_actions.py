import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from workflow import actions
from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext, Runner


def build_flow(steps):
    return Flow(version="1", meta=Meta(name="t"), steps=steps)


def test_set_var_expression():
    flow = build_flow([])
    ctx = ExecutionContext(flow, {})
    ctx.set_var("a", 2, scope="flow")
    step = Step(id="1", params={"name": "b", "value": "a + 3"})
    result = actions.set_var(step, ctx)
    assert result == 5
    assert ctx.get_var("b") == 5


def test_runner_eval_expr():
    steps = [
        Step(id="1", action="set", params={"name": "x", "value": "1 + 1"}),
        Step(id="2", action="if", condition="x == 2", steps=[
            Step(id="3", action="set", params={"name": "y", "value": "x * 3"})
        ])
    ]
    flow = build_flow(steps)
    runner = Runner()
    runner.register_action("set", actions.set_var)
    ctx = ExecutionContext(flow, {})
    runner._run_steps(flow.steps, ctx)
    assert ctx.get_var("x") == 2
    assert ctx.get_var("y") == 6
