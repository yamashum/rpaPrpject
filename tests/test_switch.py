from workflow.flow import Flow
from workflow.runner import ExecutionContext, Runner
from workflow.actions import BUILTIN_ACTIONS


def run_flow_with_x(x):
    data = {
        "version": "1",
        "meta": {"name": "t"},
        "steps": [
            {"id": "set", "action": "set", "params": {"name": "x", "value": x}},
            {
                "id": "sw",
                "action": "switch",
                "switch": "vars['x']",
                "cases": [
                    {"value": 1, "steps": [{"id": "case1", "action": "set", "params": {"name": "res", "value": 1}}]},
                    {"value": 2, "steps": [{"id": "case2", "action": "set", "params": {"name": "res", "value": 2}}]},
                ],
                "default": [
                    {"id": "default", "action": "set", "params": {"name": "res", "value": 0}}
                ],
            },
        ],
    }
    flow = Flow.from_dict(data)
    ctx = ExecutionContext(flow, {})
    runner = Runner()
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    runner._run_steps(flow.steps, ctx)
    return ctx.get_var("res")


def test_switch_cases_and_default():
    assert run_flow_with_x(2) == 2
    assert run_flow_with_x(3) == 0
