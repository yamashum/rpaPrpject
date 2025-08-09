"""Interpreter for workflow definitions."""

from __future__ import annotations

import json
import time
import os
import fcntl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, IO, List, Optional, Set

from .flow import Flow, Step
from .safe_eval import safe_eval
from .logging import log_step, mask_pii
from .config import PROFILES, WAIT_PRESETS, get_profile_chain

# Mapping of action names to required roles
SENSITIVE_ACTION_ROLES: Dict[str, Set[str]] = {
    "prompt.input": {"user"},
    "prompt.confirm": {"user"},
    "prompt.select": {"user"},
}


class BreakFlow(Exception):
    pass


class ContinueFlow(Exception):
    pass


@dataclass
class ExecutionContext:
    flow: Flow
    inputs: Dict[str, Any]
    globals: Dict[str, Any] = field(default_factory=dict)
    roles: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.flow_vars = dict(self.flow.inputs)
        self.var_types: Dict[str, str] = {}
        for name, vdef in self.flow.variables.items():
            self.flow_vars[name] = vdef.value
            self.var_types[name] = vdef.type
        self.flow_vars.update(self.inputs)
        self.permissions: Dict[str, Set[str]] = {
            k: set(v) for k, v in self.flow.permissions.items()
        }
        self.locals_stack: List[Dict[str, Any]] = []
        roles_input = self.inputs.get("roles")
        if isinstance(roles_input, (list, set, tuple)):
            self.roles = set(roles_input)
        elif isinstance(roles_input, str):
            self.roles = {roles_input}

    # ----- variable helpers -----
    def push_local(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self.locals_stack.append(initial or {})

    def pop_local(self) -> None:
        self.locals_stack.pop()

    def _check_write(self, name: str) -> None:
        if "write" not in self.permissions.get(name, {"read", "write"}):
            raise PermissionError(f"Write not permitted for variable '{name}'")

    def _check_read(self, name: str) -> None:
        if "read" not in self.permissions.get(name, {"read", "write"}):
            raise PermissionError(f"Read not permitted for variable '{name}'")

    def _has_var(self, name: str) -> bool:
        for scope in reversed(self.locals_stack):
            if name in scope:
                return True
        return name in self.flow_vars or name in self.globals

    def set_var(self, name: str, value: Any, scope: str = "local") -> None:
        self._check_write(name)
        expected = self.var_types.get(name)
        if expected and expected != "any":
            type_map = {"int": int, "float": float, "str": str, "bool": bool}
            py_type = type_map.get(expected)
            if py_type and not isinstance(value, py_type):
                raise TypeError(f"Variable '{name}' expects {expected}")
        if scope == "global":
            self.globals[name] = value
        elif scope == "flow":
            self.flow_vars[name] = value
        else:
            if not self.locals_stack:
                self.locals_stack.append({})
            self.locals_stack[-1][name] = value

    def get_var(self, name: str) -> Any:
        self._check_read(name)
        for scope in reversed(self.locals_stack):
            if name in scope:
                return scope[name]
        if name in self.flow_vars:
            return self.flow_vars[name]
        if name in self.globals:
            return self.globals[name]
        raise KeyError(name)

    def all_vars(self) -> Dict[str, Any]:
        env = _EnvProxy(self)
        env["vars"] = env
        return env


class _EnvProxy(dict):
    """Mapping proxy that enforces read permissions on access."""

    def __init__(self, ctx: ExecutionContext):
        super().__init__()
        self._ctx = ctx
        for scope in ctx.locals_stack:
            for k, v in scope.items():
                if "read" in ctx.permissions.get(k, {"read", "write"}):
                    super().__setitem__(k, v)
        for k, v in ctx.flow_vars.items():
            if "read" in ctx.permissions.get(k, {"read", "write"}):
                super().__setitem__(k, v)
        for k, v in ctx.globals.items():
            if "read" in ctx.permissions.get(k, {"read", "write"}):
                super().__setitem__(k, v)

    def __contains__(self, key: object) -> bool:  # type: ignore[override]
        if key == "vars":
            return True
        if isinstance(key, str) and self._ctx._has_var(key):
            self._ctx._check_read(key)
            return True
        return super().__contains__(key)  # pragma: no cover - defensive

    def __getitem__(self, key: str) -> Any:  # type: ignore[override]
        if key == "vars":
            return self
        return self._ctx.get_var(key)


ActionFunc = Callable[[Step, ExecutionContext], Any]


class Runner:
    """Execute a :class:`Flow` step by step."""

    def __init__(self, run_id: Optional[str] = None, base_dir: Path | str = Path("runs")) -> None:
        self.actions: Dict[str, ActionFunc] = {}
        self.paused = False
        self.stopped = False
        self.skip_requested = False
        self.run_id = run_id or str(int(time.time() * 1000))
        self.base_dir = Path(base_dir)
        self.lock_path = self.base_dir / "runner.lock"
        self._lock_file: Optional[IO[str]] = None
        self.run_dir = self.base_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = self.run_dir / "artifacts"
        self.artifacts_dir.mkdir(exist_ok=True)

    def _acquire_lock(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = open(self.lock_path, "w")
        fcntl.flock(self._lock_file, fcntl.LOCK_EX)

    def _release_lock(self) -> None:
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            finally:
                self._lock_file.close()
                self._lock_file = None
                try:
                    self.lock_path.unlink()
                except OSError:
                    pass

    # ----- registration -----
    def register_action(self, name: str, func: ActionFunc) -> None:
        self.actions[name] = func

    # ----- public API -----
    def run_file(self, path: str, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = json.loads(Path(path).read_text())
        flow = Flow.from_dict(data)
        return self.run_flow(flow, inputs or {})

    def run_flow(self, flow: Flow, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._acquire_lock()
        try:
            ctx = ExecutionContext(flow, inputs or {})
            required = set(flow.meta.permissions)
            if required and not required.issubset(ctx.roles):
                raise PermissionError(
                    f"Flow requires roles {sorted(required)}"
                )
            self._run_steps(flow.steps, ctx)
            return ctx.flow_vars
        finally:
            self._release_lock()

    def resume_flow(self, flow: Flow, start_step_id: str, checkpoint_path: Path | str) -> Dict[str, Any]:
        state = json.loads(Path(checkpoint_path).read_text())
        ctx = ExecutionContext(flow, {})
        required = set(flow.meta.permissions)
        if required and not required.issubset(ctx.roles):
            raise PermissionError(
                f"Flow requires roles {sorted(required)}"
            )
        ctx.flow_vars.update(state.get("flow_vars", {}))
        ctx.globals.update(state.get("globals", {}))
        index = next((i for i, s in enumerate(flow.steps) if s.id == start_step_id), None)
        if index is None:
            return ctx.flow_vars
        self._run_steps(flow.steps[index:], ctx)
        return ctx.flow_vars

    # ----- secure desktop / UAC handling -----
    def _has_uac_prompt(self) -> bool:
        return os.getenv("UAC_PROMPT", "").lower() in {"1", "true", "yes"}

    def _is_secure_desktop(self) -> bool:
        return os.getenv("SECURE_DESKTOP", "").lower() in {"1", "true", "yes"}

    def _handle_secure_desktop(self) -> None:
        if self._has_uac_prompt():
            print(json.dumps({"event": "uacPrompt"}))
            while self._has_uac_prompt():
                time.sleep(0.1)
        if self._is_secure_desktop():
            print(json.dumps({"event": "secureDesktop"}))
            while self._is_secure_desktop():
                time.sleep(0.1)

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

    def _wait_for_preset(
        self,
        func: Callable[[Step, ExecutionContext], bool],
        step: Step,
        ctx: ExecutionContext,
        timeout_ms: int,
    ) -> None:
        """Repeatedly call ``func`` until it returns True or timeout."""

        end_time = time.time() + timeout_ms / 1000.0
        while time.time() < end_time:
            try:
                if func(step, ctx):
                    return
            except Exception:
                pass
            time.sleep(0.1)
        raise TimeoutError("waitFor condition not met")

    def _focus_target(self, step: Step, ctx: ExecutionContext) -> None:
        """Placeholder to focus the UI element/window specified in ``step.target``.

        Real implementations would bring the target application window to the
        foreground. For testing purposes we simply emit a structured log so that
        the behaviour can be asserted."""

        if step.target is None:
            return
        print(json.dumps({"stepId": step.id, "action": "focus", "target": step.target}))

    def _save_context(self, step: Step, ctx: ExecutionContext) -> None:
        state = {"globals": ctx.globals, "flow_vars": ctx.flow_vars}
        path = self.run_dir / f"{step.id}_ctx.json"
        path.write_text(json.dumps(state))

    def _run_step(self, step: Step, ctx: ExecutionContext) -> None:
        if step.break_flag:
            raise BreakFlow()
        if step.continue_flag:
            raise ContinueFlow()

        if self.skip_requested:
            self.skip_requested = False
            log_step(self.run_id, self.run_dir, step.id, step.action, 0.0, "skipped")
            print(json.dumps({"stepId": step.id, "action": step.action, "result": "skipped"}))
            return

        self._save_context(step, ctx)
        self._handle_secure_desktop()

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
        required = SENSITIVE_ACTION_ROLES.get(step.action, set())
        if required and not required.issubset(ctx.roles):
            raise PermissionError(
                f"Action '{step.action}' requires roles {sorted(required)}"
            )
        func = self.actions.get(step.action)
        if not func:
            log_step(self.run_id, self.run_dir, step.id, step.action, 0.0, "unknown")
            return
        ctx.push_local()
        original_selector = step.selector
        last_exc: Optional[Exception] = None
        profiles = get_profile_chain(ctx.flow.defaults.envProfile)
        for pname in profiles:
            profile = PROFILES.get(pname)
            if profile is None:
                continue
            retry = (
                step.retry
                if step.retry is not None
                else (
                    ctx.flow.defaults.retry
                    if ctx.flow.defaults.retry is not None
                    else profile.retry
                )
            )
            timeout_ms = (
                step.timeoutMs
                if step.timeoutMs is not None
                else (
                    ctx.flow.defaults.timeoutMs
                    if ctx.flow.defaults.timeoutMs is not None
                    else profile.timeoutMs
                )
            )

            selectors = [original_selector]
            if isinstance(original_selector, dict):
                ordered = [s for s in profile.selectors if s in original_selector]
                if ordered:
                    selectors = [{name: original_selector[name]} for name in ordered]

            for sel in selectors:
                step.selector = sel
                for attempt in range(retry + 1):
                    start = time.time()
                    ctx.globals["profile"] = pname
                    try:
                        if step.target:
                            self._focus_target(step, ctx)
                        if step.waitFor:
                            preset = WAIT_PRESETS.get(step.waitFor)
                            if preset is not None:
                                self._wait_for_preset(preset, step, ctx, timeout_ms)
                            else:
                                self._wait_for_condition(step.waitFor, ctx, timeout_ms)
                        result = func(step, ctx)
                        duration = (time.time() - start) * 1000.0
                        if duration > timeout_ms:
                            raise TimeoutError(
                                f"Step '{step.id}' exceeded {timeout_ms}ms"
                            )
                        if step.out:
                            ctx.set_var(step.out, result, scope="flow")
                        redact = None
                        if step.action == "prompt.input" and step.params.get("mask"):
                            redact = ["output"]
                        log_step(
                            self.run_id,
                            self.run_dir,
                            step.id,
                            step.action,
                            duration,
                            "ok",
                            output=result,
                            redact=redact,
                        )
                        display = "***" if redact else result
                        print(
                            json.dumps(
                                {
                                    "stepId": step.id,
                                    "action": step.action,
                                    "result": "ok",
                                    "output": display,
                                }
                            )
                        )
                        ctx.pop_local()
                        step.selector = original_selector
                        return
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
                        print(
                            json.dumps(
                                {
                                    "stepId": step.id,
                                    "action": step.action,
                                    "result": "error",
                                    "error": str(exc),
                                }
                            )
                        )
                        # ----- onError handling -----
                        oe = step.onError or {}
                        if oe.get("screenshot"):
                            self._take_screenshot(step, ctx, exc)
                        if oe.get("recover"):
                            self._recover(oe["recover"], ctx)
                        if oe.get("continue"):
                            ctx.pop_local()
                            step.selector = original_selector
                            return
                        if attempt == retry:
                            break
                        time.sleep(0.1 * (2 ** attempt))
            step.selector = original_selector
        ctx.pop_local()
        if last_exc is not None:
            raise last_exc

    # ----- control -----
    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def stop(self) -> None:
        self.stopped = True
        self._release_lock()

    def skip(self) -> None:
        self.skip_requested = True

    # ----- error helpers -----
    def _take_screenshot(self, step: Step, ctx: ExecutionContext, exc: Exception) -> None:
        """Placeholder screenshot handler.

        Real implementation would capture the current screen. Here we simply
        emit a log entry so tests can verify it was invoked."""
        print(
            json.dumps(
                {
                    "stepId": step.id,
                    "action": "screenshot",
                    "error": mask_pii(str(exc)),
                }
            )
        )

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
