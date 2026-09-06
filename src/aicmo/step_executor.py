from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Future, InvalidStateError
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from time import perf_counter
from typing import assert_never
from uuid import uuid4

from aicmo.adapters import (
    ARTIFACT_REF_CONTENT_BUDGET,
    ARTIFACT_REF_TRUNCATION_MARKER,
    OFFLINE_STUB_MARKER,
    AgentRequest,
    AgentResult,
    ArtifactRef,
    LocalAdapter,
    StepAdapter,
)
from aicmo.errors import WorkflowExecutionError
from aicmo.gate import (
    REVIEW_DECISION_SCHEMA_VERSION,
    allowed_statuses,
    evaluate_artifacts,
    stricter,
)
from aicmo.local_pack import WORKFLOW_ID as LOCAL_PACK_WORKFLOW
from aicmo.local_pack import validate_pack
from aicmo.models import (
    ApprovalDecision,
    GateDecision,
    StepStatus,
    StepType,
    WorkflowSpec,
    WorkflowStep,
)
from aicmo.paths import resolve_inside_repo
from aicmo.redaction import minimize_customer_pii
from aicmo.reviewer_contract import (
    REVIEW_CLIENT_CRITERIA,
    REVIEW_CLIENT_CRITERIA_LIMIT,
    REVIEW_CONTRACT,
    REVIEW_INPUT_LIMIT,
    ReviewerResolution,
    resolve_reviewer_output,
)
from aicmo.store import WorkflowStore

PhaseAnnouncer = Callable[[WorkflowStep, tuple[str, ...]], None]
PhaseCompletionHook = Callable[[WorkflowStep, tuple[str, ...]], None]
type _LeaseSignal = Future[None]
DELIVERY_MANIFEST_SCHEMA_VERSION = "aicmo.delivery-manifest.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observation_text(value: object) -> str:
    if value is None:
        return "unavailable"
    text = minimize_customer_pii(str(value))
    return text if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,159}", text) else "unavailable"


@dataclass(frozen=True, slots=True)
class WorkflowStepExecutor:
    repo_root: Path
    store: WorkflowStore
    adapter: StepAdapter = field(default_factory=LocalAdapter)
    review_adapter: StepAdapter | None = None
    runner_token: str = field(default_factory=lambda: uuid4().hex)
    lease_ttl_seconds: float = 30.0
    heartbeat_interval_seconds: float = 10.0
    phase_announcer: PhaseAnnouncer | None = None
    phase_completed: PhaseCompletionHook | None = None

    def _execute_step(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
        status: StepStatus,
        artifact_refs: tuple[ArtifactRef, ...],
    ) -> list[str]:
        if self.phase_announcer is not None:
            self.phase_announcer(step, self._declared_outputs(step, context))
        owns_lease = status != StepStatus.WAITING_APPROVAL
        if owns_lease and not self.store.mark_step_running(
            run_id,
            step,
            self.runner_token,
            self.lease_ttl_seconds,
        ):
            raise WorkflowExecutionError(step.id, "step is held by another live runner")
        with self._lease_heartbeat(run_id, step.id, active=owns_lease) as lease_signal:
            match step.type:
                case StepType.FILE_LOAD:
                    return self._run_file_load(step, context, lease_signal)
                case StepType.AGENT:
                    return self._run_agent(step, context, artifact_refs, lease_signal)
                case StepType.GATE:
                    return self._run_gate(run_id, step, context, status, lease_signal)
                case StepType.KB_UPDATE:
                    return self._run_kb_update(run_id, step, context, lease_signal)
                case unreachable:
                    assert_never(unreachable)

    @contextmanager
    def _lease_heartbeat(
        self,
        run_id: str,
        step_id: str,
        *,
        active: bool,
    ) -> Iterator[_LeaseSignal]:
        failure = Future[None]()
        if not active:
            failure.set_result(None)
            yield failure
            return
        stop = threading.Event()

        def beat() -> None:
            while not stop.wait(self.heartbeat_interval_seconds):
                try:
                    self._renew_lease(run_id, step_id)
                except WorkflowExecutionError as exc:
                    with suppress(InvalidStateError):
                        failure.set_exception(exc)
                    return
                except Exception as exc:  # noqa: BLE001  # noqa: BROAD_EXCEPT_OK
                    reason = f"lease heartbeat failed: {type(exc).__name__}: {exc}"
                    with suppress(InvalidStateError):
                        failure.set_exception(WorkflowExecutionError(step_id, reason))
                    return

        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        try:
            yield failure
        finally:
            stop.set()
            thread.join(timeout=self.heartbeat_interval_seconds + 1.0)
        failure.result() if failure.done() else None

    def _check_lease(self, run_id: str, step_id: str, failure: _LeaseSignal) -> bool:
        if failure.done():
            failure.result()
            return False
        self._renew_lease(run_id, step_id)
        if failure.done():
            failure.result()
        return True

    def _renew_lease(self, run_id: str, step_id: str) -> None:
        if not self.store.renew_lease(run_id, step_id, self.runner_token):
            raise WorkflowExecutionError(step_id, "step lease lost during execution")

    def _run_file_load(
        self,
        step: WorkflowStep,
        context: dict[str, str],
        lease_signal: _LeaseSignal,
    ) -> list[str]:
        loaded: list[str] = []
        for path_template in step.paths:
            source = self._resolve(path_template, context)
            if not source.exists():
                raise WorkflowExecutionError(step.id, f"required file missing: {source}")
            relative_source = source.relative_to(self.repo_root)
            source_text = source.read_text(encoding="utf-8")
            loaded.append(f"## Source: {relative_source}\n\n{source_text}")
        return self._write_outputs(step, context, "\n\n---\n\n".join(loaded), lease_signal)

    def _run_agent(
        self,
        step: WorkflowStep,
        context: dict[str, str],
        artifact_refs: tuple[ArtifactRef, ...],
        lease_signal: _LeaseSignal,
    ) -> list[str]:
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
            model=step.model or "",
            artifact_refs=artifact_refs,
        )
        request = replace(
            request,
            artifact_refs=self._minimize_artifact_refs(request.artifact_refs, context),
        )
        if context["workflow_id"] == LOCAL_PACK_WORKFLOW and any(
            ref.truncated for ref in artifact_refs
        ):
            raise WorkflowExecutionError(step.id, "local pack context was truncated")
        result = self._invoke_adapter(self.adapter, request)
        if not result.ok:
            detail = self._minimize_pii(result.detail, context)
            raise WorkflowExecutionError(step.id, f"agent executor failed: {detail}")
        content = self._minimize_pii(result.text, context)
        if (
            context["workflow_id"] == LOCAL_PACK_WORKFLOW
            and step.id == "drafts"
            and OFFLINE_STUB_MARKER not in content
        ):
            validate_pack(content, context)
        return self._write_outputs(step, context, content, lease_signal)

    def _invoke_adapter(self, adapter: StepAdapter, request: AgentRequest) -> AgentResult:
        """Record logical adapter calls, including reviewer repair, without content or prices."""
        started = perf_counter()
        call_id = uuid4().hex
        attempt = next(
            str(row["attempt"])
            for row in self.store.list_steps(request.run_id)
            if row["step_id"] == request.step_id
        )
        base = {
            "schema_version": "aicmo.adapter-call.v1",
            "call_id": call_id,
            "adapter": _observation_text(type(adapter).__name__),
            "role": _observation_text(request.role),
            "attempt": attempt,
        }
        self.store.record_event(
            request.run_id,
            request.step_id,
            "agent.call_started",
            "Adapter call started",
            base,
        )
        try:
            result = adapter.generate(request)
        except Exception:
            self.store.record_event(
                request.run_id,
                request.step_id,
                "agent.call_finished",
                "Adapter call raised",
                {
                    **base,
                    "result": "error",
                    "usage_status": "unavailable",
                    "cost_status": "unavailable",
                    "elapsed_ms": str(round((perf_counter() - started) * 1000)),
                },
            )
            raise
        usage = result.usage
        metadata: dict[str, str] = {}
        if usage is not None:
            for key, value in asdict(usage).items():
                if key.endswith("_tokens"):
                    metadata[key] = (
                        str(value) if type(value) is int and value >= 0 else "unavailable"
                    )
                else:
                    metadata[key] = _observation_text(value)
        measured = all(
            metadata.get(key, "unavailable") != "unavailable"
            for key in ("input_tokens", "output_tokens")
        )
        self.store.record_event(
            request.run_id,
            request.step_id,
            "agent.call_finished",
            "Adapter response recorded",
            {
                **base,
                "result": "response_ok" if result.ok else "error",
                "usage_status": "reported" if measured else "unavailable",
                "cost_status": "not_applicable"
                if isinstance(adapter, LocalAdapter)
                else "unavailable",
                "execution_mode": "demo"
                if isinstance(adapter, LocalAdapter)
                else "configured_executor",
                "elapsed_ms": str(round((perf_counter() - started) * 1000)),
                **metadata,
            },
        )
        return result

    @staticmethod
    def _minimize_pii(text: str, context: dict[str, str]) -> str:
        allowed = (
            (context.get("public_store_phone", ""),)
            if context.get("public_contact_approved", "false").casefold() == "true"
            else ()
        )
        return minimize_customer_pii(text, allowed=allowed)

    def _minimize_artifact_refs(
        self,
        refs: tuple[ArtifactRef, ...],
        context: dict[str, str],
    ) -> tuple[ArtifactRef, ...]:
        return tuple(
            ArtifactRef(
                producer_step_id=ref.producer_step_id,
                path=ref.path,
                sha256=ref.sha256,
                content_excerpt=self._minimize_pii(ref.content_excerpt, context),
                truncated=ref.truncated,
            )
            for ref in refs
        )

    def _run_gate(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
        status: StepStatus,
        lease_signal: _LeaseSignal,
    ) -> list[str]:
        approval = self.store.approval_for(run_id, step.id)
        if step.requires_approval and approval is None:
            if status == StepStatus.WAITING_APPROVAL:
                # Idempotent re-wait: the step already holds its waiting state and
                # outputs; a resume without an approval decision changes nothing
                # (and must not re-snapshot files the owner may be editing).
                return self.store.get_step_outputs(run_id, step.id)
            self._snapshot_run_artifacts(run_id, step.id, context, lease_signal)
            payload = self._gate_payload(run_id, step, GateDecision.WAITING_APPROVAL, context)
            outputs = self._write_outputs(
                step,
                context,
                json.dumps(payload, ensure_ascii=False, indent=2),
                lease_signal,
            )
            self._check_lease(run_id, step.id, lease_signal)
            # mark_step_waiting releases the lease while the heartbeat thread is
            # still alive; resolve the signal first so a post-release renewal
            # failure cannot fail a legitimately waiting gate. Ownership stays
            # fail-closed via mark_step_waiting's owner guard below.
            with suppress(InvalidStateError):
                lease_signal.set_result(None)
            if not self.store.mark_step_waiting(
                run_id,
                step.id,
                outputs,
                owner=self.runner_token,
            ):
                raise WorkflowExecutionError(step.id, "step lease lost before gate wait")
            self.store.record_event(
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
        if approval == ApprovalDecision.APPROVED:
            decision, semantic_review = GateDecision.PASS, None
        else:
            decision, semantic_review = self._evaluate_gate(run_id, step, context)
        payload = self._gate_payload(run_id, step, decision, context, semantic_review)
        outputs = self._write_outputs(
            step,
            context,
            json.dumps(payload, ensure_ascii=False, indent=2),
            lease_signal,
        )
        if decision.value not in allowed_statuses(step.pass_if):
            msg = f"gate {decision.value}: artifact failed quality check"
            raise WorkflowExecutionError(step.id, msg)
        return outputs

    def _snapshot_run_artifacts(
        self,
        run_id: str,
        step_id: str,
        context: dict[str, str],
        lease_signal: _LeaseSignal,
    ) -> None:
        """Write-once copies of every successful step's outputs, taken when an
        approval gate first waits. Human edits happen after this point, so the
        snapshot is the diff base for reflection steps. The scope deliberately
        matches what approve --accept-edits blesses (all successful steps), and
        each file mirrors its full relative path under _pre_edit/ so same-named
        outputs can never collide. Existing snapshots are never overwritten — a
        resumed wait must not capture already-edited files as the original."""
        if not context.get("run_id"):
            return
        snapshot_root = self._resolve("artifacts/${run_id}/_pre_edit", context)
        for row in self.store.list_steps(run_id):
            if row["status"] != StepStatus.SUCCESS.value:
                continue
            for relative in self.store.get_step_outputs(run_id, str(row["step_id"])):
                source = self._stored_artifact_path(relative)
                if source is None or not source.exists():
                    continue
                target = snapshot_root / relative
                if target.exists():
                    continue
                active = self._check_lease(run_id, step_id, lease_signal)
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(f"{target.name}.{self.runner_token}.tmp")
                try:
                    tmp.write_bytes(source.read_bytes())
                    self._replace_output(run_id, step_id, lease_signal, active, tmp, target)
                finally:
                    tmp.unlink(missing_ok=True)

    def _stored_artifact_path(self, relative: str) -> Path | None:
        """Containment re-check for output paths read back from the store.

        Paths are validated at write time, so this is defense in depth: a row
        tampered directly in SQLite must not let the engine read or copy files
        outside the repository."""
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            return None
        resolved = (self.repo_root / candidate).resolve()
        if not resolved.is_relative_to(self.repo_root.resolve()):
            return None
        return resolved

    def _artifact_refs(self, run_id: str, step: WorkflowStep) -> tuple[ArtifactRef, ...]:
        remaining = ARTIFACT_REF_CONTENT_BUDGET
        refs: list[ArtifactRef] = []
        for dependency in step.depends_on:
            for relative in self.store.get_step_outputs(run_id, dependency):
                source = self._stored_artifact_path(relative)
                if source is None or not source.is_file():
                    continue
                excerpt, truncated = self._artifact_excerpt(source, remaining)
                remaining -= len(excerpt.encode("utf-8"))
                refs.append(
                    ArtifactRef(
                        producer_step_id=dependency,
                        path=relative,
                        sha256=_sha256(source),
                        content_excerpt=excerpt,
                        truncated=truncated,
                    ),
                )
        return tuple(refs)

    def _artifact_excerpt(self, source: Path, budget: int) -> tuple[str, bool]:
        with source.open("rb") as stream:
            raw = stream.read(budget + 1)
        encoded = raw.decode("utf-8", errors="replace").encode("utf-8")
        truncated = len(raw) > budget or len(encoded) > budget
        if not truncated:
            return encoded.decode("utf-8"), False
        marker = ARTIFACT_REF_TRUNCATION_MARKER.encode("utf-8")
        if budget < len(marker):
            return "", True
        prefix = encoded[: budget - len(marker)].decode("utf-8", errors="ignore")
        return prefix + ARTIFACT_REF_TRUNCATION_MARKER, True

    def _consumed_ref_digest(self, refs: tuple[ArtifactRef, ...]) -> str:
        payload = json.dumps(
            [[ref.version, ref.producer_step_id, ref.path, ref.sha256] for ref in refs],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _reopen_stale_successes(
        self,
        spec: WorkflowSpec,
        run_id: str,
        context: dict[str, str],
    ) -> None:
        if self.store.is_run_cancelled(run_id):
            return
        stale: set[str] = set()
        for step in spec.execution_order():
            if self.store.get_step_status(run_id, step.id) != StepStatus.SUCCESS:
                continue
            if not self._successful_outputs_present(run_id, step, context):
                stale.add(step.id)
                continue
            if step.depends_on and self.store.get_consumed_ref_digest(
                run_id,
                step.id,
            ) != self._consumed_ref_digest(self._artifact_refs(run_id, step)):
                stale.add(step.id)
        self._reopen_successes_and_dependents(spec, run_id, stale)

    def _reopen_successes_and_dependents(
        self,
        spec: WorkflowSpec,
        run_id: str,
        roots: set[str],
    ) -> None:
        invalidated = set(roots)
        for step in spec.execution_order():
            if any(dependency in invalidated for dependency in step.depends_on):
                invalidated.add(step.id)
        for step in spec.execution_order():
            if step.id in invalidated and self.store.get_step_status(run_id, step.id) in {
                StepStatus.SUCCESS,
                StepStatus.WAITING_APPROVAL,
            }:
                self.store.reopen_step(run_id, step.id)

    def _evaluate_gate(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
    ) -> tuple[GateDecision, ReviewerResolution | None]:
        texts = self._gate_texts(run_id, step)
        if not texts:
            # Fail closed: an auto gate with no gated artifact text cannot validate
            # anything, so it must block rather than silently pass.
            return GateDecision.FAIL, None
        deterministic = evaluate_artifacts(texts).status
        if deterministic == GateDecision.FAIL or self.review_adapter is None:
            return deterministic, None
        review = self._semantic_review(step, context, texts)
        return stricter(deterministic, review.decision), review

    def _gate_texts(self, run_id: str, step: WorkflowStep) -> list[str]:
        texts: list[str] = []
        for dependency in step.depends_on:
            for relative in self.store.get_step_outputs(run_id, dependency):
                source = self._stored_artifact_path(relative)
                if source is not None and source.exists():
                    content = source.read_text(encoding="utf-8")
                    if (
                        step.terminal_delivery
                        and dependency == "drafts"
                        and self.store.get_run(run_id)["workflow_id"] == LOCAL_PACK_WORKFLOW
                        and OFFLINE_STUB_MARKER not in content
                    ):
                        validate_pack(content, self.store.get_inputs(run_id))
                    texts.append(content)
        return texts

    def _semantic_review(
        self,
        step: WorkflowStep,
        context: dict[str, str],
        texts: list[str],
    ) -> ReviewerResolution:
        review_adapter = self.review_adapter
        if review_adapter is None:
            msg = "semantic review requires a configured reviewer"
            raise RuntimeError(msg)
        review_input = self._minimize_pii(
            "\n\n---\n\n".join(texts)[:REVIEW_INPUT_LIMIT],
            context,
        )
        policy_sources: list[str] = []
        role_contracts = [REVIEW_CONTRACT]
        declared_policy_sources = tuple(
            relative
            for relative in (
                f"agents/{step.role}.md" if step.role else None,
                step.prompt,
            )
            if relative is not None
        )
        for relative in declared_policy_sources:
            source = self._resolve(relative, {})
            if source.is_file():
                policy_sources.append(relative)
                role_contracts.append(source.read_text(encoding="utf-8"))
        client = context.get("client", "")
        client_criteria: list[dict[str, str]] = []
        criteria_remaining = REVIEW_CLIENT_CRITERIA_LIMIT
        for filename in REVIEW_CLIENT_CRITERIA if client else ():
            relative = f"clients/{client}/{filename}"
            source = self._resolve(relative, {})
            if source.is_file() and criteria_remaining:
                content = self._minimize_pii(
                    source.read_text(encoding="utf-8")[:criteria_remaining],
                    context,
                )
                client_criteria.append({"path": relative, "content": content})
                criteria_remaining -= len(content)
        request = AgentRequest(
            step_id=step.id,
            run_id=context["run_id"],
            workflow_id=context["workflow_id"],
            role="reviewer",
            role_contract="\n\n---\n\n".join(role_contracts),
            prompt_source=review_input,
            inputs_json=json.dumps(
                {
                    "policy_version": REVIEW_DECISION_SCHEMA_VERSION,
                    "policy_sources": policy_sources,
                    "client": client,
                    "client_criteria": client_criteria,
                    **(
                        {"brief_json": context["brief_json"]}
                        if context["workflow_id"] == LOCAL_PACK_WORKFLOW
                        else {}
                    ),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            model=step.model or "",
            artifact_refs=self._minimize_artifact_refs(
                self._artifact_refs(context["run_id"], step),
                context,
            ),
        )
        result = self._invoke_adapter(review_adapter, request)
        result = replace(result, text=self._minimize_pii(result.text, context))
        resolution = resolve_reviewer_output(
            review_adapter,
            request,
            result,
            generate=lambda repair: self._invoke_adapter(review_adapter, repair),
        )
        self.store.record_event(
            context["run_id"],
            step.id,
            "gate.reviewer",
            "Structured reviewer decision evaluated",
            {
                "schema_version": REVIEW_DECISION_SCHEMA_VERSION,
                "adapter": type(review_adapter).__name__,
                "attempts": str(resolution.attempts),
                "outcome": resolution.outcome,
                "effective_decision": resolution.decision.value,
                "input_sha256": hashlib.sha256(review_input.encode()).hexdigest(),
                "initial_response_sha256": hashlib.sha256(
                    resolution.initial_response.encode(),
                ).hexdigest(),
                "effective_response_sha256": hashlib.sha256(
                    resolution.effective_response.encode(),
                ).hexdigest(),
                "policy_sources": policy_sources,
                "artifact_ref_count": str(len(request.artifact_refs)),
            },
        )
        return resolution

    def _run_kb_update(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
        lease_signal: _LeaseSignal,
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
        outputs = self._write_outputs(step, context, body, lease_signal)
        for output in outputs:
            self._check_lease(run_id, step.id, lease_signal)
            self.store.record_kb_update(run_id, step.id, context.get("client", ""), output, body)
        return outputs

    def _gate_payload(
        self,
        run_id: str,
        step: WorkflowStep,
        status: GateDecision,
        context: dict[str, str],
        semantic_review: ReviewerResolution | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "step_id": step.id,
            "status": status.value,
            "run_id": run_id,
            "workflow_id": context["workflow_id"],
            "pass_if": step.pass_if or "status in ['PASS','WARN']",
        }
        if not step.terminal_delivery:
            return payload

        texts = self._gate_texts(run_id, step)
        combined = "\n\n---\n\n".join(texts)
        refs = self._artifact_refs(run_id, step)
        deterministic = evaluate_artifacts(texts)
        reasons = list(deterministic.reasons)
        demo = isinstance(self.adapter, LocalAdapter) or any(
            OFFLINE_STUB_MARKER in text for text in texts
        )
        review_truncated = len(combined) > REVIEW_INPUT_LIMIT
        if self.review_adapter is None:
            reasons.append("semantic reviewer was not configured")
        if semantic_review is not None and semantic_review.decision != GateDecision.PASS:
            reasons.append(semantic_review.reason)
        elif status != GateDecision.PASS and not deterministic.reasons:
            reasons.append(f"review gate returned {status.value}")
        if review_truncated:
            reasons.append("semantic review input was truncated")
        if any(ref.truncated for ref in refs):
            reasons.append("artifact reference was truncated")
        if not refs:
            reasons.append("no versioned artifact reference was produced")
        deliverable = (
            not demo
            and self.review_adapter is not None
            and status == GateDecision.PASS
            and not review_truncated
            and bool(refs)
            and not any(ref.truncated for ref in refs)
        )
        payload.update(
            {
                "schema_version": DELIVERY_MANIFEST_SCHEMA_VERSION,
                "delivery_status": (
                    "deliverable" if deliverable else "demo" if demo else "blocked"
                ),
                "deliverable": deliverable,
                "reasons": list(dict.fromkeys(reasons)),
                "generator": type(self.adapter).__name__,
                "reviewer": (
                    type(self.review_adapter).__name__ if self.review_adapter is not None else None
                ),
                "semantic_review": (
                    {
                        "status": semantic_review.decision.value,
                        "reason": semantic_review.reason,
                        "outcome": semantic_review.outcome,
                    }
                    if semantic_review is not None
                    else None
                ),
                "review_input": {
                    "characters_total": len(combined),
                    "characters_reviewed": min(len(combined), REVIEW_INPUT_LIMIT),
                    "truncated": review_truncated,
                },
                "artifacts": [
                    {
                        "version": ref.version,
                        "producer_step_id": ref.producer_step_id,
                        "path": ref.path,
                        "sha256": ref.sha256,
                        "truncated": ref.truncated,
                    }
                    for ref in refs
                ],
            },
        )
        return payload

    def _write_outputs(
        self,
        step: WorkflowStep,
        context: dict[str, str],
        content: str,
        lease_signal: _LeaseSignal,
    ) -> list[str]:
        content = self._minimize_pii(content, context)
        written: list[str] = []
        for output_template in self._output_templates(step):
            target = self._resolve(output_template, context)
            active = self._check_lease(context["run_id"], step.id, lease_signal)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f"{target.name}.{self.runner_token}.tmp")
            try:
                tmp.write_text(content.rstrip() + "\n", encoding="utf-8")
                self._replace_output(
                    context["run_id"],
                    step.id,
                    lease_signal,
                    active,
                    tmp,
                    target,
                )
            finally:
                tmp.unlink(missing_ok=True)
            written.append(str(target.relative_to(self.repo_root)).replace("\\", "/"))
        return written

    def _replace_output(
        self,
        run_id: str,
        step_id: str,
        lease_signal: _LeaseSignal,
        active: bool,
        tmp: Path,
        target: Path,
    ) -> None:
        if not active:
            tmp.replace(target)
            return
        with self.store.hold_lease_for_write(run_id, step_id, self.runner_token) as owned:
            if lease_signal.done():
                lease_signal.result()
            if not owned:
                raise WorkflowExecutionError(step_id, "step lease lost before artifact replace")
            tmp.replace(target)

    def _output_templates(self, step: WorkflowStep) -> tuple[str, ...]:
        if step.outputs:
            return step.outputs
        return (f"artifacts/${{run_id}}/{step.id}.md",)

    def _declared_outputs(self, step: WorkflowStep, context: dict[str, str]) -> tuple[str, ...]:
        return tuple(
            str(self._resolve(template, context).relative_to(self.repo_root)).replace("\\", "/")
            for template in self._output_templates(step)
        )

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
        return resolve_inside_repo(self.repo_root, path_template, context)

    def _successful_outputs_present(
        self,
        run_id: str,
        step: WorkflowStep,
        context: dict[str, str],
    ) -> bool:
        recorded_outputs = self.store.get_step_outputs(run_id, step.id)
        paths = recorded_outputs or [
            str(self._resolve(output, context).relative_to(self.repo_root)).replace("\\", "/")
            for output in self._output_templates(step)
        ]
        stored = self.store.get_output_hashes(run_id, step.id)
        for path in paths:
            full = self._stored_artifact_path(path)
            if full is None or not full.exists():
                return False
            expected = stored.get(path)
            if expected is not None and _sha256(full) != expected:
                return False
        return True

    def _hash_outputs(self, outputs: list[str]) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for path in outputs:
            full = self._stored_artifact_path(path)
            if full is not None and full.exists():
                hashes[path] = _sha256(full)
        return hashes
