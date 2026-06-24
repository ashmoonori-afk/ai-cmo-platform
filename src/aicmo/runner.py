from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from aicmo.errors import WorkflowExecutionError
from aicmo.models import (
    ApprovalDecision,
    RunResult,
    StepStatus,
    WorkflowSpec,
    WorkflowStep,
)
from aicmo.paths import parse_safe_id
from aicmo.spec import load_workflow_spec
from aicmo.step_executor import WorkflowStepExecutor


@dataclass(frozen=True, slots=True)
class WorkflowRunner(WorkflowStepExecutor):
    def run(self: Self, workflow_id: str, run_id: str, inputs: dict[str, str]) -> RunResult:
        parse_safe_id("workflow_id", workflow_id)
        parse_safe_id("run_id", run_id)
        spec = load_workflow_spec(self.repo_root, workflow_id)
        self._validate_inputs(spec, inputs)
        self.store.initialize()
        self.store.ensure_run(spec=spec, run_id=run_id, inputs=inputs)
        self.store.record_event(run_id, None, "run.started", f"Started {workflow_id}", inputs)
        return self._execute(spec, run_id, inputs)

    def resume(self: Self, run_id: str) -> RunResult:
        self.store.initialize()
        run = self.store.get_run(run_id)
        spec = load_workflow_spec(self.repo_root, str(run["workflow_id"]))
        inputs = self.store.get_inputs(run_id)
        self.store.record_event(run_id, None, "run.resumed", f"Resumed {run_id}")
        return self._execute(spec, run_id, inputs)

    def approve(self: Self, run_id: str, step_id: str, reviewer: str, notes: str) -> None:
        self.store.initialize()
        self.store.approve(run_id, step_id, ApprovalDecision.APPROVED, reviewer, notes)
        self.store.record_event(run_id, step_id, "gate.approved", notes, {"reviewer": reviewer})

    def reject(self: Self, run_id: str, step_id: str, reviewer: str, notes: str) -> None:
        self.store.initialize()
        self.store.approve(run_id, step_id, ApprovalDecision.REJECTED, reviewer, notes)
        self.store.mark_step_failed(run_id, step_id, "manual gate rejected")
        self.store.record_event(run_id, step_id, "gate.rejected", notes, {"reviewer": reviewer})

    def retry(self: Self, run_id: str, step_id: str) -> None:
        self.store.initialize()
        self.store.retry_step(run_id, step_id)
        self.store.record_event(run_id, step_id, "step.retry", f"Retry requested for {step_id}")

    def _execute(self: Self, spec: WorkflowSpec, run_id: str, inputs: dict[str, str]) -> RunResult:
        context = {**inputs, "run_id": run_id, "workflow_id": spec.id}
        for step in spec.steps:
            status = self.store.get_step_status(run_id, step.id)
            if status == StepStatus.SUCCESS:
                if self._successful_outputs_present(run_id, step, context):
                    continue
                self.store.retry_step(run_id, step.id)
                status = StepStatus.PENDING
            if not self._dependencies_done(run_id, step):
                return self._fail(run_id, step.id, "dependency did not complete")
            try:
                outputs = self._execute_step(run_id, step, context, status)
            except WorkflowExecutionError as exc:
                return self._fail(run_id, step.id, str(exc))
            waiting_without_approval = (
                self.store.get_step_status(run_id, step.id) == StepStatus.WAITING_APPROVAL
                and self.store.approval_for(run_id, step.id) is None
            )
            if waiting_without_approval:
                return RunResult(status=StepStatus.WAITING_APPROVAL.value, run_id=run_id)
            self.store.mark_step_success(run_id, step.id, outputs)
            self.store.record_event(run_id, step.id, "step.success", f"Completed {step.id}")
        self.store.mark_run_success(run_id)
        self.store.record_event(run_id, None, "run.success", f"Completed {run_id}")
        return RunResult(status="success", run_id=run_id)

    def _dependencies_done(self: Self, run_id: str, step: WorkflowStep) -> bool:
        return all(
            self.store.get_step_status(run_id, dependency) == StepStatus.SUCCESS
            for dependency in step.depends_on
        )

    def _validate_inputs(self: Self, spec: WorkflowSpec, inputs: dict[str, str]) -> None:
        missing = [
            key
            for key, requirement in spec.inputs.items()
            if requirement == "required" and not inputs.get(key)
        ]
        if missing:
            step_id = "inputs"
            raise WorkflowExecutionError(step_id, f"missing required inputs: {', '.join(missing)}")

    def _fail(self: Self, run_id: str, step_id: str, message: str) -> RunResult:
        self.store.mark_step_failed(run_id, step_id, message)
        self.store.record_event(run_id, step_id, "step.failed", message)
        return RunResult(status="failed", run_id=run_id, failed_step_id=step_id)
