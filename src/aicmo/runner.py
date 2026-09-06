from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Self

from aicmo.adapters import CommandAdapter, StepAdapter
from aicmo.anthropic_adapter import AnthropicAdapter, resolve_model
from aicmo.errors import (
    RunConflictError,
    StepTransitionError,
    WorkflowExecutionError,
    WorkflowSpecError,
)
from aicmo.local_pack import WORKFLOW_ID as LOCAL_PACK_WORKFLOW
from aicmo.local_pack import parse_brief
from aicmo.models import (
    ApprovalDecision,
    RunResult,
    RunStatus,
    StepStatus,
    WorkflowSpec,
    WorkflowStep,
)
from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.redaction import contains_raw_secret, minimize_customer_pii
from aicmo.source_input import PreparedInputs, operating_inputs, prepare_workflow_inputs
from aicmo.spec import load_workflow_spec
from aicmo.step_executor import WorkflowStepExecutor
from aicmo.step_state import MAX_STEP_ATTEMPTS

_OPERATING_INPUTS = {"artifact_format", "feedback", *operating_inputs()}


@dataclass(frozen=True, slots=True)
class WorkflowRunner(WorkflowStepExecutor):
    def run(self: Self, workflow_id: str, run_id: str, inputs: dict[str, str]) -> RunResult:
        parse_safe_id("workflow_id", workflow_id)
        parse_safe_id("run_id", run_id)
        spec = load_workflow_spec(self.repo_root, workflow_id)
        if spec.id == LOCAL_PACK_WORKFLOW:
            parse_brief(inputs)
        prepared = prepare_workflow_inputs(spec.inputs, inputs)
        inputs = prepared.values
        if spec.id == LOCAL_PACK_WORKFLOW:
            parse_brief(inputs)
        self._validate_inputs(spec, inputs)
        self.store.initialize()
        self.store.ensure_run(spec=spec, run_id=run_id, inputs=inputs)
        self.store.ensure_execution_policy(run_id, self._execution_policy(spec))
        self._write_source_manifest(run_id, prepared)
        self.store.record_event(run_id, None, "run.started", f"Started {workflow_id}", inputs)
        return self._execute(spec, run_id, inputs)

    def resume(self: Self, run_id: str, *, allow_policy_change: bool = False) -> RunResult:
        self.store.initialize()
        run = self.store.get_run(run_id)
        inputs = self.store.get_inputs(run_id)
        try:
            spec = load_workflow_spec(self.repo_root, str(run["workflow_id"]))
            self.store.ensure_run(spec=spec, run_id=run_id, inputs=inputs)
            prepared = prepare_workflow_inputs(spec.inputs, inputs)
            if spec.id == LOCAL_PACK_WORKFLOW:
                parse_brief(prepared.values)
            if prepared.values != inputs:
                raise RunConflictError(
                    run_id,
                    "stored inputs do not meet current privacy rules; start a new run",
                )
            self._write_source_manifest(run_id, prepared)
            changed = self.store.ensure_execution_policy(
                run_id,
                self._execution_policy(spec),
                allow_change=allow_policy_change,
            )
        except WorkflowSpecError as exc:
            reason = f"current specification cannot be verified ({exc}); start a new run"
            raise RunConflictError(run_id, reason) from None
        if changed:
            self.store.record_event(
                run_id,
                None,
                "run.policy_changed",
                "Executor, reviewer, or model policy changed by explicit request",
            )
        self.store.record_event(run_id, None, "run.resumed", f"Resumed {run_id}")
        return self._execute(spec, run_id, inputs)

    def verified_export_outputs(
        self: Self,
        spec: WorkflowSpec,
        run_id: str,
        inputs: dict[str, str],
    ) -> dict[str, bytes]:
        """Capture only current successful outputs whose dependency/version hashes match."""
        context = {**inputs, "run_id": run_id, "workflow_id": spec.id}
        step_id = "export"
        contents: dict[str, bytes] = {}
        for step in spec.execution_order():
            outputs = self.store.get_step_outputs(run_id, step.id)
            hashes = self.store.get_output_hashes(run_id, step.id)
            if (
                self.store.get_step_status(run_id, step.id) != StepStatus.SUCCESS
                or set(outputs) != set(self._declared_outputs(step, context))
                or set(outputs) != set(hashes)
                or (
                    step.depends_on
                    and self.store.get_consumed_ref_digest(run_id, step.id)
                    != self._consumed_ref_digest(self._artifact_refs(run_id, step))
                )
            ):
                raise WorkflowExecutionError(
                    step_id, "stale or incomplete approval/review; resume first"
                )
            for relative in outputs:
                path = resolve_inside_repo(self.repo_root, relative, {})
                try:
                    data = path.read_bytes()
                except OSError:
                    raise WorkflowExecutionError(step_id, "required artifact is missing") from None
                if hashlib.sha256(data).hexdigest() != hashes[relative]:
                    raise WorkflowExecutionError(
                        step_id, "artifact changed after review; resume first"
                    )
                contents[relative] = data
        return contents

    def cancel(self: Self, run_id: str) -> None:
        self.store.initialize()
        self.store.cancel_run(run_id)
        self.store.record_event(run_id, None, "run.cancelled", f"Cancelled {run_id}")

    def _execution_policy(self: Self, spec: WorkflowSpec) -> str:
        return json.dumps(
            {
                "schema_version": "aicmo.run-policy.v1",
                "executor": self._adapter_identity(self.adapter),
                "reviewer": (
                    self._adapter_identity(self.review_adapter)
                    if self.review_adapter is not None
                    else None
                ),
                "models": {step.id: step.model or "" for step in spec.steps},
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _adapter_identity(adapter: StepAdapter) -> dict[str, str]:
        identity = f"{type(adapter).__module__}.{type(adapter).__qualname__}"
        if isinstance(adapter, CommandAdapter):
            command = json.dumps(adapter.command, separators=(",", ":"))
            return {
                "type": identity,
                "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                "timeout_seconds": f"{adapter.timeout_seconds:g}",
            }
        if isinstance(adapter, AnthropicAdapter):
            return {
                "type": identity,
                "default_model": resolve_model("", adapter.default_model),
                "max_tokens": str(adapter.max_tokens),
            }
        return {"type": identity}

    def _write_source_manifest(self: Self, run_id: str, prepared: PreparedInputs) -> None:
        if prepared.source_manifest is None:
            return
        target = self.repo_root / "artifacts" / run_id / "source-manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(prepared.source_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)

    def approve(
        self: Self,
        run_id: str,
        step_id: str,
        reviewer: str,
        notes: str,
        accept_edits: bool = False,
    ) -> list[str]:
        """Record a manual approval. With accept_edits, bless human edits made to
        successful steps' artifacts while the gate was waiting: their hashes are
        recomputed so resume keeps the edited files instead of regenerating them.
        Blessing happens BEFORE the approval row lands — the approval row is what
        lets a concurrent resume proceed past the gate, so the reverse order would
        open a window where that resume regenerates over the owner's edits.
        Returns the list of artifact paths whose content changed since generation."""
        self.store.initialize()
        changed: list[str] = []
        if accept_edits:
            if self.store.get_step_status(run_id, step_id) != StepStatus.WAITING_APPROVAL:
                raise StepTransitionError(
                    run_id,
                    step_id,
                    "--accept-edits requires a gate in waiting_approval",
                )
            changed = self._accept_artifact_edits(run_id, step_id)
        safe_notes = minimize_customer_pii(notes)
        self.store.approve(run_id, step_id, ApprovalDecision.APPROVED, reviewer, safe_notes)
        self.store.record_event(
            run_id,
            step_id,
            "gate.approved",
            safe_notes,
            {"reviewer": reviewer},
        )
        if accept_edits:
            self.store.record_event(
                run_id,
                step_id,
                "gate.edits_accepted",
                ", ".join(changed) if changed else "no artifact changes",
                {"files": changed},
            )
        return changed

    def _accept_artifact_edits(self: Self, run_id: str, gate_step_id: str) -> list[str]:
        changed: list[str] = []
        for row in self.store.list_steps(run_id):
            if row["status"] != StepStatus.SUCCESS.value:
                continue
            step_id = str(row["step_id"])
            outputs = self.store.get_step_outputs(run_id, step_id)
            if not outputs:
                continue
            previous = self.store.get_output_hashes(run_id, step_id)
            current = self._hash_outputs(outputs)
            changed.extend(path for path, digest in current.items() if previous.get(path) != digest)
            missing = [path for path in outputs if path not in current]
            if missing:
                # A deleted output cannot be blessed; resume will reopen the whole
                # step and regenerate ALL of its outputs, including blessed siblings.
                self.store.record_event(
                    run_id,
                    gate_step_id,
                    "gate.edits_missing_artifacts",
                    f"{step_id}: missing outputs will trigger regeneration on resume",
                    {"step": step_id, "missing": missing},
                )
            self.store.record_output_hashes(run_id, step_id, current)
        return changed

    def reject(self: Self, run_id: str, step_id: str, reviewer: str, notes: str) -> None:
        self.store.initialize()
        safe_notes = minimize_customer_pii(notes)
        self.store.approve(run_id, step_id, ApprovalDecision.REJECTED, reviewer, safe_notes)
        self.store.mark_step_failed(run_id, step_id, "manual gate rejected")
        self.store.record_event(
            run_id,
            step_id,
            "gate.rejected",
            safe_notes,
            {"reviewer": reviewer},
        )

    def retry(self: Self, run_id: str, step_id: str) -> None:
        self.store.initialize()
        self.store.retry_step(run_id, step_id)
        self.store.record_event(run_id, step_id, "step.retry", f"Retry requested for {step_id}")

    def _execute(self: Self, spec: WorkflowSpec, run_id: str, inputs: dict[str, str]) -> RunResult:
        context = {**inputs, "run_id": run_id, "workflow_id": spec.id}
        self._reopen_stale_successes(spec, run_id, context)
        for step in spec.execution_order():
            status = self.store.get_step_status(run_id, step.id)
            if status == StepStatus.SUCCESS:
                hash_index_complete = set(self.store.get_step_outputs(run_id, step.id)) == set(
                    self.store.get_output_hashes(run_id, step.id),
                )
                if hash_index_complete and self._successful_outputs_present(run_id, step, context):
                    continue
                self._reopen_successes_and_dependents(spec, run_id, {step.id})
                status = StepStatus.PENDING
            halted = self._before_step(run_id, step, status)
            if halted is not None:
                return halted
            try:
                artifact_refs = self._artifact_refs(run_id, step)
                outputs = self._execute_step(run_id, step, context, status, artifact_refs)
            except WorkflowExecutionError as exc:
                return self._fail(
                    run_id,
                    step.id,
                    str(exc),
                    owner=self._owner_for_status(status),
                )
            except Exception as exc:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
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
            after_step = self._after_step(
                run_id,
                step,
                status,
                outputs,
                waiting_without_approval,
                self._consumed_ref_digest(artifact_refs),
            )
            if after_step is not None:
                return after_step
        return self._complete_run(run_id)

    def _before_step(
        self: Self,
        run_id: str,
        step: WorkflowStep,
        status: StepStatus,
    ) -> RunResult | None:
        if self.store.is_run_cancelled(run_id):
            return RunResult(status=RunStatus.CANCELLED.value, run_id=run_id)
        if (
            status != StepStatus.WAITING_APPROVAL
            and self.store.get_step_attempt(run_id, step.id) >= MAX_STEP_ATTEMPTS
        ):
            self.store.record_event(
                run_id,
                step.id,
                "step.retry_exhausted",
                f"Step attempt limit reached ({MAX_STEP_ATTEMPTS})",
            )
            return RunResult(
                status=RunStatus.FAILED.value,
                run_id=run_id,
                failed_step_id=step.id,
            )
        if not self._dependencies_done(run_id, step):
            return self._fail(run_id, step.id, "dependency did not complete", owner=None)
        return None

    def _complete_run(self: Self, run_id: str) -> RunResult:
        if not self.store.mark_run_success(run_id):
            return RunResult(status=RunStatus.CANCELLED.value, run_id=run_id)
        self.store.record_event(run_id, None, "run.success", f"Completed {run_id}")
        return RunResult(status=RunStatus.SUCCESS.value, run_id=run_id)

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
        for key, value in inputs.items():
            if contains_raw_secret(value):
                step_id = "inputs"
                msg = f"input {key!r} contains a raw credential; pass env:NAME references instead"
                raise WorkflowExecutionError(step_id, msg)
        client = inputs.get("client")
        if "client" in spec.inputs and client:
            slug = parse_safe_id("client", client)
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
        if self.store.is_run_cancelled(run_id):
            return RunResult(status=RunStatus.CANCELLED.value, run_id=run_id)
        self.store.record_event(run_id, step_id, "step.lost_lease", message)
        return RunResult(status="failed", run_id=run_id, failed_step_id=step_id)

    def _after_step(
        self: Self,
        run_id: str,
        step: WorkflowStep,
        status: StepStatus,
        outputs: list[str],
        waiting_without_approval: bool,
        consumed_ref_digest: str,
    ) -> RunResult | None:
        if waiting_without_approval:
            if not self._phase_completed(run_id, step, outputs):
                return self._fail(run_id, step.id, "phase automation failed", owner=None)
            return RunResult(status=StepStatus.WAITING_APPROVAL.value, run_id=run_id)
        if not self.store.complete_step_success(
            run_id,
            step.id,
            outputs,
            self._hash_outputs(outputs),
            consumed_ref_digest,
            owner=self._owner_for_status(status),
        ):
            return self._lost_lease(run_id, step.id, "step lease lost before success")
        if not self._phase_completed(run_id, step, outputs):
            return self._fail(run_id, step.id, "phase automation failed", owner=None)
        return None

    def _phase_completed(self: Self, run_id: str, step: WorkflowStep, outputs: list[str]) -> bool:
        if self.phase_completed is None:
            return True
        try:
            self.phase_completed(step, tuple(outputs))
        except Exception as exc:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
            message = f"phase automation failed: {type(exc).__name__}: {exc}"
            self.store.record_event(run_id, step.id, "phase.automation_failed", message)
            return False
        return True
