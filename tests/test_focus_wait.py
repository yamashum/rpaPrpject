import json
from pathlib import Path

from workflow.flow import Flow
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def _build_runner(tmp_path: Path) -> Runner:
    runner = Runner(base_dir=tmp_path, run_id="focus")
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    return runner


def test_focus_and_wait(tmp_path, capsys):
    """A step with a target should emit focus logs and honour waitFor."""

    flow_dict = {
        "version": "1.0",
        "meta": {"name": "wf"},
        "steps": [
            {"id": "prep", "action": "set", "params": {"name": "ready", "value": True}},
            {
                "id": "s1",
                "action": "log",
                "params": {"message": "hello"},
                "waitFor": "vars['ready']",
                "target": {"app": "calc"},
            },
        ],
    }
    flow = Flow.from_dict(flow_dict)
    runner = _build_runner(tmp_path)
    runner.run_flow(flow)

    out_lines = capsys.readouterr().out.strip().splitlines()
    focus_idx = next(i for i, l in enumerate(out_lines) if '"action": "focus"' in l)
    msg_idx = next(i for i, l in enumerate(out_lines) if "hello" in l)
    assert focus_idx < msg_idx

    log_file = runner.run_dir / "log.jsonl"
    records = [json.loads(line) for line in log_file.read_text().splitlines()]
    rec = next(r for r in records if r["stepId"] == "s1")
    assert rec["output"] == "hello"
