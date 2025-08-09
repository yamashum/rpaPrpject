import pytest
from workflow.flow import Flow
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def _make_runner() -> Runner:
    r = Runner()
    for name, func in BUILTIN_ACTIONS.items():
        r.register_action(name, func)
    return r


def test_wait_for_times_out():
    flow_dict = {
        "version": "1.0",
        "meta": {"name": "wf"},
        "steps": [
            {
                "id": "s1",
                "action": "log",
                "params": {"message": "nope"},
                "waitFor": "False",
                "timeoutMs": 100,
            }
        ],
    }
    flow = Flow.from_dict(flow_dict)
    runner = _make_runner()
    with pytest.raises(TimeoutError):
        runner.run_flow(flow)


def test_wait_for_passes_and_executes(capsys):
    flow_dict = {
        "version": "1.0",
        "meta": {"name": "wf"},
        "inputs": {"ready": True},
        "steps": [
            {
                "id": "s1",
                "action": "log",
                "params": {"message": "done"},
                "waitFor": "vars['ready']",
            }
        ],
    }
    flow = Flow.from_dict(flow_dict)
    runner = _make_runner()
    runner.run_flow(flow)
    out = capsys.readouterr().out
    assert "done" in out
