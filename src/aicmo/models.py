from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aicmo.paths import SAFE_ID_PATTERN


class StepType(StrEnum):
    FILE_LOAD = "file.load"
    AGENT = "agent"
    GATE = "gate"
    KB_UPDATE = "kb.update"
    METRICS_REPORT = "metrics.report"
    FEEDBACK_REPORT = "feedback.report"
    LEARNING_CONTEXT = "learning.context"
    PHOTOS_PREPARE = "photos.prepare"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_APPROVAL = "waiting_approval"
    CANCELLED = "cancelled"


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
    terminal_delivery: bool = False
    model: str | None = None

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

    @model_validator(mode="after")
    def validate_terminal_delivery(self) -> WorkflowStep:
        if not self.terminal_delivery:
            return self
        match self.type:
            case StepType.GATE:
                if self.requires_approval:
                    msg = "terminal delivery step must be an automatic gate"
                    raise ValueError(msg)
            case (
                StepType.FILE_LOAD
                | StepType.AGENT
                | StepType.KB_UPDATE
                | StepType.METRICS_REPORT
                | StepType.FEEDBACK_REPORT
                | StepType.LEARNING_CONTEXT
                | StepType.PHOTOS_PREPARE
            ):
                msg = "terminal delivery step must be an automatic gate"
                raise ValueError(msg)
            case unreachable:
                assert_never(unreachable)
        if not self.depends_on:
            msg = "terminal delivery gate requires artifact producers"
            raise ValueError(msg)
        return self


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
        for input_name, requirement in self.inputs.items():
            if requirement not in ("required", "optional"):
                msg = f"invalid requirement for input {input_name}: {requirement}"
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
            for template in (*step.paths, *step.outputs):
                if not template.strip():
                    msg = f"empty path or output template in {step.id}"
                    raise ValueError(msg)
            outputs.extend(step.outputs)
        if len(outputs) != len(set(outputs)):
            msg = "duplicate output path"
            raise ValueError(msg)
        self._validate_acyclic()
        return self

    @model_validator(mode="after")
    def validate_terminal_topology(self) -> WorkflowSpec:
        terminal_steps = tuple(step for step in self.steps if step.terminal_delivery)
        if len(terminal_steps) > 1:
            msg = "workflow may define only one terminal delivery gate"
            raise ValueError(msg)
        terminal_ids = {step.id for step in terminal_steps}
        for step in self.steps:
            if any(dependency in terminal_ids for dependency in step.depends_on):
                msg = "terminal delivery gate must be a leaf"
                raise ValueError(msg)
        if terminal_steps and self.execution_order()[-1] != terminal_steps[0]:
            msg = "terminal delivery gate must be the final step"
            raise ValueError(msg)
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

    def execution_order(self) -> tuple[WorkflowStep, ...]:
        """Return steps in a stable topological order (dependencies first).

        Declaration order is preserved among steps that are ready at the same time, so a
        spec that is already authored in dependency order keeps its original sequence.
        The spec is validated acyclic before this runs, so every step is emitted exactly once.
        """
        position = {step.id: index for index, step in enumerate(self.steps)}
        step_by_id = {step.id: step for step in self.steps}
        indegree = {step.id: len(step.depends_on) for step in self.steps}
        dependents: dict[str, list[str]] = {step.id: [] for step in self.steps}
        for step in self.steps:
            for dependency in step.depends_on:
                dependents[dependency].append(step.id)
        ready = sorted(
            (step_id for step_id, degree in indegree.items() if degree == 0),
            key=position.__getitem__,
        )
        ordered: list[WorkflowStep] = []
        while ready:
            current = ready.pop(0)
            ordered.append(step_by_id[current])
            newly_ready: list[str] = []
            for dependent in dependents[current]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    newly_ready.append(dependent)
            if newly_ready:
                ready = sorted([*ready, *newly_ready], key=position.__getitem__)
        return tuple(ordered)
