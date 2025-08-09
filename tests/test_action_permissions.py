from pathlib import Path

import pytest

from workflow.flow import Flow, Meta, Step
from workflow.runner import Runner
from workflow.actions import BUILTIN_ACTIONS


def build_runner(tmp_path: Path) -> Runner:
    runner = Runner(run_id="t", base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    return runner


def test_requires_permission(tmp_path):
    step = Step(id="s", action="launch")
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("launch", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["desktop.uia"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}


def test_web_permission(tmp_path):
    step = Step(id="s", action="open", params={"url": "http://example.com"})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("open", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["web"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}


def test_desktop_image_permission(tmp_path):
    step = Step(id="s", action="find_image", params={"path": "img.png"})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("find_image", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["desktop.image"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}


def test_excel_permission(tmp_path):
    step = Step(id="s", action="excel.open", params={"path": "file.xlsx"})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("excel.open", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["excel.com"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}


def test_office_permission(tmp_path):
    step = Step(id="s", action="word.open", params={"path": "file.docx"})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("word.open", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["office"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}


def test_http_permission(tmp_path):
    step = Step(id="s", action="http.get", params={"url": "http://example.com"})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("http.get", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["http"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}


def test_file_permission(tmp_path):
    step = Step(id="s", action="file.read", params={"path": "file.txt"})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    runner = build_runner(tmp_path)

    with pytest.raises(PermissionError):
        runner.run_flow(flow, {})

    runner.register_action("file.read", lambda step, ctx: True)
    flow_ok = Flow(version="1", meta=Meta(name="t", permissions=["files"]), steps=[step])
    assert runner.run_flow(flow_ok, {}) == {}

