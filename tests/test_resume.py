import pytest

from workflow.flow import Flow
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def test_resume_from_failed_step(tmp_path):
    flow_dict = {
        "version": "1.0",
        "meta": {"name": "test"},
        "steps": [
            {"id": "s1", "action": "set", "params": {"name": "x", "value": 1}},
            {"id": "s2", "action": "fail_once"},
            {"id": "s3", "action": "set", "params": {"name": "result", "value": "vars['x']"}},
        ],
    }
    flow = Flow.from_dict(flow_dict)

    state = {"fail": True}

    def fail_once(step, ctx):
        if state["fail"]:
            state["fail"] = False
            raise ValueError("boom")
        return "ok"

    runner = Runner(run_id="run1", base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    runner.register_action("fail_once", fail_once)

    with pytest.raises(ValueError):
        runner.run_flow(flow, {})

    checkpoint = runner.run_dir / "s2_ctx.json"
    assert checkpoint.exists()

    runner2 = Runner(run_id="run2", base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner2.register_action(name, func)
    runner2.register_action("fail_once", fail_once)

    vars_after = runner2.resume_flow(flow, "s2", checkpoint)
    assert vars_after["result"] == 1

    log = (runner2.run_dir / "log.jsonl").read_text().splitlines()
    assert not any("\"stepId\": \"s1\"" in line for line in log)
    assert any("\"stepId\": \"s2\"" in line for line in log)
    assert any("\"stepId\": \"s3\"" in line for line in log)
