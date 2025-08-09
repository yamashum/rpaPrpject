import pytest

from workflow.actions import BUILTIN_ACTIONS
from workflow.flow import Step, Flow, Meta
from workflow.runner import ExecutionContext
from workflow.selector import normalize_selector, suggest_selector


def make_context():
    flow = Flow(version="1.0", meta=Meta(name="t"))
    return ExecutionContext(flow, {})


def test_fallback_to_image_selector():
    """When UIA fails, the resolver should use the image selector."""
    step = Step(id="s1", action="attach", selector={"uia": {"exists": False}, "image": {"path": "btn.png"}})
    ctx = make_context()
    result = BUILTIN_ACTIONS["attach"](step, ctx)
    assert result["strategy"] == "image"
    assert ctx.globals["learned_selectors"] == ["image"]


def test_selector_normalization_and_suggestion():
    assert normalize_selector("#save") == ["[data-testid=\"save\"]", "#save"]
    assert suggest_selector("button#save") == "[data-testid=\"save\"]"
