"""Restricted expression evaluator used by the workflow engine."""

from __future__ import annotations

import ast
import operator
from typing import Any, Mapping, Optional


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


class _SafeEval(ast.NodeVisitor):
    def __init__(self, variables: Mapping[str, Any], functions: Optional[Mapping[str, Any]] = None) -> None:
        self.variables = dict(variables)
        self.functions = dict(functions or {})

    def visit_Expression(self, node: ast.Expression) -> Any:  # pragma: no cover - trivial
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.variables:
            return self.variables[node.id]
        raise NameError(node.id)

    def visit_Constant(self, node: ast.Constant) -> Any:  # pragma: no cover - trivial
        return node.value

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        op = _BIN_OPS.get(type(node.op))
        if not op:
            raise ValueError("Operation not allowed")
        return op(self.visit(node.left), self.visit(node.right))

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        op = _UNARY_OPS.get(type(node.op))
        if not op:
            raise ValueError("Operation not allowed")
        return op(self.visit(node.operand))

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not self.visit(value):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for value in node.values:
                if self.visit(value):
                    return True
            return False
        raise ValueError("Operation not allowed")

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            func = _CMP_OPS.get(type(op))
            if not func:
                raise ValueError("Operation not allowed")
            if not func(left, right):
                return False
            left = right
        return True

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Calls not allowed")
        func = self.functions.get(node.func.id)
        if func is None:
            raise ValueError(f"Function '{node.func.id}' not allowed")
        args = [self.visit(a) for a in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords}
        return func(*args, **kwargs)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        value = self.visit(node.value)
        slice_value = self.visit(node.slice)
        return value[slice_value]

    def visit_List(self, node: ast.List) -> Any:  # pragma: no cover - trivial
        return [self.visit(e) for e in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> Any:  # pragma: no cover - trivial
        return tuple(self.visit(e) for e in node.elts)

    def visit_Dict(self, node: ast.Dict) -> Any:  # pragma: no cover - trivial
        return {self.visit(k): self.visit(v) for k, v in zip(node.keys, node.values)}

    def generic_visit(self, node: ast.AST) -> Any:  # pragma: no cover - safety
        raise ValueError(f"Unsupported expression: {type(node).__name__}")


def safe_eval(expr: str, variables: Optional[Mapping[str, Any]] = None, functions: Optional[Mapping[str, Any]] = None) -> Any:
    """Evaluate *expr* using only the supplied *variables* and *functions*."""

    tree = ast.parse(expr, mode="eval")
    evaluator = _SafeEval(variables or {}, functions)
    return evaluator.visit(tree)
