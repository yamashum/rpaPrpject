from pathlib import Path

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext, Runner
from workflow import hooks


def test_screenshot_mask_hook(tmp_path):
    flow = Flow(version="1", meta=Meta(name="t"))
    ctx = ExecutionContext(flow, {})
    runner = Runner(base_dir=tmp_path)

    def masker(data: bytes) -> bytes:
        return b"masked"

    hooks.screenshot_mask_hook = masker
    try:
        artifacts = runner._capture_artifacts(Step(id="s", action="a"), Exception("boom"))
        shot_path = Path(artifacts["screenshot"])
        assert shot_path.read_bytes() == b"masked"
    finally:
        hooks.screenshot_mask_hook = None
