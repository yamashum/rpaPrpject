import json
from workflow.logging import log_step, set_step_log_callback


def test_log_step_redact(tmp_path):
    log_step("r1", tmp_path, "s1", "prompt.input", 1.0, "ok", redact=["output"], output="secret")
    content = (tmp_path / "log.jsonl").read_text().splitlines()[0]
    record = json.loads(content)
    assert record["output"] == "***"


def test_log_step_callback(tmp_path):
    got = []

    def cb(rec: dict) -> None:
        got.append(rec)

    set_step_log_callback(cb)
    log_step("r1", tmp_path, "s1", "click", 1.0, "ok")
    assert got and got[0]["stepId"] == "s1"
    set_step_log_callback(None)
