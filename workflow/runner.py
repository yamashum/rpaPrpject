"""Interpreter for workflow definitions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .flow import Flow, Step
from .safe_eval import safe_eval


class BreakFlow(Exception):
    pass


class ContinueFlow(Exception):
    pass


@dataclass
class ExecutionContext:
    flow: Flow
    inputs: Dict[str, Any]
    globals: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.flow_vars = dict(self.flow.inputs)
        self.flow_vars.update(self.flow.variables)
        self.flow_vars.update(self.inputs)
        self.locals_stack: List[Dict[str, Any]] = []

    # ----- variable helpers -----
    def push_local(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self.locals_stack.append(initial or {})

    def pop_local(self) -> None:
        self.locals_stack.pop()

    def set_var(self, name: str, value: Any, scope: str = "local") -> None:
        if scope == "global":
            self.globals[name] = value
        elif scope == "flow":
            self.flow_vars[name] = value
        else:
            if not self.locals_stack:
                self.locals_stack.append({})
            self.locals_stack[-1][name] = value

    def get_var(self, name: str) -> Any:
        for scope in reversed(self.locals_stack):
            if name in scope:
                return scope[name]
        if name in self.flow_vars:
            return self.flow_vars[name]
        if name in self.globals:
            return self.globals[name]
        raise KeyError(name)

    def all_vars(self) -> Dict[str, Any]:
        merged = dict(self.globals)
        merged.update(self.flow_vars)
        for scope in self.locals_stack:
            merged.update(scope)
        return merged


ActionFunc = Callable[[Step, ExecutionContext], Any]


class Runner:
    """Execute a :class:`Flow` step by step."""

    def __init__(self) -> None:
        self.actions: Dict[str, ActionFunc] = {}
        self.paused = False
        self.stopped = False

    # ----- registration -----
    def register_action(self, name: str, func: ActionFunc) -> None:
        self.actions[name] = func

    # ----- public API -----
    def run_file(self, path: str, inputs: Optional[Dict[str, Any]] = None) -> None:
        data = json.loads(Path(path).read_text())
        flow = Flow.from_dict(data)
        self.run_flow(flow, inputs or {})

    def run_flow(self, flow: Flow, inputs: Optional[Dict[str, Any]] = None) -> None:
        ctx = ExecutionContext(flow, inputs or {})
        self._run_steps(flow.steps, ctx)

    # ----- core execution -----
    def _run_steps(self, steps: List[Step], ctx: ExecutionContext) -> None:
        for step in steps:
            if self.stopped:
                break
            while self.paused:
                time.sleep(0.1)
            try:
                self._run_step(step, ctx)
            except BreakFlow:
                break
            except ContinueFlow:
                continue

    def _eval_expr(self, expr: str, ctx: ExecutionContext) -> Any:
        env = ctx.all_vars()
        env = {"vars": env, **env}
        funcs = {"range": range}
        return safe_eval(expr, env, funcs)

    def _run_step(self, step: Step, ctx: ExecutionContext) -> None:
        if step.break_flag:
            raise BreakFlow()
        if step.continue_flag:
            raise ContinueFlow()

        if step.action == "if":
            cond = self._eval_expr(step.condition or "False", ctx)
            branch = step.steps if cond else step.else_steps
            self._run_steps(branch, ctx)
            print(json.dumps({"stepId": step.id, "action": "if", "result": bool(cond)}))
            return

        if step.action == "while":
            while self._eval_expr(step.while_condition or "False", ctx):
                try:
                    self._run_steps(step.steps, ctx)
                except BreakFlow:
                    break
                except ContinueFlow:
                    continue
            print(json.dumps({"stepId": step.id, "action": "while", "result": "done"}))
            return

        if step.action == "for_each":
            iterable = self._eval_expr(step.params.get("items", "[]"), ctx)
            var_name = step.for_each or "item"
            for item in iterable:
                ctx.push_local({var_name: item})
                try:
                    self._run_steps(step.steps, ctx)
                finally:
                    ctx.pop_local()
            print(json.dumps({"stepId": step.id, "action": "for_each", "count": len(iterable)}))
            return

        if step.action == "try":
            try:
                self._run_steps(step.steps, ctx)
            except Exception as exc:
                ctx.push_local({"error": exc})
                self._run_steps(step.catch_steps, ctx)
                ctx.pop_local()
            finally:
                self._run_steps(step.finally_steps, ctx)
            print(json.dumps({"stepId": step.id, "action": "try", "result": "done"}))
            return

        if step.action == "subflow":
            path = step.subflow
            if not path:
                return
            data = json.loads(Path(path).read_text())
            sub = Flow.from_dict(data)
            self._run_steps(sub.steps, ExecutionContext(sub, ctx.flow_vars))
            print(json.dumps({"stepId": step.id, "action": "subflow", "result": path}))
            return

        # actual action
        func = self.actions.get(step.action)
        if not func:
            print(json.dumps({"stepId": step.id, "action": step.action, "result": "unknown"}))
            return
        ctx.push_local()
        log = {"stepId": step.id, "action": step.action}
        retry = step.retry if step.retry is not None else ctx.flow.defaults.retry
        timeout_ms = step.timeoutMs if step.timeoutMs is not None else ctx.flow.defaults.timeoutMs
        last_exc: Optional[Exception] = None
        for attempt in range(retry + 1):
            start = time.time()
            try:
                result = func(step, ctx)
                duration = (time.time() - start) * 1000.0
                if duration > timeout_ms:
                    raise TimeoutError(f"Step '{step.id}' exceeded {timeout_ms}ms")
                if step.out:
                    ctx.set_var(step.out, result, scope="flow")
                log["result"] = "ok"
                break
            except Exception as exc:
                last_exc = exc
                log["result"] = "error"
                log["error"] = str(exc)
                if attempt == retry:
                    print(json.dumps(log))
                    ctx.pop_local()
                    raise
        else:
            if last_exc is not None:
                raise last_exc
        print(json.dumps(log))
        ctx.pop_local()

    # ----- control -----
    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def stop(self) -> None:
        self.stopped = True
