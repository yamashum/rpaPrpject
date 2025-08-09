import pytest

from workflow.actions import BUILTIN_ACTIONS
from workflow.flow import Flow, Meta, Step
from workflow.runner import Runner

from tests.mocks.mock_dom import MockDOM
from tests.mocks.mock_network import MockNetwork


DOM = MockDOM()
NETWORK = MockNetwork()


def _build_runner() -> Runner:
    runner = Runner()
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)
    runner.register_action("dom.change", lambda step, ctx: DOM.change(step.params["value"]))
    runner.register_action("dom.read", lambda step, ctx: DOM.query())
    runner.register_action("network.get", lambda step, ctx: NETWORK.get(step.params["url"]))
    return runner


@pytest.mark.regression
def test_dom_change_injection():
    runner = _build_runner()
    DOM.text = "before"
    flow = Flow(
        version="1.0",
        meta=Meta(name="dom"),
        steps=[
            Step(id="c", action="dom.change", params={"value": "after"}),
            Step(id="r", action="dom.read", out="text"),
        ],
    )
    result = runner.run_flow(flow, {})
    assert result["text"] == "after"


@pytest.mark.regression
def test_network_disconnection_injection():
    runner = _build_runner()
    NETWORK.fail = True
    flow = Flow(
        version="1.0",
        meta=Meta(name="net"),
        steps=[
            Step(
                id="n",
                action="network.get",
                params={"url": "http://example.com"},
                out="data",
            ),
        ],
    )
    with pytest.raises(ConnectionError):
        runner.run_flow(flow, {})
    NETWORK.fail = False
