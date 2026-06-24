from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aicmo.paths import SAFE_ID_PATTERN


class StepType(StrEnum):
    FILE_LOAD = "file.load"
    AGENT = "agent"
    GATE = "gate"
    KB_UPDATE = "kb.update"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"


class GateDecision(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    ESCALATE = "ESCALATE"
    WAITING_APPROVAL = "WAITING_APPROVAL"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RunResult:
    status: str
    run_id: str
    failed_step_id: str | None = None


class WorkflowStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    type: StepType
    paths: tuple[str, ...] = Field(default_factory=tuple)
    outputs: tuple[str, ...] = Field(default_factory=tuple)
    depends_on: tuple[str, ...] = Field(default_factory=tuple)
    role: str | None = None
    prompt: str | None = None
    pass_if: str | None = None
    requires_approval: bool = False

    @field_validator("id")
    @classmethod
    def valid_step_id(cls, value: str) -> str:
        if SAFE_ID_PATTERN.fullmatch(value) is None:
            msg = f"unsafe step id: {value}"
            raise ValueError(msg)
        return value

    @field_validator("paths", "outputs", "depends_on", mode="before")
    @classmethod
    def tuple_from_sequence(
        cls,
        value: str | list[str] | tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        return tuple(value)


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    inputs: dict[str, str] = Field(default_factory=dict)
    steps: tuple[WorkflowStep, ...]
    source_path: Path | None = None

    @field_validator("id")
    @classmethod
    def valid_workflow_id(cls, value: str) -> str:
        if SAFE_ID_PATTERN.fullmatch(value) is None:
            msg = f"unsafe workflow id: {value}"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_graph(self) -> WorkflowSpec:
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            msg = "duplicate step id"
            raise ValueError(msg)
        known_steps = set(step_ids)
        outputs: list[str] = []
        for step in self.steps:
            if len(step.depends_on) != len(set(step.depends_on)):
                msg = f"duplicate dependency for {step.id}"
                raise ValueError(msg)
            missing = [
                dependency for dependency in step.depends_on if dependency not in known_steps
            ]
            if missing:
                msg = f"unknown dependency for {step.id}: {', '.join(missing)}"
                raise ValueError(msg)
            outputs.extend(step.outputs)
        if len(outputs) != len(set(outputs)):
            msg = "duplicate output path"
            raise ValueError(msg)
        self._validate_acyclic()
        return self

    def _validate_acyclic(self) -> None:
        graph = {step.id: set(step.depends_on) for step in self.steps}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                msg = f"cycle detected at {step_id}"
                raise ValueError(msg)
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in graph:
            visit(step_id)
