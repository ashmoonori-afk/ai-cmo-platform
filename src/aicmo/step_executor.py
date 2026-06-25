from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import assert_never

from aicmo.adapters import AgentRequest, LocalAdapter, StepAdapter
from aicmo.errors import WorkflowExecutionError
from aicmo.gate import allowed_statuses, evaluate_artifacts
from aicmo.models import (
    ApprovalDecision,
    GateDecision,
    StepStatus,
    StepType,
    WorkflowStep,
)
from aicmo.paths import resolve_inside_repo
from aicmo.store import WorkflowStore


@dataclass(frozen=True, slots=True)
class WorkflowStepExecutor:
    repo_root: Path
    store: WorkflowStore
    adapter: StepAdapter = field(default_factory=LocalAdapter)

    @property
    def _repo_root(self) -> Path:
        return self.repo_root

    @property
    def _store(self) -> WorkflowStore:
        return self.store

    def _execute_step(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
        status: StepStatus,
    ) -> list[str]:
        if status != StepStatus.WAITING_APPROVAL:
            self._store.mark_step_running(run_id, step)
        match step.type:
            case StepType.FILE_LOAD:
                return self._run_file_load(step, context)
            case StepType.AGENT:
                return self._run_agent(step, context)
            case StepType.GATE:
                return self._run_gate(run_id, step, context)
            case StepType.KB_UPDATE:
                return self._run_kb_update(run_id, step, context)
            case unreachable:
                assert_never(unreachable)

    def _run_file_load(self, step: WorkflowStep, context: dict[str, str]) -> list[str]:
        loaded: list[str] = []
        for path_template in step.paths:
            source = self._resolve(path_template, context)
            if not source.exists():
                raise WorkflowExecutionError(step.id, f"required file missing: {source}")
            relative_source = source.relative_to(self._repo_root)
            source_text = source.read_text(encoding="utf-8")
            loaded.append(f"## Source: {relative_source}\n\n{source_text}")
        return self._write_outputs(step, context, "\n\n---\n\n".join(loaded))

    def _run_agent(self, step: WorkflowStep, context: dict[str, str]) -> list[str]:
        # Role/prompt files are read here (not in the adapter) so a missing prompt still
        # fails the step exactly as before, independent of which executor is configured.
        role_text = self._read_optional(step, f"agents/{step.role}.md" if step.role else None)
        prompt_text = self._read_optional(step, step.prompt)
        request = AgentRequest(
            step_id=step.id,
            run_id=context["run_id"],
            workflow_id=context["workflow_id"],
            role=step.role or "local-adapter",
            role_contract=role_text or "[no role contract configured]",
            prompt_source=prompt_text or "[no prompt configured]",
            inputs_json=json.dumps(context, ensure_ascii=False, indent=2),
        )
        result = self.adapter.generate(request)
        if not result.ok:
            raise WorkflowExecutionError(step.id, f"agent executor failed: {result.detail}")
        return self._write_outputs(step, context, result.text)

    def _run_gate(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
    ) -> list[str]:
        approval = self._store.approval_for(run_id, step.id)
        if step.requires_approval and approval is None:
            payload = self._gate_payload(step, GateDecision.WAITING_APPROVAL, context)
            outputs = self._write_outputs(
                step,
                context,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            self._store.mark_step_waiting(run_id, step.id, outputs)
            self._store.record_event(
                run_id,
                step.id,
                "gate.waiting",
                f"Approval required for {step.id}",
            )
            return outputs
        if approval == ApprovalDecision.REJECTED:
            raise WorkflowExecutionError(step.id, "manual gate rejected")
        # Approved manual gates pass on the human's authority; auto gates are evaluated
        # against the gated artifacts so a stub/empty/incomplete output cannot pass silently.
        status = (
            GateDecision.PASS
            if approval == ApprovalDecision.APPROVED
            else self._evaluate_gate(run_id, step)
        )
        payload = self._gate_payload(step, status, context)
        outputs = self._write_outputs(
            step,
            context,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        if status.value not in allowed_statuses(step.pass_if):
            msg = f"gate {status.value}: artifact failed quality check"
            raise WorkflowExecutionError(step.id, msg)
        return outputs

    def _evaluate_gate(self, run_id: str, step: WorkflowStep) -> GateDecision:
        texts: list[str] = []
        for dependency in step.depends_on:
            for relative in self._store.get_step_outputs(run_id, dependency):
                source = self._repo_root / relative
                if source.exists():
                    texts.append(source.read_text(encoding="utf-8"))
        if not texts:
            return GateDecision.PASS
        return evaluate_artifacts(texts).status

    def _run_kb_update(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
    ) -> list[str]:
        body = "\n".join(
            [
                f"# KB Update Queue: {step.id}",
                "",
                f"- client: {context.get('client', '[unknown]')}",
                f"- run_id: {run_id}",
                "- status: queued-for-reporter",
                "",
                "Reporter must verify and append durable insights.",
                "Runner does not write directly to knowledge-base.",
            ],
        )
        outputs = self._write_outputs(step, context, body)
        for output in outputs:
            self._store.record_kb_update(run_id, step.id, context.get("client", ""), output, body)
        return outputs

    def _gate_payload(
        self,
        step: WorkflowStep,
        status: GateDecision,
        context: dict[str, str],
    ) -> dict[str, str]:
        return {
            "step_id": step.id,
            "status": status.value,
            "run_id": context["run_id"],
            "workflow_id": context["workflow_id"],
            "pass_if": step.pass_if or "status in ['PASS','WARN']",
        }

    def _write_outputs(
        self,
        step: WorkflowStep,
        context: dict[str, str],
        content: str,
    ) -> list[str]:
        written: list[str] = []
        for output_template in step.outputs:
            target = self._resolve(output_template, context)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content.rstrip() + "\n", encoding="utf-8")
            written.append(str(target.relative_to(self._repo_root)).replace("\\", "/"))
        return written

    def _read_optional(self, step: WorkflowStep, path_template: str | None) -> str:
        if path_template is None:
            return ""
        # role/prompt templates are static references (agents/, playbooks/) resolved with only
        # run_id/workflow_id, NOT client inputs. A ${input} variable here is unsupported and will
        # fail the paths guard with "unresolved variable in path".
        path = self._resolve(path_template, {"run_id": "", "workflow_id": ""})
        if not path.exists():
            raise WorkflowExecutionError(step.id, f"required file missing: {path}")
        return path.read_text(encoding="utf-8")

    def _resolve(self, path_template: str, context: dict[str, str]) -> Path:
        return resolve_inside_repo(self._repo_root, path_template, context)

    def _successful_outputs_present(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
    ) -> bool:
        recorded_outputs = self._store.get_step_outputs(run_id, step.id)
        if not recorded_outputs and not step.outputs:
            return True
        paths = recorded_outputs or [
            str(self._resolve(output, context).relative_to(self._repo_root)).replace("\\", "/")
            for output in step.outputs
        ]
        return all((self._repo_root / path).exists() for path in paths)
