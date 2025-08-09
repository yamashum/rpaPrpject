from workflow.flow import Flow, Meta, Step
from workflow.runner import Runner, ExecutionContext
import workflow.runner as runner_mod


def make_ctx():
    flow = Flow(version="1", meta=Meta(name="t"), steps=[])
    return ExecutionContext(flow, {})


def test_handles_uac_prompt(monkeypatch, capsys):
    runner = Runner()
    runner.register_action("noop", lambda step, ctx: None)
    step = Step(id="s", action="noop")
    ctx = make_ctx()
    uac_states = iter([True, False])
    monkeypatch.setattr(runner, "_has_uac_prompt", lambda: next(uac_states, False))
    monkeypatch.setattr(runner, "_is_secure_desktop", lambda: False)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda x: None)
    runner._run_step(step, ctx)
    out = capsys.readouterr().out
    assert "uacPrompt" in out


def test_handles_secure_desktop(monkeypatch, capsys):
    runner = Runner()
    runner.register_action("noop", lambda step, ctx: None)
    step = Step(id="s", action="noop")
    ctx = make_ctx()
    sd_states = iter([True, False])
    monkeypatch.setattr(runner, "_is_secure_desktop", lambda: next(sd_states, False))
    monkeypatch.setattr(runner, "_has_uac_prompt", lambda: False)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda x: None)
    runner._run_step(step, ctx)
    out = capsys.readouterr().out
    assert "secureDesktop" in out
