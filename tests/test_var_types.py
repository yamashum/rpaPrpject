import pytest
from datetime import date
from pathlib import Path

from workflow.flow import Flow, Meta, VarDef
from workflow.runner import ExecutionContext


@pytest.mark.parametrize(
    "vtype,value",
    [
        ("date", "2024-01-01"),
        ("path", 123),
        ("secret", 123),
        ("array", {"a": 1}),
        ("object", [1, 2, 3]),
    ],
)
def test_type_error_on_assignment(vtype, value):
    flow = Flow(version="1", meta=Meta(name="t"), variables={"x": VarDef(type=vtype, value=None)})
    ctx = ExecutionContext(flow, {})
    with pytest.raises(TypeError):
        ctx.set_var("x", value)


@pytest.mark.parametrize(
    "vtype,value",
    [
        ("date", date(2024, 1, 1)),
        ("path", Path("/tmp")),
        ("secret", "abc"),
        ("array", [1, 2]),
        ("object", {"a": 1}),
    ],
)
def test_valid_assignment(vtype, value):
    flow = Flow(version="1", meta=Meta(name="t"), variables={"x": VarDef(type=vtype, value=None)})
    ctx = ExecutionContext(flow, {})
    ctx.set_var("x", value)
