"""Interpreter for workflow definitions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .flow import Flow, Step
from .safe_eval import safe_eval
from .logging import log_step


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

    def __init__(self, run_id: Optional[str] = None, base_dir: Path | str = Path("runs")) -> None:
        self.actions: Dict[str, ActionFunc] = {}
        self.paused = False
        self.stopped = False
        self.run_id = run_id or str(int(time.time() * 1000))
        self.base_dir = Path(base_dir)
        self.run_dir = self.base_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.run_dir / "artifacts"
        self.artifacts_dir.mkdir(exist_ok=True)

    # ----- registration -----
    def register_action(self, name: str, func: ActionFunc) -> None:
        self.actions[name] = func

    # ----- public API -----
    def run_file(self, path: str, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = json.loads(Path(path).read_text())
        flow = Flow.from_dict(data)
        return self.run_flow(flow, inputs or {})

    def run_flow(self, flow: Flow, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ctx = ExecutionContext(flow, inputs or {})
        self._run_steps(flow.steps, ctx)
        return ctx.flow_vars

    def resume_flow(self, flow: Flow, start_step_id: str, checkpoint_path: Path | str) -> Dict[str, Any]:
        state = json.loads(Path(checkpoint_path).read_text())
        ctx = ExecutionContext(flow, {})
        ctx.flow_vars.update(state.get("flow_vars", {}))
        ctx.globals.update(state.get("globals", {}))
        index = next((i for i, s in enumerate(flow.steps) if s.id == start_step_id), None)
        if index is None:
            return ctx.flow_vars
        self._run_steps(flow.steps[index:], ctx)
        return ctx.flow_vars

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

    def _wait_for_condition(self, expr: str, ctx: ExecutionContext, timeout_ms: int) -> None:
        """Wait until the given expression evaluates to True or timeout."""
        end_time = time.time() + timeout_ms / 1000.0
        while time.time() < end_time:
            try:
                if self._eval_expr(expr, ctx):
                    return
            except Exception:
                pass
            time.sleep(0.1)
        raise TimeoutError(f"waitFor condition not met: {expr}")

    def _save_context(self, step: Step, ctx: ExecutionContext) -> None:
        state = {"globals": ctx.globals, "flow_vars": ctx.flow_vars}
        path = self.run_dir / f"{step.id}_ctx.json"
        path.write_text(json.dumps(state))

    def _run_step(self, step: Step, ctx: ExecutionContext) -> None:
        if step.break_flag:
            raise BreakFlow()
        if step.continue_flag:
            raise ContinueFlow()

        self._save_context(step, ctx)

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

        if step.action == "switch":
            value = self._eval_expr(step.switch_expr or "None", ctx)
            matched = False
            for case in step.cases:
                case_val = case.get("value")
                if isinstance(case_val, str):
                    case_val = self._eval_expr(case_val, ctx)
                if value == case_val:
                    self._run_steps(case.get("steps", []), ctx)
                    matched = True
                    break
            if not matched:
                self._run_steps(step.default_steps, ctx)
            print(json.dumps({"stepId": step.id, "action": "switch", "result": value}))
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
            log_step(self.run_id, self.run_dir, step.id, step.action, 0.0, "unknown")
            return
        ctx.push_local()
        retry = step.retry if step.retry is not None else ctx.flow.defaults.retry
        timeout_ms = step.timeoutMs if step.timeoutMs is not None else ctx.flow.defaults.timeoutMs
        last_exc: Optional[Exception] = None
        for attempt in range(retry + 1):
            start = time.time()
            try:
                if step.waitFor:
                    self._wait_for_condition(step.waitFor, ctx, timeout_ms)
                result = func(step, ctx)
                duration = (time.time() - start) * 1000.0
                if duration > timeout_ms:
                    raise TimeoutError(f"Step '{step.id}' exceeded {timeout_ms}ms")
                if step.out:
                    ctx.set_var(step.out, result, scope="flow")
                log_step(self.run_id, self.run_dir, step.id, step.action, duration, "ok")
                break
            except Exception as exc:
                last_exc = exc
                duration = (time.time() - start) * 1000.0
                artifacts = self._capture_artifacts(step, exc)
                log_step(
                    self.run_id,
                    self.run_dir,
                    step.id,
                    step.action,
                    duration,
                    "error",
                    error=str(exc),
                    **artifacts,
                )
                # ----- onError handling -----
                oe = step.onError or {}
                if oe.get("screenshot"):
                    self._take_screenshot(step, ctx, exc)
                if oe.get("recover"):
                    self._recover(oe["recover"], ctx)
                if oe.get("continue"):
                    ctx.pop_local()
                    return
                if attempt == retry:
                    ctx.pop_local()
                    raise
        else:
            if last_exc is not None:
                raise last_exc
        ctx.pop_local()

    # ----- control -----
    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def stop(self) -> None:
        self.stopped = True

    # ----- error helpers -----
    def _take_screenshot(self, step: Step, ctx: ExecutionContext, exc: Exception) -> None:
        """Placeholder screenshot handler.

        Real implementation would capture the current screen. Here we simply
        emit a log entry so tests can verify it was invoked."""
        print(json.dumps({"stepId": step.id, "action": "screenshot", "error": str(exc)}))

    def _capture_artifacts(self, step: Step, exc: Exception) -> Dict[str, str]:
        """Create placeholder artifact files for a failed step."""
        ts = int(time.time() * 1000)
        screenshot_path = self.artifacts_dir / f"{step.id}_{ts}.txt"
        screenshot_path.write_text("screenshot")
        ui_tree_path = self.artifacts_dir / f"{step.id}_{ts}_ui.json"
        ui_tree_path.write_text(json.dumps({}))
        return {"screenshot": str(screenshot_path), "uiTree": str(ui_tree_path)}

    def _recover(self, recover_spec: Any, ctx: ExecutionContext) -> None:
        """Execute recovery steps specified in ``onError.recover``."""
        steps_data = recover_spec
        if not isinstance(steps_data, list):
            steps_data = [steps_data]
        steps = Flow._load_steps(steps_data)
        self._run_steps(steps, ctx)
