"""Data models for workflow definition."""

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
    """Default settings for all steps."""

    timeoutMs: int = 3000
    retry: int = 0
    envProfile: str = "default"


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
    variables: Dict[str, Any] = field(default_factory=dict)
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
        return cls(
            version=data.get("version", "1.0"),
            meta=meta,
            inputs=data.get("inputs", {}),
            variables=data.get("variables", {}),
            defaults=defaults,
            steps=steps,
        )
