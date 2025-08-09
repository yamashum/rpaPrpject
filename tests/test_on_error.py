import pytest

from workflow.flow import Flow, Meta, Step
from workflow.runner import ExecutionContext, Runner
from workflow.actions import BUILTIN_ACTIONS


def failing_action(step, ctx):
    raise ValueError("boom")


def build_runner():
    runner = Runner()
    # register builtins
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    runner.register_action("fail", failing_action)
    return runner


def make_ctx(step):
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step])
    return ExecutionContext(flow, {})


def test_on_error_screenshot_called(monkeypatch):
    step = Step(id="s", action="fail", onError={"screenshot": True})
    ctx = make_ctx(step)
    runner = build_runner()
    called = {}

    def fake_shot(step, ctx, exc):
        called["yes"] = True

    monkeypatch.setattr(runner, "_take_screenshot", fake_shot)

    with pytest.raises(ValueError):
        runner._run_steps([step], ctx)

    assert called.get("yes") is True


def test_on_error_recover_and_continue():
    recover_step = {"id": "r", "action": "set", "params": {"name": "x", "value": 1}}
    step = Step(id="s", action="fail", onError={"recover": recover_step, "continue": True})
    ctx = make_ctx(step)
    runner = build_runner()

    runner._run_steps([step], ctx)

    assert ctx.get_var("x") == 1


def test_on_error_continue_skips_exception():
    step1 = Step(id="s", action="fail", onError={"continue": True})
    step2 = Step(id="after", action="set", params={"name": "y", "value": 5})
    flow = Flow(version="1", meta=Meta(name="t"), steps=[step1, step2])
    ctx = ExecutionContext(flow, {})
    runner = build_runner()

    runner._run_steps(flow.steps, ctx)

    assert ctx.get_var("y") == 5


def test_on_error_uiatree_webtrace_har_video(monkeypatch):
    step = Step(
        id="s",
        action="fail",
        onError={"uiatree": True, "webTrace": True, "har": True, "video": True},
    )
    ctx = make_ctx(step)
    runner = build_runner()
    called = {}

    def fake_capture(
        step,
        exc,
        *,
        uiatree=False,
        web_trace=False,
        har=False,
        video=False,
    ):
        called["uiatree"] = uiatree
        called["web_trace"] = web_trace
        called["har"] = har
        called["video"] = video
        return {}

    monkeypatch.setattr(runner, "_capture_artifacts", fake_capture)

    with pytest.raises(ValueError):
        runner._run_steps([step], ctx)

    assert called.get("uiatree") is True
    assert called.get("web_trace") is True
    assert called.get("har") is True
    assert called.get("video") is True


def test_on_error_uiatree_webtrace_files(tmp_path):
    step = Step(
        id="s",
        action="fail",
        onError={"uiatree": True, "webTrace": True, "har": True, "video": True},
    )
    ctx = make_ctx(step)
    runner = Runner(base_dir=tmp_path)
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    runner.register_action("fail", failing_action)

    with pytest.raises(ValueError):
        runner._run_steps([step], ctx)

    ui_files = list(runner.artifacts_dir.glob("*_ui.json"))
    trace_files = list(runner.artifacts_dir.glob("*_trace.json"))
    har_files = list(runner.artifacts_dir.glob("*.har"))
    video_files = list(runner.artifacts_dir.glob("*_video.mp4"))
    assert ui_files
    assert trace_files
    assert har_files
    assert video_files


def test_recover_scroll_retry_success(monkeypatch):
    """Step succeeds after executing a shorthand 'scroll' recovery."""

    def needs_scroll(step, ctx):
        if not ctx.globals.get("scrolled"):
            raise ValueError("needs scroll")
        ctx.set_var("z", 10, scope="flow")

    def fake_scroll(step, ctx):
        ctx.globals["scrolled"] = True

    step = Step(
        id="s",
        action="needs_scroll",
        retry=1,
        onError={"recover": "scroll"},
    )
    flow = Flow(version="1", meta=Meta(name="t", permissions=["desktop.uia"]), steps=[step])
    ctx = ExecutionContext(flow, {})
    runner = build_runner()
    runner.register_action("needs_scroll", needs_scroll)
    # override scroll with our fake to avoid external dependencies
    runner.register_action("scroll", fake_scroll)

    runner._run_steps([step], ctx)

    assert ctx.get_var("z") == 10
    assert ctx.globals.get("scrolled") is True

