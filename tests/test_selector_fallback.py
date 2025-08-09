from workflow.flow import Defaults, Flow, Meta, Step
from workflow.runner import Runner
import workflow.config as cfg


def _make_action(attempts):
    def action(step, ctx):
        # step.selector is a dict with single strategy name
        name = next(iter(step.selector)) if step.selector else None
        attempts.append(name)
        if name == "uia":
            return "ok"
        raise RuntimeError("fail")
    return action


def test_selector_order_and_retry(monkeypatch):
    # ensure profile retry/timeouts do not interfere
    monkeypatch.setitem(
        cfg.PROFILES,
        "physical",
        cfg.ProfileConfig(timeoutMs=100, retry=0, fallback=[]),
    )
    attempts = []
    runner = Runner()
    runner.register_action("test", _make_action(attempts))
    flow = Flow(
        version="1.0",
        meta=Meta(name="sel"),
        defaults=Defaults(envProfile="physical"),
        steps=[
            Step(
                id="s",
                action="test",
                selector={"uia": 1, "image": 2},
                selectorOrder=["image", "uia"],
                selectorRetry=1,
                out="r",
            )
        ],
    )
    result = runner.run_flow(flow, {})
    assert result["r"] == "ok"
    assert attempts == ["image", "image", "uia"]
