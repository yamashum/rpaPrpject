import json
from pathlib import Path

import pytest

from workflow.flow import Flow, Meta, Step
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def build_runner(tmp_path: Path, run_id: str = "run") -> Runner:
    runner = Runner(run_id=run_id, base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    return runner


def test_log_written(tmp_path):
    step = Step(id="s", action="set", params={"name": "x", "value": 1})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path, run_id="abc")

    runner.run_flow(flow, {})

    log_file = runner.run_dir / "log.jsonl"
    assert log_file.exists()
    lines = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert lines[0]["runId"] == "abc"
    assert lines[0]["stepId"] == "s"
    assert lines[0]["result"] == "ok"


def test_failure_artifacts(tmp_path):
    def fail(step, ctx):
        raise RuntimeError("boom")

    step = Step(id="f", action="fail")
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path, run_id="err")
    runner.register_action("fail", fail)

    with pytest.raises(RuntimeError):
        runner.run_flow(flow, {})

    log_file = runner.run_dir / "log.jsonl"
    lines = [json.loads(l) for l in log_file.read_text().splitlines()]
    record = lines[0]
    assert record["result"] == "error"
    shot = Path(record["screenshot"])
    tree = Path(record["uiTree"])
    assert shot.exists() and tree.exists()
