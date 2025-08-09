import json
import socket
import getpass

from workflow.flow import Flow
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS
from workflow import scheduler


def test_log_includes_environment_and_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "gethostname", lambda: "host1")
    monkeypatch.setattr(getpass, "getuser", lambda: "user1")
    monkeypatch.setattr(
        scheduler,
        "_get_display_info",
        lambda: {"dpi": 123, "monitors": [{"width": 1, "height": 2}]},
    )

    flow_dict = {
        "version": "1.0",
        "meta": {"name": "wf"},
        "steps": [
            {
                "id": "s1",
                "action": "fail_once",
                "selector": {"css": "btn"},
                "retry": 1,
            }
        ],
    }
    flow = Flow.from_dict(flow_dict)

    state = {"fail": True}

    def fail_once(step, ctx):
        if state["fail"]:
            state["fail"] = False
            raise ValueError("boom")
        return "done"

    runner = Runner(run_id="run1", base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    runner.register_action("fail_once", fail_once)

    runner.run_flow(flow, {})

    log_file = runner.run_dir / "log.jsonl"
    records = [json.loads(line) for line in log_file.read_text().splitlines()]
    rec = records[-1]
    assert rec["host"] == "host1"
    assert rec["user"] == "user1"
    assert rec["dpi"] == 123
    assert rec["monitors"] == [{"width": 1, "height": 2}]
    assert rec["selectorUsed"] == {"css": "btn"}
    assert rec["retries"] == 1
    assert rec["fallbackUsed"] is True
