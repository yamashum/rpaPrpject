from __future__ import annotations

import ast
import operator as op
from typing import Any, Dict

# Mapping of supported binary operators to their functions
_BIN_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}

_UNARY_OPS = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}

_CMP_OPS = {
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
}


def safe_eval(expr: str, variables: Dict[str, Any]) -> Any:
    """Safely evaluate an arithmetic expression with variables.

    Only arithmetic operations, comparisons and variable references are allowed.
    """
    tree = ast.parse(expr, mode="eval")
    return _eval(tree.body, variables)


def _eval(node: ast.AST, variables: Dict[str, Any]) -> Any:
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise ValueError("Unsupported operator")
        left = _eval(node.left, variables)
        right = _eval(node.right, variables)
        return _BIN_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _UNARY_OPS:
            raise ValueError("Unsupported unary operator")
        operand = _eval(node.operand, variables)
        return _UNARY_OPS[op_type](operand)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, variables)
        for op_node, comparator in zip(node.ops, node.comparators):
            op_type = type(op_node)
            if op_type not in _CMP_OPS:
                raise ValueError("Unsupported comparison operator")
            right = _eval(comparator, variables)
            if not _CMP_OPS[op_type](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(v, variables) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_eval(v, variables) for v in node.values)
        raise ValueError("Unsupported boolean operator")
    if isinstance(node, ast.Name):
        if node.id in variables:
            return variables[node.id]
        raise NameError(node.id)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValueError("Constants of type %s are not allowed" % type(node.value).__name__)
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")
