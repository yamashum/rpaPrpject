"""Data models for workflow definition.

The classes in this module mirror the JSON structure used to describe a
workflow.  Variables are declared with :class:`VarDef` which supports a
small set of primitive types as well as a few convenience types.

Example
-------
>>> from datetime import date
>>> from pathlib import Path
>>> flow = Flow(
...     version="1",
...     meta=Meta(name="demo"),
...     variables={
...         "today": VarDef(type="date", value=date.today()),
...         "out": VarDef(type="path", value=Path("/tmp")),
...     },
... )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Meta:
    """Metadata for a flow."""

    name: str
    desc: str = ""
    permissions: List[str] = field(default_factory=list)


@dataclass
class Defaults:
    """Default settings for all steps.

    ``timeoutMs`` and ``retry`` are optional and, when not provided, fall back
    to the values defined by the active execution profile (see
    :mod:`workflow.config`).
    """

    timeoutMs: Optional[int] = None
    retry: Optional[int] = None
    envProfile: str = "physical"


@dataclass
class VarDef:
    """Definition of a flow variable including its type and default value.

    Parameters
    ----------
    type:
        Name of the variable type. Supported values are ``int``, ``float``,
        ``str``, ``bool``, ``date``, ``path``, ``secret``, ``array``, ``object``
        and ``any``. ``date`` accepts :class:`datetime.date` or
        :class:`datetime.datetime` objects; ``path`` accepts strings or
        :class:`pathlib.Path`; ``array`` maps to :class:`list`; ``object`` maps
        to :class:`dict`; ``secret`` behaves like ``str`` but marks the value as
        sensitive.
    value:
        Default value for the variable.
    """

    type: str = "any"
    value: Any = None


@dataclass
class Step:
    """Definition of a single step in the flow.

    The model covers both action steps and control-structure steps.
    """

    id: str
    action: Optional[str] = None
    selector: Optional[Dict[str, Any]] = None
    target: Optional[Dict[str, Any]] = None
    params: Dict[str, Any] = field(default_factory=dict)
    waitFor: Optional[str] = None
    timeoutMs: Optional[int] = None
    retry: Optional[int] = None
    onError: Dict[str, Any] = field(default_factory=dict)
    out: Optional[str] = None

    # ----- control structure fields -----
    condition: Optional[str] = None
    while_condition: Optional[str] = None
    for_each: Optional[str] = None
    subflow: Optional[str] = None
    switch_expr: Optional[str] = None
    steps: List["Step"] = field(default_factory=list)
    else_steps: List["Step"] = field(default_factory=list)
    catch_steps: List["Step"] = field(default_factory=list)
    finally_steps: List["Step"] = field(default_factory=list)
    cases: List[Dict[str, Any]] = field(default_factory=list)
    default_steps: List["Step"] = field(default_factory=list)

    break_flag: bool = False
    continue_flag: bool = False


@dataclass
class Flow:
    """Top level workflow model."""

    version: str
    meta: Meta
    inputs: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, VarDef] = field(default_factory=dict)
    permissions: Dict[str, List[str]] = field(default_factory=dict)
    defaults: Defaults = field(default_factory=Defaults)
    steps: List[Step] = field(default_factory=list)

    @staticmethod
    def _load_steps(data: List[Dict[str, Any]]) -> List[Step]:
        steps: List[Step] = []
        for sd in data or []:
            step = Step(
                id=sd.get("id", ""),
                action=sd.get("action"),
                selector=sd.get("selector"),
                target=sd.get("target"),
                params=sd.get("params", {}),
                waitFor=sd.get("waitFor"),
                timeoutMs=sd.get("timeoutMs"),
                retry=sd.get("retry"),
                onError=sd.get("onError", {}),
                out=sd.get("out"),
                condition=sd.get("condition"),
                while_condition=sd.get("while"),
                for_each=sd.get("for_each"),
                subflow=sd.get("subflow"),
                switch_expr=sd.get("switch"),
                break_flag=sd.get("break", False),
                continue_flag=sd.get("continue", False),
            )
            step.steps = Flow._load_steps(sd.get("steps", []))
            step.else_steps = Flow._load_steps(sd.get("else", []))
            step.catch_steps = Flow._load_steps(sd.get("catch", []))
            step.finally_steps = Flow._load_steps(sd.get("finally", []))
            step.cases = []
            for cd in sd.get("cases", []):
                case_steps = Flow._load_steps(cd.get("steps", []))
                step.cases.append({"value": cd.get("value"), "steps": case_steps})
            step.default_steps = Flow._load_steps(sd.get("default", []))
            steps.append(step)
        return steps

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Flow":
        meta = Meta(**data.get("meta", {}))
        defaults = Defaults(**data.get("defaults", {}))
        steps = cls._load_steps(data.get("steps", []))
        vars_spec: Dict[str, VarDef] = {}
        for name, spec in (data.get("variables") or {}).items():
            if isinstance(spec, dict):
                vars_spec[name] = VarDef(type=spec.get("type", "any"), value=spec.get("value"))
            else:
                vars_spec[name] = VarDef(value=spec)
        return cls(
            version=data.get("version", "1.0"),
            meta=meta,
            inputs=data.get("inputs", {}),
            variables=vars_spec,
            permissions=data.get("permissions", {}),
            defaults=defaults,
            steps=steps,
        )
