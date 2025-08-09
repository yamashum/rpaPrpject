import pytest

from workflow.actions import BUILTIN_ACTIONS
from workflow.flow import Step, Flow, Meta
from workflow.runner import ExecutionContext


def make_context():
    flow = Flow(version="1.0", meta=Meta(name="t"))
    return ExecutionContext(flow, {})


def test_fallback_to_image_selector():
    """When UIA fails, the resolver should use the image selector."""
    step = Step(id="s1", action="launch", selector={"uia": {"exists": False}, "image": {"path": "btn.png"}})
    ctx = make_context()
    result = BUILTIN_ACTIONS["launch"](step, ctx)
    assert result["strategy"] == "image"
    assert ctx.globals["learned_selectors"] == ["image"]
