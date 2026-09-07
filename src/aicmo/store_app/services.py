from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from aicmo.adapters import CommandAdapter
from aicmo.errors import AicmoError, RunNotFoundError, StepTransitionError
from aicmo.export import export_local_pack, verified_delivery
from aicmo.local_pack import WORKFLOW_ID, LocalPack, parse_brief, validate_pack
from aicmo.models import ApprovalDecision, WorkflowStep
from aicmo.pack_edits import EditApproval, EditBase
from aicmo.paths import resolve_inside_repo
from aicmo.runner import WorkflowRunner
from aicmo.source_input import prepare_workflow_inputs
from aicmo.spec import load_workflow_spec
from aicmo.store import WorkflowStore
from aicmo.store_app.models import EditDraft, Job, Store
from aicmo.web_run_lock import web_run_lock

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.db.models import QuerySet


class StoreActionError(Exception):
    pass


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["aicmo.web-approval.v1"]
    pack_sha: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    photo_sha: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    reviewer: Annotated[str, Field(pattern=r"^web-user:[1-9][0-9]*$")]
    requested_at: datetime


def allowed_stores(user: AbstractBaseUser | AnonymousUser) -> QuerySet[Store]:
    if not isinstance(user, User) or not user.is_active:
        return Store.objects.none()
    if user.has_perm("store_app.operate_stores"):
        return Store.objects.all()
    return Store.objects.filter(owner_id=user.pk)


def owned_job(user: AbstractBaseUser | AnonymousUser, job_id: uuid.UUID) -> Job:
    job = Job.objects.filter(pk=job_id, store__in=allowed_stores(user)).first()
    if job is None:
        raise Http404
    return job


def configured_commands() -> tuple[CommandAdapter, CommandAdapter]:
    def command(name: str) -> CommandAdapter:
        try:
            value = TypeAdapter(list[str]).validate_json(os.environ.get(name, "null"), strict=True)
        except ValueError:
            value = None
        if not value or not all(value):
            reason = "운영자가 작성·검토 서비스를 연결해야 합니다."
            raise StoreActionError(reason)
        return CommandAdapter(command=tuple(value))

    return command("AICMO_WEB_EXECUTOR_CMD"), command("AICMO_WEB_REVIEW_CMD")


def engine() -> WorkflowRunner:
    adapter, review_adapter = configured_commands()
    root = Path(settings.REPO_ROOT)
    return WorkflowRunner(
        root,
        WorkflowStore(root / ".aicmo/runs.sqlite3"),
        adapter=adapter,
        review_adapter=review_adapter,
    )


def reader() -> WorkflowRunner:
    root = Path(settings.REPO_ROOT)
    return WorkflowRunner(root, WorkflowStore(root / ".aicmo/runs.sqlite3", read_only=True))


def submit(store: Store, submission_key: uuid.UUID, brief: str) -> Job:
    inputs = {"client": str(store.client), "brief_json": brief}
    spec = load_workflow_spec(Path(settings.REPO_ROOT), WORKFLOW_ID)
    inputs = prepare_workflow_inputs(spec.inputs, inputs).values
    parse_brief(inputs)
    # No user-supplied client, path, workflow or executor reaches a job.
    try:
        with transaction.atomic():
            prior = Job.objects.filter(store=store, submission_key=submission_key).first()
            if prior is not None:
                if prior.inputs != inputs:
                    reason = "같은 제출에서 내용이 바뀌었습니다. 만들기 화면을 다시 열어 주세요."
                    raise StoreActionError(reason)
                return prior
            return Job.objects.create(store=store, submission_key=submission_key, inputs=inputs)
    except IntegrityError:
        prior = Job.objects.filter(store=store, submission_key=submission_key).first()
        if prior is not None and prior.inputs == inputs:
            return prior
        reason = "진행 중인 작업을 먼저 확인하거나 취소해 주세요."
        raise StoreActionError(reason) from None


def preview(job: Job) -> tuple[LocalPack, str, str]:
    runner = reader()
    inputs = runner.store.get_inputs(job.run_id)
    if inputs.get("client") != job.store.client:
        reason = "가게 연결을 확인할 수 없습니다. 운영자에게 문의해 주세요."
        raise StoreActionError(reason)
    path = f"artifacts/{job.run_id}/local-pack.json"
    source = resolve_inside_repo(runner.repo_root, path, {})
    with source.open("rb") as stream:
        raw = stream.read(12 * 1024 + 1)
    digest = hashlib.sha256(raw).hexdigest()
    if runner.store.get_output_hashes(job.run_id, "drafts").get(path) != digest:
        reason = "문안 버전이 바뀌었습니다. 운영자 확인이 필요합니다."
        raise StoreActionError(reason)
    photo_digest, _ = runner.verified_photos(job.run_id)
    return validate_pack(raw.decode("utf-8"), inputs), digest, photo_digest


def request_approval(job: Job, pack_sha: str, photo_sha: str, user_id: str) -> None:
    with web_run_lock(Path(settings.REPO_ROOT), job.run_id, blocking=False):
        _, current_pack, current_photo = preview(job)
        if (pack_sha, photo_sha) != (current_pack, current_photo):
            reason = "확인한 버전이 달라졌습니다. 화면을 새로 열고 확인해 주세요."
            raise StoreActionError(reason)
        approval = ApprovalRequest.model_validate_json(
            json.dumps(
                {
                    "schema_version": "aicmo.web-approval.v1",
                    "pack_sha": pack_sha,
                    "photo_sha": photo_sha,
                    "reviewer": f"web-user:{user_id}",
                    "requested_at": timezone.now().isoformat(),
                }
            )
        ).model_dump(mode="json")
        with transaction.atomic():
            current = Job.objects.select_for_update().get(pk=job.pk)
            if EditDraft.objects.filter(job=current).exists():
                reason = "저장된 수정본의 미리보기에서 확인해 주세요."
                raise StoreActionError(reason)
            prior = (
                ApprovalRequest.model_validate_json(json.dumps(current.approval)).model_dump(
                    mode="json"
                )
                if current.approval != {}
                else {}
            )
            if all(
                prior.get(key) == approval[key] for key in ("pack_sha", "photo_sha", "reviewer")
            ) and current.state in ("queued", "running", "success"):
                return
            if current.state != "waiting_approval" or current.cancel_requested:
                reason = "현재 승인할 수 없는 작업입니다. 화면을 새로 열어 주세요."
                raise StoreActionError(reason)
            current.approval = approval
            current.state = "queued"
            current.save(update_fields=["approval", "state", "updated_at"])


def request_cancel(job: Job) -> None:
    Job.objects.filter(pk=job.pk, state__in=["queued", "running", "waiting_approval"]).update(
        cancel_requested=True
    )


def cancel(job: Job, runner: WorkflowRunner) -> None:
    """Worker-only cancellation; durable intent is cleared after engine reconciliation."""
    job.refresh_from_db()
    if not job.cancel_requested:
        return
    state = "cancelled"
    notice = ""
    try:
        try:
            runner.store.get_run(job.run_id)
        except RunNotFoundError:
            existing = False
        else:
            existing = True
        if existing:
            with runner.store.connect() as connection:
                pending_edit = connection.execute(
                    "select 1 from pack_edit_receipts where run_id=? and state='applying'",
                    (job.run_id,),
                ).fetchone()
            if pending_edit:
                _apply_approval(
                    job, runner, EditApproval.model_validate_json(json.dumps(job.approval))
                )
            try:
                runner.cancel(job.run_id)
            except StepTransitionError:
                # All steps may have finished just before the completion write.
                if runner.store.get_run(job.run_id)["status"] != "success":
                    runner.complete_verified_local_pack(job.run_id)
                state = delivery_state(runner, job.run_id)
    except (AicmoError, OSError, ValueError, sqlite3.Error, StoreActionError):
        state, notice = "failed", "취소 상태를 확인하지 못했습니다. 운영자에게 문의해 주세요."
    Job.objects.filter(pk=job.pk, cancel_requested=True).update(
        state=state, cancel_requested=False, notice=notice
    )


def download(job: Job) -> Path:
    if job.state != "success" or job.cancel_requested:
        reason = "검토·승인을 마친 파일만 저장할 수 있습니다."
        raise StoreActionError(reason)
    runner = reader()
    if runner.store.get_inputs(job.run_id).get("client") != job.store.client:
        raise Http404
    # Export takes an engine write transaction; this endpoint is POST-only.
    runner = replace(runner, store=WorkflowStore(runner.store.db_path))
    return export_local_pack(runner, job.run_id)


def _job_inputs(job: Job, runner: WorkflowRunner) -> dict[str, str]:
    inputs = TypeAdapter(dict[str, str]).validate_python(job.inputs, strict=True)
    if set(inputs) != {"client", "brief_json"} or inputs["client"] != job.store.client:
        reason = "invalid stored job inputs"
        raise StoreActionError(reason)
    spec = load_workflow_spec(runner.repo_root, WORKFLOW_ID)
    if prepare_workflow_inputs(spec.inputs, inputs).values != inputs:
        reason = "stored job privacy policy changed"
        raise StoreActionError(reason)
    parse_brief(inputs)
    return inputs


def _apply_approval(
    job: Job, runner: WorkflowRunner, approval: ApprovalRequest | EditApproval
) -> None:
    if isinstance(approval, EditApproval):
        draft = EditDraft.objects.filter(job=job).first()
        if (
            draft is None
            or draft.revision != approval.revision
            or EditBase.model_validate_json(json.dumps(draft.base)) != approval.base
        ):
            reason = "confirmed edit draft changed"
            raise StoreActionError(reason)
        runner.apply_pack_edit(job.run_id, approval, draft.body)
        return
    _, pack_sha, photo_sha = preview(job)
    if (pack_sha, photo_sha) != (approval.pack_sha, approval.photo_sha):
        reason = "승인 버전이 바뀌었습니다. 운영자 확인이 필요합니다."
        raise StoreActionError(reason)
    if runner.store.approval_for(job.run_id, "owner_gate") is None:
        runner.approve(job.run_id, "owner_gate", approval.reviewer, "웹에서 문안 확인")
    elif runner.store.approval_for(job.run_id, "owner_gate") != ApprovalDecision.APPROVED:
        reason = "승인 상태를 확인할 수 없습니다."
        raise StoreActionError(reason)
    # The engine approval row is the durable applied receipt; retry never invents an approval.
    with runner.store.connect() as connection:
        applied = connection.execute(
            "select reviewer, photo_manifest_sha256 from approvals "
            "where run_id=? and step_id='owner_gate'",
            (job.run_id,),
        ).fetchone()
    if (
        applied is None
        or applied["reviewer"] != approval.reviewer
        or applied["photo_manifest_sha256"] != approval.photo_sha
    ):
        reason = "engine approval belongs to another request"
        raise StoreActionError(reason)


def execute(job: Job, runner: WorkflowRunner) -> None:
    """One persistent job; called only while holding the repository's worker file lock."""
    job.refresh_from_db()
    if job.cancel_requested:
        cancel(job, runner)
        return
    if not Job.objects.filter(
        pk=job.pk, state__in=["queued", "running"], cancel_requested=False
    ).update(state="running"):
        return
    try:
        inputs = _job_inputs(job, runner)
        approval = (
            TypeAdapter[ApprovalRequest | EditApproval](
                ApprovalRequest | EditApproval
            ).validate_json(json.dumps(job.approval))
            if job.approval != {}
            else None
        )
        runner.store.initialize()
        try:
            existing = runner.store.get_run(job.run_id)
        except RunNotFoundError:
            existing = None
        if existing is not None and (
            existing["workflow_id"] != WORKFLOW_ID or runner.store.get_inputs(job.run_id) != inputs
        ):
            reason = "stored run differs from this job"
            raise StoreActionError(reason)  # noqa: TRY301 — safe worker error boundary
        if existing is not None and approval is not None:
            _apply_approval(job, runner, approval)

        def observe_cancel(_step: WorkflowStep, _paths: tuple[str, ...]) -> None:
            if Job.objects.filter(pk=job.pk, cancel_requested=True).exists():
                runner.cancel(job.run_id)

        runner = replace(runner, phase_announcer=observe_cancel)
        result = (
            runner.run(WORKFLOW_ID, job.run_id, inputs)
            if existing is None
            else runner.resume(job.run_id)
        )
        state = delivery_state(runner, job.run_id) if result.status == "success" else result.status
        notice = "" if state not in ("failed", "needs_work") else "운영자 검토가 필요합니다."
    except (AicmoError, OSError, ValueError, sqlite3.Error, StoreActionError):
        state, notice = "failed", "작업을 완료하지 못했습니다. 운영자에게 문의해 주세요."
    job.refresh_from_db()
    if job.cancel_requested:
        cancel(job, runner)
    else:
        Job.objects.filter(pk=job.pk, cancel_requested=False).update(state=state, notice=notice)


def delivery_state(runner: WorkflowRunner, run_id: str) -> str:
    _, contents = verified_delivery(runner, run_id, WORKFLOW_ID, require_deliverable=False)
    manifest = json.loads(contents[f"artifacts/{run_id}/delivery-review.json"])
    return "success" if manifest["deliverable"] else "needs_work"
