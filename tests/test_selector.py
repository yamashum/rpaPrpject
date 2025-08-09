import json
import pytest
import sys


def _make_image(path, size=(5, 5)):
    for name in list(sys.modules):
        if name.startswith("PIL"):
            sys.modules.pop(name, None)
    from PIL import Image
    Image.new("RGB", size, color="white").save(path)

from workflow.actions import BUILTIN_ACTIONS
from workflow.flow import Step, Flow, Meta
from workflow.runner import ExecutionContext
from workflow.selector import normalize_selector, suggest_selector, resolve, SelectionError
import workflow.selector as sel


def make_context():
    flow = Flow(version="1.0", meta=Meta(name="t"))
    return ExecutionContext(flow, {})


def test_fallback_to_image_selector(tmp_path):
    """When UIA fails, the resolver should use the image selector."""
    img = tmp_path / "btn.png"
    _make_image(img, (5, 5))
    step = Step(
        id="s1",
        action="attach",
        selector={"uia": {"exists": False}, "image": {"path": str(img)}},
    )
    ctx = make_context()
    result = BUILTIN_ACTIONS["attach"](step, ctx)
    assert result["strategy"] == "image"
    assert ctx.globals["learned_selectors"] == ["image"]


def test_selector_normalization_and_suggestion():
    assert normalize_selector("#save") == [
        "[data-testid=\"save\"]",
        "#save",
        "//*[@id=\"save\"]",
    ]
    assert suggest_selector("button#save") == "[data-testid=\"save\"]"


def test_strategy_stats_affect_order(tmp_path):
    """Strategies are tried based on historical success rate."""

    img = tmp_path / "img.png"
    _make_image(img, (4, 4))
    run_dir = tmp_path
    # First call: UIA fails, image succeeds -> higher success rate for image
    resolve({"uia": {"exists": False}, "image": {"path": str(img)}}, run_dir=run_dir)

    # Second call: both succeed but image should be chosen due to stats
    result = resolve({"uia": {"exists": True}, "image": {"path": str(img)}}, run_dir=run_dir)
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


def test_vdi_fallback(monkeypatch, tmp_path):
    """Image strategy is prioritised when running in VDI mode."""

    img = tmp_path / "btn.png"
    _make_image(img, (3, 3))
    monkeypatch.setenv("VDI_MODE", "1")
    sel._HIT_STATS = {name: {"attempts": 0, "success": 0} for name in sel._STRATEGIES}
    result = resolve({"uia": {"exists": True}, "image": {"path": str(img)}})
    assert result["strategy"] == "image"


def test_anchor_learning(tmp_path):
    """Successful resolutions update stats and influence future ordering."""

    img = tmp_path / "anchor.png"
    _make_image(img, (6, 6))
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    sel._HIT_STATS = {name: {"attempts": 0, "success": 0} for name in sel._STRATEGIES}

    # First call: UIA fails but anchor succeeds
    resolve(
        {"uia": {"exists": False}, "anchor": {"image": {"path": str(img)}, "offset": {"x": 1, "y": 2}}},
        run_dir=run_dir,
    )

    # Second call: both succeed but anchor should be chosen due to stats
    result = resolve(
        {"uia": {"exists": True}, "anchor": {"image": {"path": str(img)}, "offset": {"x": 1, "y": 2}}},
        run_dir=run_dir,
    )
    assert result["strategy"] == "anchor"
    stats = json.loads((run_dir / "selector_stats.json").read_text())
    assert stats["anchor"]["success"] >= 1


def test_scope_is_merged_into_strategy_data():
    result = resolve({"uia": {"exists": True}, "scope": {"process": "app", "ignored": "x"}})
    assert result["target"]["process"] == "app"
    assert "ignored" not in result["target"]


def test_anyof_tries_candidates_with_scope():
    selector = {
        "scope": {"name": "main"},
        "anyOf": [
            {"uia": {"exists": False}},
            {"win32": {"value": 1}},
        ],
    }
    result = resolve(selector)
    assert result["strategy"] == "win32"
    assert result["target"]["name"] == "main"
