import json
import pytest

from workflow.actions import BUILTIN_ACTIONS
from workflow.flow import Step, Flow, Meta
from workflow.runner import ExecutionContext
from workflow.selector import normalize_selector, suggest_selector, resolve, SelectionError
import workflow.selector as sel


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


def test_strategy_stats_affect_order(tmp_path):
    """Strategies are tried based on historical success rate."""

    run_dir = tmp_path
    # First call: UIA fails, image succeeds -> higher success rate for image
    resolve({"uia": {"exists": False}, "image": {"path": "img.png"}}, run_dir=run_dir)

    # Second call: both succeed but image should be chosen due to stats
    result = resolve({"uia": {"exists": True}, "image": {"path": "img.png"}}, run_dir=run_dir)
    assert result["strategy"] == "image"

    stats_file = run_dir / "selector_stats.json"
    data = json.loads(stats_file.read_text())
    assert data["uia"]["attempts"] >= 1
    assert data["image"]["success"] >= 1


def test_stats_persist_on_failure(tmp_path):
    run_dir = tmp_path
    with pytest.raises(SelectionError):
        resolve({"uia": {"exists": False}}, run_dir=run_dir)
    data = json.loads((run_dir / "selector_stats.json").read_text())
    assert data["uia"]["attempts"] == 1
    assert data["uia"]["success"] == 0


def test_vdi_fallback(monkeypatch):
    """Image strategy is prioritised when running in VDI mode."""

    monkeypatch.setenv("VDI_MODE", "1")
    sel._HIT_STATS = {name: {"attempts": 0, "success": 0} for name in sel._STRATEGIES}
    result = resolve({"uia": {"exists": True}, "image": {"path": "btn.png"}})
    assert result["strategy"] == "image"
