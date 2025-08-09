from workflow.flow import Flow, Meta, Step
from workflow.runner import Runner


def test_runner_skip_skips_next_step(tmp_path):
    calls = []

    def dummy(step, ctx):
        calls.append(step.id)

    flow = Flow(version="1", meta=Meta(name="t"), steps=[Step(id="s1", action="dummy"), Step(id="s2", action="dummy")])
    runner = Runner(base_dir=tmp_path)
    runner.actions["dummy"] = dummy
    runner.skip()
    runner.run_flow(flow, {})
    assert calls == ["s2"]
