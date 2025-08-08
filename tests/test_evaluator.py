import pathlib
import sys

import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from workflow.evaluator import safe_eval


def test_arithmetic_and_variables():
    assert safe_eval("1 + 2 * 3", {}) == 7
    assert safe_eval("a - b", {"a": 5, "b": 2}) == 3


def test_comparisons_and_boolean():
    vars = {"x": 10, "y": 5}
    assert safe_eval("x > y", vars) is True
    assert safe_eval("x < y or x == 10", vars) is True


def test_disallows_bad_nodes():
    with pytest.raises(Exception):
        safe_eval("__import__('os')", {})
