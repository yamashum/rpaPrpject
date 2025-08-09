from pathlib import Path

import pytest

from workflow.actions import BUILTIN_ACTIONS
from workflow.runner import Runner

from tests.mocks.mock_dom import MockDOM
from tests.mocks.mock_network import MockNetwork

pytestmark = pytest.mark.regression

DOM = MockDOM()
NETWORK = MockNetwork()


def build_runner() -> Runner:
    runner = Runner()
    for name, func in BUILTIN_ACTIONS.items():
        runner.register_action(name, func)

    # Register mock actions
    runner.register_action("dom.change", lambda step, ctx: DOM.change(step.params["value"]))
    runner.register_action("dom.read", lambda step, ctx: DOM.query())
    runner.register_action("network.get", lambda step, ctx: NETWORK.get(step.params["url"]))
    return runner


def flow_path(name: str) -> str:
    return str(Path(__file__).parent / "flows" / name)


def test_dom_change_flow():
    runner = build_runner()
    DOM.text = "initial"
    result = runner.run_file(flow_path("dom_change_flow.json"))
    assert result["current"] == "updated"


def test_network_failure_flow():
    runner = build_runner()
    NETWORK.fail = True
    with pytest.raises(ConnectionError):
        runner.run_file(flow_path("network_failure_flow.json"))
    NETWORK.fail = False
