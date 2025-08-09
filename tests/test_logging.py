import json
from workflow.logging import log_step


def test_log_step_redact(tmp_path):
    log_step("r1", tmp_path, "s1", "prompt.input", 1.0, "ok", redact=["output"], output="secret")
    content = (tmp_path / "log.jsonl").read_text().splitlines()[0]
    record = json.loads(content)
    assert record["output"] == "***"
