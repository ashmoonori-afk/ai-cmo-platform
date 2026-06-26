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

_OPERATING_INPUTS = {"artifact_format", "feedback"}


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
        self.store.ensure_run(spec=spec, run_id=run_id, inputs=inputs)
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
        for step in spec.execution_order():
            status = self.store.get_step_status(run_id, step.id)
            if status == StepStatus.SUCCESS:
                if self._successful_outputs_present(run_id, step, context):
                    continue
                self.store.reopen_step(run_id, step.id)
                status = StepStatus.PENDING
            if not self._dependencies_done(run_id, step):
                return self._fail(
                    run_id,
                    step.id,
                    "dependency did not complete",
                    owner=None,
                )
            try:
                outputs = self._execute_step(run_id, step, context, status)
            except WorkflowExecutionError as exc:
                return self._fail(
                    run_id,
                    step.id,
                    str(exc),
                    owner=self._owner_for_status(status),
                )
            except Exception as exc:  # noqa: BLE001 — record any step failure, never strand the run
                message = f"unexpected error: {type(exc).__name__}: {exc}"
                return self._fail(
                    run_id,
                    step.id,
                    message,
                    owner=self._owner_for_status(status),
                )
            waiting_without_approval = (
                self.store.get_step_status(run_id, step.id) == StepStatus.WAITING_APPROVAL
                and self.store.approval_for(run_id, step.id) is None
            )
            after_step = self._after_step(run_id, step, status, outputs, waiting_without_approval)
            if after_step is not None:
                return after_step
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
        undeclared = sorted(
            key for key in inputs if key not in spec.inputs and key not in _OPERATING_INPUTS
        )
        if undeclared:
            step_id = "inputs"
            raise WorkflowExecutionError(step_id, f"undeclared inputs: {', '.join(undeclared)}")
        client = inputs.get("client")
        if "client" in spec.inputs and client:
            slug = parse_safe_id("client", client).value
            required = (
                self.repo_root / "clients" / slug / "config.md",
                self.repo_root / "clients" / slug / "brand-guidelines.md",
            )
            missing_files = [
                path.relative_to(self.repo_root) for path in required if not path.exists()
            ]
            if missing_files:
                joined = ", ".join(str(path).replace("\\", "/") for path in missing_files)
                step_id = "inputs"
                msg = (
                    "client onboarding required: run "
                    f"'uv run aicmo onboard --client {slug} --from answers.json' "
                    f"or upload/create {joined}"
                )
                raise WorkflowExecutionError(step_id, msg)

    def _owner_for_status(self: Self, status: StepStatus) -> str | None:
        if status == StepStatus.WAITING_APPROVAL:
            return None
        return self.runner_token

    def _fail(self: Self, run_id: str, step_id: str, message: str, owner: str | None) -> RunResult:
        if not self.store.mark_step_failed(run_id, step_id, message, owner=owner):
            return self._lost_lease(run_id, step_id, message)
        self.store.record_event(run_id, step_id, "step.failed", message)
        return RunResult(status="failed", run_id=run_id, failed_step_id=step_id)

    def _lost_lease(self: Self, run_id: str, step_id: str, message: str) -> RunResult:
        self.store.record_event(run_id, step_id, "step.lost_lease", message)
        return RunResult(status="failed", run_id=run_id, failed_step_id=step_id)

    def _after_step(
        self: Self,
        run_id: str,
        step: WorkflowStep,
        status: StepStatus,
        outputs: list[str],
        waiting_without_approval: bool,
    ) -> RunResult | None:
        if waiting_without_approval:
            if not self._phase_completed(run_id, step, outputs):
                return self._fail(run_id, step.id, "phase automation failed", owner=None)
            return RunResult(status=StepStatus.WAITING_APPROVAL.value, run_id=run_id)
        if not self.store.mark_step_success(
            run_id,
            step.id,
            outputs,
            owner=self._owner_for_status(status),
        ):
            return self._lost_lease(run_id, step.id, "step lease lost before success")
        self.store.record_output_hashes(run_id, step.id, self._hash_outputs(outputs))
        self.store.record_event(run_id, step.id, "step.success", f"Completed {step.id}")
        if not self._phase_completed(run_id, step, outputs):
            return self._fail(run_id, step.id, "phase automation failed", owner=None)
        return None

    def _phase_completed(self: Self, run_id: str, step: WorkflowStep, outputs: list[str]) -> bool:
        if self.phase_completed is None:
            return True
        try:
            self.phase_completed(step, tuple(outputs))
        except Exception as exc:  # noqa: BLE001
            message = f"phase automation failed: {type(exc).__name__}: {exc}"
            self.store.record_event(run_id, step.id, "phase.automation_failed", message)
            return False
        return True
