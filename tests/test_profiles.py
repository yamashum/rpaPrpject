import time

from workflow.flow import Defaults, Flow, Meta, Step
from workflow.runner import Runner
import workflow.config as cfg


def _make_action(attempts):
    def action(step, ctx):
        attempts.append(ctx.globals.get("profile"))
        time.sleep(0.15)
        return "done"
    return action


def test_profile_fallback(monkeypatch):
    # Shrink timeouts for faster testing
    monkeypatch.setitem(cfg.PROFILES, "physical", cfg.ProfileConfig(timeoutMs=100, retry=0, fallback=["vdi"]))
    monkeypatch.setitem(cfg.PROFILES, "vdi", cfg.ProfileConfig(timeoutMs=250, retry=0, fallback=[]))

    attempts = []
    runner = Runner()
    runner.register_action("test", _make_action(attempts))
    flow = Flow(
        version="1.0",
        meta=Meta(name="p"),
        defaults=Defaults(envProfile="physical"),
        steps=[Step(id="s", action="test", out="r")],
    )
    result = runner.run_flow(flow, {})
    assert result["r"] == "done"
    assert attempts == ["physical", "vdi"]


def test_profile_selection(monkeypatch):
    # Use only vdi profile, ensure no fallback occurs
    monkeypatch.setitem(cfg.PROFILES, "physical", cfg.ProfileConfig(timeoutMs=100, retry=0, fallback=[]))
    monkeypatch.setitem(cfg.PROFILES, "vdi", cfg.ProfileConfig(timeoutMs=250, retry=0, fallback=[]))

    attempts = []
    runner = Runner()
    runner.register_action("test", _make_action(attempts))
    flow = Flow(
        version="1.0",
        meta=Meta(name="v"),
        defaults=Defaults(envProfile="vdi"),
        steps=[Step(id="s", action="test", out="r")],
    )
    result = runner.run_flow(flow, {})
    assert result["r"] == "done"
    assert attempts == ["vdi"]
