"""Web confirmation for real approved copy and its optional reviewed outcomes."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import Http404
from pydantic import BaseModel, ConfigDict, Field

from aicmo.errors import AicmoError
from aicmo.export import verified_delivery
from aicmo.learning import PackFeedback
from aicmo.source_input import source_checked_date
from aicmo.store_app import report_services, services
from aicmo.store_app.models import Job
from aicmo.web_run_lock import web_run_lock

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

TOKEN_SALT = "aicmo.web-feedback-source.v1"
TOKEN_MAX_AGE = 15 * 60
MAX_TOKEN_LENGTH = 8192
type Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
type UUIDText = Annotated[str, Field(pattern=r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$")]


class ReportReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    job_id: UUIDText
    week_start: str = Field(pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
    sha256: Digest


class SourceConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    client: str = Field(min_length=1, max_length=128)
    source_job_id: UUIDText
    item_key: str = Field(pattern=r"^(news-[12]|reply-[1-5])$")
    bundle_sha256: Digest
    file_sha256: Digest
    request_key: UUIDText
    reports: list[ReportReference] = Field(max_length=20)


@dataclass(frozen=True)
class ApprovedSource:
    text: str
    bundle_sha256: str
    file_sha256: str
    created_on: date


def source(job: Job, item_key: str) -> ApprovedSource:
    if not re.fullmatch(r"(news-[12]|reply-[1-5])", item_key):
        raise Http404
    bundle_sha, files = services.verified_files(job)
    raw = files.get(f"{item_key}.txt")
    if raw is None:
        raise Http404
    created = datetime.fromisoformat(str(services.reader().store.get_run(job.run_id)["created_at"]))
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return ApprovedSource(
        raw.decode("utf-8"),
        bundle_sha,
        hashlib.sha256(raw).hexdigest(),
        source_checked_date(created),
    )


def prepare(
    actor: AbstractBaseUser | AnonymousUser, job: Job, item_key: str
) -> tuple[ApprovedSource, SourceConfirmation, str]:
    approved = source(job, item_key)
    actor_id = actor.pk
    if type(actor_id) is not int or actor_id <= 0:
        raise Http404
    reports: list[ReportReference] = []
    # ponytail: inspect at most 20 recent reports; add explicit period search when needed.
    candidates = Job.objects.filter(
        store=job.store, workflow_id="weekly-report", state="success", cancel_requested=False
    ).order_by("-created_at")[:20]
    for report_job in candidates:
        try:
            report = report_services.verify(report_job)
        except (
            AicmoError,
            OSError,
            ValueError,
            KeyError,
            sqlite3.Error,
            services.StoreActionError,
        ):
            continue
        if report.source.channel == "naver":
            reports.append(
                ReportReference(
                    job_id=str(report_job.pk),
                    week_start=report.source.week_start,
                    sha256=report.sha256,
                )
            )
    envelope = SourceConfirmation(
        actor_id=actor_id,
        store_id=job.store.pk,
        client=job.store.client,
        source_job_id=str(job.pk),
        item_key=item_key,
        bundle_sha256=approved.bundle_sha256,
        file_sha256=approved.file_sha256,
        request_key=str(uuid.uuid4()),
        reports=reports,
    )
    token = signing.dumps(envelope.model_dump(), salt=TOKEN_SALT)
    if len(token) > MAX_TOKEN_LENGTH:
        reason = "Too many report references"
        raise services.StoreActionError(reason)
    return approved, envelope, token


def decode(
    actor: AbstractBaseUser | AnonymousUser, job: Job, item_key: str, token: str
) -> SourceConfirmation:
    if len(token) > MAX_TOKEN_LENGTH:
        raise signing.BadSignature
    envelope = SourceConfirmation.model_validate(
        signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    )
    if (
        envelope.actor_id != actor.pk
        or envelope.store_id != job.store.pk
        or envelope.client != job.store.client
        or envelope.source_job_id != str(job.pk)
        or envelope.item_key != item_key
    ):
        raise Http404
    return envelope


def submit(
    actor: AbstractBaseUser | AnonymousUser,
    job: Job,
    item_key: str,
    token: str,
    feedback: PackFeedback,
) -> Job:
    envelope = decode(actor, job, item_key, token)
    with web_run_lock(Path(settings.REPO_ROOT), job.run_id, blocking=False), transaction.atomic():
        current_actor = services.fresh_actor(actor)
        current = services.owned_pack_job(current_actor, job.pk)
        if (
            current.store.pk != envelope.store_id
            or current.inputs != job.inputs
            or current.store.client != envelope.client
        ):
            raise Http404
        approved = source(current, item_key)
        if (
            approved.bundle_sha256 != envelope.bundle_sha256
            or approved.file_sha256 != envelope.file_sha256
            or feedback.source_run_id != current.run_id
            or feedback.item != f"{item_key}.txt"
        ):
            reason = "Confirmed source changed"
            raise services.StoreActionError(reason)
        if feedback.weekly_report_run_id:
            reference = next(
                (
                    item
                    for item in envelope.reports
                    if f"web-{uuid.UUID(item.job_id).hex}" == feedback.weekly_report_run_id
                ),
                None,
            )
            if reference is None:
                raise Http404
            report_job = services.owned_job(current_actor, uuid.UUID(reference.job_id))
            if report_job.store.pk != current.store.pk:
                raise Http404
            report = report_services.verify(report_job)
            if report.sha256 != reference.sha256:
                reason = "Confirmed report changed"
                raise services.StoreActionError(reason)
        return services.submit_feedback(
            current.store, uuid.UUID(envelope.request_key), feedback, actor=current_actor
        )


def verified_candidate(job: Job) -> tuple[bytes, str]:
    if job.workflow_id != "local-pack-feedback" or job.cancel_requested:
        raise Http404
    raw, digest = services.feedback_candidate(job)
    if job.state == "success":
        _, files = verified_delivery(services.reader(), job.run_id, "local-pack-feedback")
        if files[f"artifacts/{job.run_id}/feedback.json"] != raw:
            reason = "Reviewed candidate changed"
            raise services.StoreActionError(reason)
    return raw, digest
