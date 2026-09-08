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

from aicmo import learning
from aicmo.adapters import CommandAdapter
from aicmo.errors import AicmoError, RunNotFoundError, StepTransitionError
from aicmo.export import export_local_pack, verified_delivery, verified_pack
from aicmo.learning import PackFeedback, feedback_report, parse_feedback
from aicmo.local_pack import WORKFLOW_ID, LocalPack, parse_brief, validate_pack
from aicmo.models import ApprovalDecision, StepStatus, WorkflowStep
from aicmo.outcomes import (
    parse_channel,
    parse_outcomes_snapshot,
    read_weekly_outcomes,
    week_start_date,
)
from aicmo.pack_edits import EditApproval, EditBase
from aicmo.paths import resolve_inside_repo
from aicmo.photos import parse_photos, verify_photo_assets
from aicmo.runner import WorkflowRunner
from aicmo.source_input import prepare_workflow_inputs
from aicmo.spec import RUN_SPEC_REVISION, load_workflow_spec, run_spec_digest
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


class FeedbackApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["aicmo.web-feedback-approval.v1"]
    candidate_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    reviewer: Annotated[str, Field(pattern=r"^web-user:[1-9][0-9]*$")]
    requested_at: datetime


def allowed_stores(user: AbstractBaseUser | AnonymousUser) -> QuerySet[Store]:
    if not isinstance(user, User) or not user.is_active:
        return Store.objects.none()
    if user.has_perm("store_app.operate_stores"):
        return Store.objects.all()
    return Store.objects.filter(owner_id=user.pk)


def fresh_actor(user: AbstractBaseUser | AnonymousUser) -> User:
    """Re-read authority inside the caller's write transaction, without permission caches."""
    actor = (
        User.objects.filter(pk=user.pk, is_active=True).first() if isinstance(user, User) else None
    )
    if actor is None:
        raise Http404
    return actor


def owned_store(user: AbstractBaseUser | AnonymousUser, store_id: int) -> Store:
    store = allowed_stores(user).filter(pk=store_id).first()
    if store is None:
        raise Http404
    return store


def owned_job(user: AbstractBaseUser | AnonymousUser, job_id: uuid.UUID) -> Job:
    job = Job.objects.filter(pk=job_id, store__in=allowed_stores(user)).first()
    if job is None:
        raise Http404
    return job


def owned_pack_job(user: AbstractBaseUser | AnonymousUser, job_id: uuid.UUID) -> Job:
    job = owned_job(user, job_id)
    if job.workflow_id != WORKFLOW_ID:
        raise Http404
    return job


def _configured_command(name: str) -> CommandAdapter:
    try:
        value = TypeAdapter(list[str]).validate_json(os.environ.get(name, "null"), strict=True)
    except ValueError:
        value = None
    if not value or not all(value):
        reason = "운영자가 작성·검토 서비스를 연결해야 합니다."
        raise StoreActionError(reason)
    return CommandAdapter(command=tuple(value))


def configured_commands() -> tuple[CommandAdapter, CommandAdapter]:
    return (
        _configured_command("AICMO_WEB_EXECUTOR_CMD"),
        _configured_command("AICMO_WEB_REVIEW_CMD"),
    )


def engine(workflow_id: str = WORKFLOW_ID) -> WorkflowRunner:
    root = Path(settings.REPO_ROOT)
    if workflow_id in ("weekly-report", "local-pack-feedback"):
        return WorkflowRunner(
            root,
            WorkflowStore(root / ".aicmo/runs.sqlite3"),
            review_adapter=_configured_command("AICMO_WEB_REVIEW_CMD"),
        )
    if workflow_id != WORKFLOW_ID:
        reason = "unsupported job workflow"
        raise StoreActionError(reason)
    adapter, review_adapter = configured_commands()
    return WorkflowRunner(
        root,
        WorkflowStore(root / ".aicmo/runs.sqlite3"),
        adapter=adapter,
        review_adapter=review_adapter,
    )


def reader() -> WorkflowRunner:
    root = Path(settings.REPO_ROOT)
    return WorkflowRunner(root, WorkflowStore(root / ".aicmo/runs.sqlite3", read_only=True))


def submit(
    store: Store,
    submission_key: uuid.UUID,
    brief: str,
    photos_json: str | None = None,
    rewrite_json: str | None = None,
    *,
    actor: AbstractBaseUser | AnonymousUser,
) -> Job:
    inputs = {"client": str(store.client), "brief_json": brief}
    if photos_json is not None:
        inputs["photos_json"] = photos_json
    if rewrite_json is not None:
        inputs["rewrite_json"] = rewrite_json
    spec = load_workflow_spec(Path(settings.REPO_ROOT), WORKFLOW_ID)
    inputs = prepare_workflow_inputs(spec.inputs, inputs).values
    parse_brief(inputs)
    photos = parse_photos(inputs).photos
    if photos and (len(photos) != 1 or photos[0].news_index != 0):
        reason = "웹 요청에는 첫 소식의 사진 1장만 넣을 수 있습니다."
        raise StoreActionError(reason)
    verify_photo_assets(Path(settings.REPO_ROOT), inputs)
    # No user-supplied client, path, workflow or executor reaches a job.
    try:
        with transaction.atomic():
            current = owned_store(fresh_actor(actor), store.pk)
            if current.client != store.client:
                raise Http404
            store = current
            prior = Job.objects.filter(store=store, submission_key=submission_key).first()
            if prior is not None:
                if prior.workflow_id != WORKFLOW_ID or prior.inputs != inputs:
                    reason = "같은 제출에서 내용이 바뀌었습니다. 만들기 화면을 다시 열어 주세요."
                    raise StoreActionError(reason)
                return prior
            return Job.objects.create(store=store, submission_key=submission_key, inputs=inputs)
    except IntegrityError:
        with transaction.atomic():
            current = owned_store(fresh_actor(actor), store.pk)
            if current.client != store.client:
                raise Http404 from None
            prior = Job.objects.filter(store=current, submission_key=submission_key).first()
            if prior is not None and prior.workflow_id == WORKFLOW_ID and prior.inputs == inputs:
                return prior
        reason = "진행 중인 작업을 먼저 확인하거나 취소해 주세요."
        raise StoreActionError(reason) from None


def _current_store(store: Store, actor: AbstractBaseUser | AnonymousUser) -> Store:
    current = owned_store(fresh_actor(actor), store.pk)
    if current.client != store.client:
        raise Http404
    return current


def _report_replay(prior: Job, week_start: str, channel: str, expected_snapshot_sha256: str) -> Job:
    if prior.workflow_id == "weekly-report":
        inputs = _job_inputs(prior, reader())
        snapshot = parse_outcomes_snapshot(inputs["outcomes_snapshot_json"])
        if (
            inputs["week_start"] == week_start
            and inputs["channel"] == channel
            and snapshot.snapshot_sha256 == expected_snapshot_sha256
        ):
            return prior
    reason = "같은 제출에서 자료가 바뀌었습니다. 보고서 요청 화면을 다시 열어 주세요."
    raise StoreActionError(reason)


def submit_weekly_report(
    store: Store,
    submission_key: uuid.UUID,
    week_start: str,
    channel: str,
    expected_snapshot_sha256: str,
    *,
    actor: AbstractBaseUser | AnonymousUser,
) -> Job:
    week_start = week_start_date(week_start).isoformat()
    channel = parse_channel(channel)
    try:
        with transaction.atomic():
            current = _current_store(store, actor)
            prior = Job.objects.filter(store=current, submission_key=submission_key).first()
            if prior is not None:
                return _report_replay(prior, week_start, channel, expected_snapshot_sha256)
            _configured_command("AICMO_WEB_REVIEW_CMD")
            runner = reader()
            snapshot = read_weekly_outcomes(
                runner.repo_root, runner.store, str(current.client), week_start, channel
            )
            if snapshot.snapshot_sha256 != expected_snapshot_sha256:
                reason = "숫자가 정정되었습니다. 현재 기록을 다시 확인해 주세요."
                raise StoreActionError(reason)
            inputs = {
                "client": str(current.client),
                "week_start": week_start,
                "channel": channel,
                "outcomes_snapshot_json": snapshot.model_dump_json(),
            }
            spec = load_workflow_spec(runner.repo_root, "weekly-report")
            inputs = prepare_workflow_inputs(spec.inputs, inputs).values
            return Job.objects.create(
                store=current,
                submission_key=submission_key,
                workflow_id="weekly-report",
                inputs=inputs,
            )
    except IntegrityError:
        with transaction.atomic():
            current = _current_store(store, actor)
            prior = Job.objects.filter(store=current, submission_key=submission_key).first()
            if prior is not None:
                return _report_replay(prior, week_start, channel, expected_snapshot_sha256)
        reason = "진행 중인 작업을 먼저 확인하거나 취소해 주세요."
        raise StoreActionError(reason) from None


def _feedback_replay(prior: Job, inputs: dict[str, str]) -> Job:
    if prior.workflow_id == "local-pack-feedback" and prior.inputs == inputs:
        return prior
    reason = "같은 제출에서 내용이 바뀌었습니다. 피드백 화면을 다시 열어 주세요."
    raise StoreActionError(reason)


def submit_feedback(
    store: Store,
    submission_key: uuid.UUID,
    feedback: PackFeedback,
    *,
    actor: AbstractBaseUser | AnonymousUser,
) -> Job:
    feedback = parse_feedback(feedback.model_dump_json())
    inputs = {"client": str(store.client), "feedback_json": feedback.model_dump_json()}
    try:
        with transaction.atomic():
            current = _current_store(store, actor)
            prior = Job.objects.filter(store=current, submission_key=submission_key).first()
            if prior is not None:
                return _feedback_replay(prior, inputs)
            _configured_command("AICMO_WEB_REVIEW_CMD")
            # Native, read-only evidence validation; no candidate file or provider call here.
            feedback_report(reader(), inputs)
            return Job.objects.create(
                store=current,
                submission_key=submission_key,
                workflow_id="local-pack-feedback",
                inputs=inputs,
            )
    except IntegrityError:
        with transaction.atomic():
            current = _current_store(store, actor)
            prior = Job.objects.filter(store=current, submission_key=submission_key).first()
            if prior is not None:
                return _feedback_replay(prior, inputs)
        reason = "진행 중인 작업을 먼저 확인하거나 취소해 주세요."
        raise StoreActionError(reason) from None


def feedback_candidate(job: Job) -> tuple[bytes, str]:
    if job.workflow_id != "local-pack-feedback":
        raise Http404
    runner = reader()
    inputs = _job_inputs(job, runner)
    run = runner.store.get_run(job.run_id)
    spec = load_workflow_spec(runner.repo_root, job.workflow_id)
    if (
        run["workflow_id"] != job.workflow_id
        or runner.store.get_inputs(job.run_id) != inputs
        or run["spec_revision"] != RUN_SPEC_REVISION
        or run["spec_digest"] != run_spec_digest(spec, inputs)
        or runner.store.get_step_status(job.run_id, "candidate") != StepStatus.SUCCESS
    ):
        reason = "피드백 근거를 확인할 수 없습니다. 운영자에게 문의해 주세요."
        raise StoreActionError(reason)
    path = f"artifacts/{job.run_id}/feedback.json"
    with resolve_inside_repo(runner.repo_root, path, {}).open("rb") as stream:
        raw = stream.read(24 * 1024 + 1)
    digest = hashlib.sha256(raw).hexdigest()
    if (
        len(raw) > 24 * 1024
        or runner.store.get_output_hashes(job.run_id, "candidate").get(path) != digest
        or json.loads(raw) != json.loads(feedback_report(runner, inputs))
    ):
        reason = "피드백 근거가 바뀌었습니다. 화면을 다시 확인해 주세요."
        raise StoreActionError(reason)
    return raw, digest


def request_feedback_approval(
    job: Job, candidate_sha256: str, *, actor: AbstractBaseUser | AnonymousUser
) -> None:
    with web_run_lock(Path(settings.REPO_ROOT), job.run_id, blocking=False), transaction.atomic():
        current = owned_job(fresh_actor(actor), job.pk)
        if (
            current.workflow_id != "local-pack-feedback"
            or current.store.pk != job.store.pk
            or current.inputs != job.inputs
            or current.store.client != job.store.client
        ):
            raise Http404
        _, digest = feedback_candidate(current)
        if digest != candidate_sha256:
            reason = "확인한 피드백 버전이 달라졌습니다. 화면을 다시 확인해 주세요."
            raise StoreActionError(reason)
        approval = FeedbackApproval.model_validate_json(
            json.dumps(
                {
                    "schema_version": "aicmo.web-feedback-approval.v1",
                    "candidate_sha256": digest,
                    "reviewer": f"web-user:{actor.pk}",
                    "requested_at": timezone.now().isoformat(),
                }
            )
        ).model_dump(mode="json")
        prior = (
            FeedbackApproval.model_validate_json(json.dumps(current.approval)).model_dump(
                mode="json"
            )
            if current.approval != {}
            else {}
        )
        if current.cancel_requested:
            reason = "취소 중인 작업입니다. 화면을 새로 열어 주세요."
            raise StoreActionError(reason)
        if all(
            prior.get(key) == approval[key] for key in ("candidate_sha256", "reviewer")
        ) and current.state in ("queued", "running", "success"):
            return
        if current.state != "waiting_approval":
            reason = "현재 승인할 수 없는 작업입니다. 화면을 새로 열어 주세요."
            raise StoreActionError(reason)
        current.approval = approval
        current.state = "queued"
        current.save(update_fields=["approval", "state", "updated_at"])


def _feedback_learning_reader(job: Job) -> tuple[WorkflowRunner, str]:
    if job.workflow_id != "local-pack-feedback":
        raise Http404
    if job.state != "success" or job.cancel_requested:
        reason = "검토를 마친 피드백만 반영할 수 있습니다."
        raise StoreActionError(reason)
    runner = reader()
    _, digest = feedback_candidate(job)
    verified_delivery(runner, job.run_id, "local-pack-feedback")
    approval = FeedbackApproval.model_validate_json(json.dumps(job.approval))
    with runner.store.connect() as connection:
        applied = connection.execute(
            "select reviewer, photo_manifest_sha256 from approvals "
            "where run_id=? and step_id='owner_gate'",
            (job.run_id,),
        ).fetchone()
    if (
        approval.candidate_sha256 != digest
        or applied is None
        or applied["reviewer"] != approval.reviewer
        or applied["photo_manifest_sha256"] is not None
    ):
        reason = "확인한 피드백 승인 기록이 달라졌습니다."
        raise StoreActionError(reason)
    return runner, digest


def feedback_is_learned(job: Job) -> bool:
    runner, _ = _feedback_learning_reader(job)
    return learning.feedback_is_learned(runner, job.run_id)


def learn_web_feedback(
    job: Job, candidate_sha256: str, *, actor: AbstractBaseUser | AnonymousUser
) -> None:
    if job.workflow_id != "local-pack-feedback":
        raise Http404
    with web_run_lock(Path(settings.REPO_ROOT), job.run_id, blocking=False), transaction.atomic():
        current = owned_job(fresh_actor(actor), job.pk)
        if (
            current.store.pk != job.store.pk
            or current.inputs != job.inputs
            or current.store.client != job.store.client
        ):
            raise Http404
        runner, digest = _feedback_learning_reader(current)
        if digest != candidate_sha256:
            reason = "확인한 피드백 버전이 달라졌습니다. 화면을 다시 확인해 주세요."
            raise StoreActionError(reason)
        runner = replace(runner, store=WorkflowStore(runner.store.db_path))
        learning.learn_feedback(runner, current.run_id)


def preview(job: Job) -> tuple[LocalPack, str, str]:
    if job.workflow_id != WORKFLOW_ID:
        raise Http404
    runner = reader()
    inputs = runner.store.get_inputs(job.run_id)
    if (
        runner.store.get_run(job.run_id)["workflow_id"] != WORKFLOW_ID
        or inputs != job.inputs
        or inputs.get("client") != job.store.client
    ):
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


def request_approval(
    job: Job, pack_sha: str, photo_sha: str, actor: AbstractBaseUser | AnonymousUser
) -> None:
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
                    "reviewer": f"web-user:{actor.pk}",
                    "requested_at": timezone.now().isoformat(),
                }
            )
        ).model_dump(mode="json")
        with transaction.atomic():
            current = owned_pack_job(fresh_actor(actor), job.pk)
            if current.inputs != job.inputs or current.store.client != job.store.client:
                raise Http404
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


def request_cancel(job: Job, actor: AbstractBaseUser | AnonymousUser) -> None:
    # Cancellation intent must remain writable while the worker holds the run lock.
    with transaction.atomic():
        current = owned_job(fresh_actor(actor), job.pk)
        Job.objects.filter(
            pk=current.pk, state__in=["queued", "running", "waiting_approval"]
        ).update(cancel_requested=True)


def cancel(job: Job, runner: WorkflowRunner) -> None:  # noqa: C901 — sequential crash recovery checks
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
            inputs = TypeAdapter(dict[str, str]).validate_python(job.inputs, strict=True)
            if (
                runner.store.get_run(job.run_id)["workflow_id"] != job.workflow_id
                or runner.store.get_inputs(job.run_id) != inputs
                or inputs.get("client") != job.store.client
            ):
                reason = "stored run differs from this job"
                raise StoreActionError(reason)  # noqa: TRY301 — cancellation error boundary
            pending_edit = None
            if job.workflow_id == WORKFLOW_ID:
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
                    runner.complete_verified_delivery(job.run_id, job.workflow_id)
                state = delivery_state(runner, job.run_id, job.workflow_id)
    except (AicmoError, OSError, ValueError, sqlite3.Error, StoreActionError):
        state, notice = "failed", "취소 상태를 확인하지 못했습니다. 운영자에게 문의해 주세요."
    Job.objects.filter(pk=job.pk, cancel_requested=True).update(
        state=state, cancel_requested=False, notice=notice
    )


def _delivery_reader(job: Job) -> WorkflowRunner:
    if job.workflow_id != WORKFLOW_ID:
        raise Http404
    if job.state != "success" or job.cancel_requested:
        reason = "검토·승인을 마친 파일만 저장할 수 있습니다."
        raise StoreActionError(reason)
    runner = reader()
    inputs = runner.store.get_inputs(job.run_id)
    if (
        runner.store.get_run(job.run_id)["workflow_id"] != WORKFLOW_ID
        or inputs != job.inputs
        or inputs.get("client") != job.store.client
    ):
        raise Http404
    return runner


def verified_files(job: Job) -> tuple[str, dict[str, bytes]]:
    return verified_pack(_delivery_reader(job), job.run_id)


def download(job: Job) -> Path:
    runner = _delivery_reader(job)
    # Export takes an engine write transaction; this endpoint is POST-only.
    runner = replace(runner, store=WorkflowStore(runner.store.db_path))
    return export_local_pack(runner, job.run_id)


def _job_inputs(job: Job, runner: WorkflowRunner) -> dict[str, str]:
    inputs = TypeAdapter(dict[str, str]).validate_python(job.inputs, strict=True)
    if inputs.get("client") != job.store.client:
        reason = "invalid stored job inputs"
        raise StoreActionError(reason)
    required = {
        WORKFLOW_ID: {"client", "brief_json"},
        "weekly-report": {"client", "week_start", "channel", "outcomes_snapshot_json"},
        "local-pack-feedback": {"client", "feedback_json"},
    }.get(job.workflow_id)
    optional: set[str] = (
        {"photos_json", "rewrite_json"} if job.workflow_id == WORKFLOW_ID else set()
    )
    if required is None or not required <= inputs.keys() <= required | optional:
        reason = "invalid stored job workflow or input fields"
        raise StoreActionError(reason)
    spec = load_workflow_spec(runner.repo_root, job.workflow_id)
    if prepare_workflow_inputs(spec.inputs, inputs).values != inputs:
        reason = "stored job privacy policy changed"
        raise StoreActionError(reason)
    if job.workflow_id == WORKFLOW_ID:
        parse_brief(inputs)
        photos = parse_photos(inputs).photos
        if photos and (len(photos) != 1 or photos[0].news_index != 0):
            reason = "invalid stored photo selection"
            raise StoreActionError(reason)
        verify_photo_assets(runner.repo_root, inputs)
    elif job.workflow_id == "weekly-report":
        snapshot = parse_outcomes_snapshot(inputs["outcomes_snapshot_json"])
        if (snapshot.client, snapshot.week_start, snapshot.channel) != (
            inputs["client"],
            inputs["week_start"],
            inputs["channel"],
        ):
            reason = "stored report snapshot scope changed"
            raise StoreActionError(reason)
    elif parse_feedback(inputs["feedback_json"]).model_dump_json() != inputs["feedback_json"]:
        reason = "stored feedback inputs changed"
        raise StoreActionError(reason)
    return inputs


def _job_approval(job: Job) -> ApprovalRequest | EditApproval | FeedbackApproval | None:
    if job.approval == {}:
        return None
    if job.workflow_id == WORKFLOW_ID:
        return TypeAdapter[ApprovalRequest | EditApproval](
            ApprovalRequest | EditApproval
        ).validate_json(json.dumps(job.approval))
    if job.workflow_id == "local-pack-feedback":
        return FeedbackApproval.model_validate_json(json.dumps(job.approval))
    reason = "this workflow does not accept owner approval"
    raise StoreActionError(reason)


def _apply_feedback_approval(job: Job, runner: WorkflowRunner, approval: FeedbackApproval) -> None:
    _, digest = feedback_candidate(job)
    if digest != approval.candidate_sha256:
        reason = "confirmed feedback candidate changed"
        raise StoreActionError(reason)
    if runner.store.approval_for(job.run_id, "owner_gate") is None:
        runner.approve(job.run_id, "owner_gate", approval.reviewer, "웹에서 문안 피드백 확인")
    elif runner.store.approval_for(job.run_id, "owner_gate") != ApprovalDecision.APPROVED:
        reason = "feedback owner approval could not be verified"
        raise StoreActionError(reason)
    with runner.store.connect() as connection:
        applied = connection.execute(
            "select reviewer, photo_manifest_sha256 from approvals "
            "where run_id=? and step_id='owner_gate'",
            (job.run_id,),
        ).fetchone()
    if (
        applied is None
        or applied["reviewer"] != approval.reviewer
        or applied["photo_manifest_sha256"] is not None
    ):
        reason = "engine approval belongs to another feedback request"
        raise StoreActionError(reason)


def _apply_approval(
    job: Job, runner: WorkflowRunner, approval: ApprovalRequest | EditApproval | FeedbackApproval
) -> None:
    if isinstance(approval, FeedbackApproval):
        _apply_feedback_approval(job, runner, approval)
        return
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
        runner.approve(
            job.run_id,
            "owner_gate",
            approval.reviewer,
            "웹에서 문안·사진 확인",
            photos_reviewed=True,
        )
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
        approval = _job_approval(job)
        runner.store.initialize()
        try:
            existing = runner.store.get_run(job.run_id)
        except RunNotFoundError:
            existing = None
        if existing is not None and (
            existing["workflow_id"] != job.workflow_id
            or runner.store.get_inputs(job.run_id) != inputs
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
            runner.run(job.workflow_id, job.run_id, inputs)
            if existing is None
            else runner.resume(job.run_id)
        )
        state = (
            delivery_state(runner, job.run_id, job.workflow_id)
            if result.status == "success"
            else result.status
        )
        notice = "" if state not in ("failed", "needs_work") else "운영자 검토가 필요합니다."
    except (AicmoError, OSError, ValueError, sqlite3.Error, StoreActionError):
        state, notice = "failed", "작업을 완료하지 못했습니다. 운영자에게 문의해 주세요."
    job.refresh_from_db()
    if job.cancel_requested:
        cancel(job, runner)
    else:
        Job.objects.filter(pk=job.pk, cancel_requested=False).update(state=state, notice=notice)


def delivery_state(runner: WorkflowRunner, run_id: str, workflow_id: str = WORKFLOW_ID) -> str:
    if workflow_id not in (WORKFLOW_ID, "weekly-report", "local-pack-feedback"):
        reason = "unsupported job workflow"
        raise StoreActionError(reason)
    _, contents = verified_delivery(runner, run_id, workflow_id, require_deliverable=False)
    manifest = json.loads(contents[f"artifacts/{run_id}/delivery-review.json"])
    return "success" if manifest["deliverable"] else "needs_work"
