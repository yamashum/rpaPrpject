"""Interpreter for workflow definitions."""

from __future__ import annotations

import json
import time
import os
import fcntl
import socket
import getpass
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, IO, List, Optional, Set

from .flow import Flow, Step
from .safe_eval import safe_eval
from .logging import log_step, mask_pii
from .config import PROFILES, WAIT_PRESETS, get_profile_chain
from .hooks import apply_screenshot_mask
from . import scheduler
from .flow_signature import verify_flow

# Supported high-level flow operations
FLOW_OPERATIONS = {"view", "run", "edit", "publish", "approve"}

# Mapping of action names to required roles
SENSITIVE_ACTION_ROLES: Dict[str, Set[str]] = {
    "prompt.input": {"user"},
    "prompt.confirm": {"user"},
    "prompt.select": {"user"},
}

# Mapping of action names to required approval levels
SENSITIVE_ACTION_APPROVALS: Dict[str, int] = {
    "prompt.input": 1,
    "prompt.confirm": 1,
    "prompt.select": 1,
}

# Mapping of action names to required permissions
ACTION_PERMISSIONS: Dict[str, str] = {
    # Desktop/UI automation actions
    "launch": "desktop.uia",
    "attach": "desktop.uia",
    "activate": "desktop.uia",
    "double_click": "desktop.uia",
    "hover": "desktop.uia",
    "scroll": "desktop.uia",
    "drag_drop": "desktop.uia",
    "type_text": "desktop.uia",
    "set_value": "desktop.uia",
    "check": "desktop.uia",
    "uncheck": "desktop.uia",
    "find_image": "desktop.uia",
    "wait_image_disappear": "desktop.uia",
    "ocr_read": "desktop.uia",
    "click_xy": "desktop.uia",
    "table.find_row": "desktop.uia",
    "row.select": "desktop.uia",
    "row.double_click": "desktop.uia",
    "ime.on": "desktop.uia",
    "ime.off": "desktop.uia",
    "layout.switch": "desktop.uia",
    # Web automation actions
    "open": "web",
    "click": "web",
    "dblclick": "web",
    "right_click": "web",
    "fill": "web",
    "select": "web",
    "upload": "web",
    "wait_for": "web",
    "download": "web",
    "evaluate": "web",
    "screenshot": "web",
    # Office automation actions
    "excel.open": "office",
    "excel.get": "office",
    "excel.set": "office",
    "excel.save": "office",
    "excel.run_macro": "office",
    "excel.export": "office",
    "excel.find_replace": "office",
    "excel.close": "office",
    "excel.activate": "office",
    "word.open": "office",
    "word.save": "office",
    "word.run_macro": "office",
    "word.bookmark.set": "office",
    "word.replace_all": "office",
    "word.export_pdf": "office",
    "outlook.open": "office",
    "outlook.save": "office",
    "outlook.run_macro": "office",
    "outlook.send": "office",
    "outlook.send_receive": "office",
    "access.open": "office",
    "access.query": "office",
    "access.export_report": "office",
    # HTTP actions
    "http.get": "http",
    "http.post": "http",
    # File system actions
    "file.read": "files",
    "file.write": "files",
    "file.copy": "files",
    "file.move": "files",
    "file.delete": "files",
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
    approval_level: int = 0

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
        self.allowed_permissions: Set[str] = set(self.flow.meta.permissions)
        self.locals_stack: List[Dict[str, Any]] = []
        self.flow_roles: Dict[str, Set[str]] = {
            op: set(r) for op, r in getattr(self.flow.meta, "roles", {}).items()
        }
        roles_input = self.inputs.get("roles")
        if isinstance(roles_input, (list, set, tuple)):
            self.roles = set(roles_input)
        elif isinstance(roles_input, str):
            self.roles = {roles_input}
        level_input = self.inputs.get("approval_level")
        if isinstance(level_input, int):
            self.approval_level = level_input
        elif isinstance(level_input, str) and level_input.isdigit():
            self.approval_level = int(level_input)

    def require_roles(self, required: Set[str]) -> None:
        """Ensure that ``required`` roles are present."""
        if required and not required.issubset(self.roles):
            raise PermissionError(
                f"Action requires roles {sorted(required)}"
            )

    def require_flow_op(self, operation: str) -> None:
        """Ensure that the current roles allow ``operation`` on the flow."""
        required = self.flow_roles.get(operation, set())
        if required and not required.issubset(self.roles):
            raise PermissionError(
                f"Flow operation '{operation}' requires roles {sorted(required)}"
            )

    def require_approval(self, level: int) -> None:
        """Ensure that the approval level is at least ``level``."""
        if level > self.approval_level:
            raise PermissionError(
                f"Action requires approval level {level}"
            )

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
            type_map = {
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "date": (datetime, date),
                "path": (str, Path),
                "secret": str,
                "array": list,
                "object": dict,
            }
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

    def __init__(
        self,
        run_id: Optional[str] = None,
        base_dir: Path | str = Path("runs"),
        signature_key: bytes | None = None,
    ) -> None:
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
        self.signature_key = signature_key

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
        if self.signature_key is not None:
            if not verify_flow(path, self.signature_key):
                raise ValueError("invalid flow signature")
        data = json.loads(Path(path).read_text())
        flow = Flow.from_dict(data)
        return self.run_flow(flow, inputs or {}, path)

    def run_flow(
        self,
        flow: Flow,
        inputs: Optional[Dict[str, Any]] = None,
        path: Path | str | None = None,
    ) -> Dict[str, Any]:
        if self.signature_key is not None:
            if path is None or not verify_flow(path, self.signature_key):
                raise ValueError("invalid flow signature")
        self._acquire_lock()
        try:
            ctx = ExecutionContext(flow, inputs or {})
            ctx.require_flow_op("run")
            self._run_steps(flow.steps, ctx)
            return ctx.flow_vars
        finally:
            self._release_lock()

    def resume_flow(self, flow: Flow, start_step_id: str, checkpoint_path: Path | str) -> Dict[str, Any]:
        state = json.loads(Path(checkpoint_path).read_text())
        ctx = ExecutionContext(flow, {})
        ctx.require_flow_op("run")
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

        host = socket.gethostname()
        try:
            user = getpass.getuser()
        except Exception:
            user = None
        try:
            display = scheduler._get_display_info()
            dpi = display.get("dpi")
            monitors = display.get("monitors")
        except Exception:
            dpi = None
            monitors = []

        if self.skip_requested:
            self.skip_requested = False
            log_step(
                self.run_id,
                self.run_dir,
                step.id,
                step.action,
                0.0,
                "skipped",
                host=host,
                user=user,
                dpi=dpi,
                monitors=monitors,
            )
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
        ctx.require_roles(required)
        required_level = SENSITIVE_ACTION_APPROVALS.get(step.action, 0)
        ctx.require_approval(required_level)
        required_perm = ACTION_PERMISSIONS.get(step.action)
        if required_perm and required_perm not in ctx.allowed_permissions:
            raise PermissionError(
                f"Action '{step.action}' requires permission '{required_perm}'"
            )
        func = self.actions.get(step.action)
        if not func:
            log_step(
                self.run_id,
                self.run_dir,
                step.id,
                step.action,
                0.0,
                "unknown",
                host=host,
                user=user,
                dpi=dpi,
                monitors=monitors,
            )
            return
        ctx.push_local()
        original_selector = step.selector
        last_exc: Optional[Exception] = None
        profiles = get_profile_chain(ctx.flow.defaults.envProfile)
        for profile_index, pname in enumerate(profiles):
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
                order = step.selectorOrder or profile.selectors
                ordered = [s for s in order if s in original_selector]
                if ordered:
                    selectors = [{name: original_selector[name]} for name in ordered]

            selector_retry = step.selectorRetry if step.selectorRetry is not None else retry

            for selector_index, sel in enumerate(selectors):
                step.selector = sel
                for attempt in range(selector_retry + 1):
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
                        fallback_used = (
                            profile_index > 0 or selector_index > 0 or attempt > 0
                        )
                        log_step(
                            self.run_id,
                            self.run_dir,
                            step.id,
                            step.action,
                            duration,
                            "ok",
                            host=host,
                            user=user,
                            dpi=dpi,
                            monitors=monitors,
                            selectorUsed=sel,
                            retries=attempt,
                            fallbackUsed=fallback_used,
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
                        oe = step.onError or {}
                        artifacts = self._capture_artifacts(
                            step,
                            exc,
                            uiatree=bool(oe.get("uiatree")),
                            web_trace=bool(oe.get("webTrace")),
                            har=bool(oe.get("har")),
                            video=bool(oe.get("video")),
                        )
                        fallback_used = (
                            profile_index > 0 or selector_index > 0 or attempt > 0
                        )
                        log_step(
                            self.run_id,
                            self.run_dir,
                            step.id,
                            step.action,
                            duration,
                            "error",
                            host=host,
                            user=user,
                            dpi=dpi,
                            monitors=monitors,
                            selectorUsed=sel,
                            retries=attempt,
                            fallbackUsed=fallback_used,
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
                        if oe.get("screenshot"):
                            self._take_screenshot(step, ctx, exc)
                        if oe.get("recover"):
                            self._recover(oe["recover"], step, ctx)
                        if oe.get("continue"):
                            ctx.pop_local()
                            step.selector = original_selector
                            return
                        if attempt == selector_retry:
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

    def _capture_artifacts(
        self,
        step: Step,
        exc: Exception,
        *,
        uiatree: bool = False,
        web_trace: bool = False,
        har: bool = False,
        video: bool = False,
    ) -> Dict[str, str]:
        """Create artifact files for a failed step.

        When ``video`` is requested, a short low-FPS screen recording is
        captured. The recording attempts to grab a few frames of the screen at
        one frame per second. If screen capture or video encoding fails (e.g. in
        headless environments), a placeholder file is written instead so that
        callers still receive a path.
        """
        ts = int(time.time() * 1000)
        artifacts: Dict[str, str] = {}
        screenshot_path = self.artifacts_dir / f"{step.id}_{ts}.png"
        data = apply_screenshot_mask(b"screenshot")
        screenshot_path.write_bytes(data)
        artifacts["screenshot"] = str(screenshot_path)
        if uiatree:
            ui_tree_path = self.artifacts_dir / f"{step.id}_{ts}_ui.json"
            ui_tree_path.write_text(json.dumps({}))
            artifacts["uiTree"] = str(ui_tree_path)
        if web_trace:
            trace_path = self.artifacts_dir / f"{step.id}_{ts}_trace.json"
            trace_path.write_text(json.dumps([]))
            artifacts["webTrace"] = str(trace_path)
        if har:
            har_path = self.artifacts_dir / f"{step.id}_{ts}.har"
            har_path.write_text(json.dumps({}))
            artifacts["har"] = str(har_path)
        if video:
            video_path = self.artifacts_dir / f"{step.id}_{ts}_video.mp4"
            try:
                import time as _time
                from PIL import Image, ImageGrab  # type: ignore
                import imageio.v2 as imageio  # type: ignore
                import numpy as np  # type: ignore

                frames = []
                for _ in range(3):
                    try:
                        img = ImageGrab.grab()
                    except Exception:
                        img = Image.new("RGB", (320, 240), color="black")
                    frames.append(np.array(img))
                    _time.sleep(1)  # 1 FPS
                imageio.mimsave(video_path, frames, fps=1)
            except Exception:
                # Fallback to placeholder file if recording fails
                video_path.write_text("video")
            artifacts["video"] = str(video_path)
        return artifacts

    def _recover(self, recover_spec: Any, step: Step, ctx: ExecutionContext) -> None:
        """Execute recovery steps specified in ``onError.recover``.

        ``recover_spec`` may be either a step definition, a list of step
        definitions or simple string identifiers for common recovery actions.
        When a string identifier is provided it is mapped to a concrete step
        using the selector of the failing ``step``.
        """

        # Map of shorthand recovery names to concrete step definitions.  The
        # failing step's selector is reused so that the recovery action targets
        # the same element/window.
        def _reactivate(s: Step) -> Dict[str, Any]:
            return {
                "id": f"{s.id}#reactivate",
                "action": "activate",
                "selector": s.selector,
            }

        def _scroll(s: Step) -> Dict[str, Any]:
            return {
                "id": f"{s.id}#scroll",
                "action": "scroll",
                "selector": s.selector,
                "params": {"clicks": -1},
            }

        shorthand: Dict[str, Callable[[Step], Dict[str, Any]]] = {
            "re-activate": _reactivate,
            "scroll": _scroll,
        }

        steps_data: List[Any]
        if isinstance(recover_spec, list):
            steps_data = recover_spec
        else:
            steps_data = [recover_spec]

        expanded: List[Dict[str, Any]] = []
        for spec in steps_data:
            if isinstance(spec, str):
                mapper = shorthand.get(spec)
                if mapper is None:
                    raise ValueError(f"Unknown recover action '{spec}'")
                expanded.append(mapper(step))
            else:
                expanded.append(spec)

        steps = Flow._load_steps(expanded)
        self._run_steps(steps, ctx)
