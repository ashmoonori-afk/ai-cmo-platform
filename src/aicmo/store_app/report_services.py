"""Confirm a server ledger snapshot and read the exact reviewed report."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from django import forms
from django.core import signing
from django.http import Http404
from pydantic import BaseModel, ConfigDict, Field

from aicmo import outcomes
from aicmo.errors import AicmoError
from aicmo.export import verified_delivery
from aicmo.store_app import outcome_services, services
from aicmo.store_app.models import Job, Store

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

TOKEN_SALT = "aicmo.outcomes.report.v1"
TOKEN_MAX_AGE = 15 * 60
MAX_TOKEN_LENGTH = 2048


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    client: str = Field(min_length=1, max_length=128)
    week_start: str = Field(pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
    channel: outcomes.Channel
    snapshot_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    request_key: str = Field(pattern=r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$")


class ReportForm(forms.Form):
    token = forms.CharField(max_length=MAX_TOKEN_LENGTH, widget=forms.HiddenInput)
    checked = forms.BooleanField(
        label="위 기간·채널의 이번 주와 지난주 숫자, 미입력을 확인했습니다."
    )


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor_id: int = Field(gt=0)
    job_id: str = Field(pattern=r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$")
    action_code: str = Field(pattern=r"^[a-z][a-z_]{0,39}$")
    request_key: str = Field(pattern=r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$")
    report_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    snapshot_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


ACTION_SALT = "aicmo.outcomes.action.v1"


def action_token(
    actor: AbstractBaseUser | AnonymousUser,
    job: Job,
    report: ReviewedReport,
    action_code: str,
) -> str:
    actor_id = actor.pk
    if type(actor_id) is not int or actor_id <= 0:
        raise Http404
    envelope = ActionRequest(
        actor_id=actor_id,
        job_id=str(job.pk),
        action_code=action_code,
        request_key=str(uuid.uuid4()),
        report_sha256=report.sha256,
        snapshot_sha256=report.source.snapshot_sha256,
    )
    return signing.dumps(envelope.model_dump(), salt=ACTION_SALT)


def decode_action(actor: AbstractBaseUser | AnonymousUser, job: Job, token: str) -> ActionRequest:
    if len(token) > MAX_TOKEN_LENGTH:
        raise signing.BadSignature
    envelope = ActionRequest.model_validate(
        signing.loads(token, salt=ACTION_SALT, max_age=TOKEN_MAX_AGE)
    )
    if envelope.actor_id != actor.pk or envelope.job_id != str(job.pk):
        raise Http404
    return envelope


def form_for(
    actor: AbstractBaseUser | AnonymousUser, store: Store, snapshot: outcomes.OutcomeSnapshot
) -> ReportForm:
    actor_id = actor.pk
    if type(actor_id) is not int or actor_id <= 0 or snapshot.client != store.client:
        raise Http404
    envelope = ReportRequest(
        actor_id=actor_id,
        store_id=store.pk,
        client=store.client,
        week_start=snapshot.week_start,
        channel=snapshot.channel,
        snapshot_sha256=snapshot.snapshot_sha256,
        request_key=str(uuid.uuid4()),
    )
    return ReportForm(initial={"token": signing.dumps(envelope.model_dump(), salt=TOKEN_SALT)})


def decode(actor: AbstractBaseUser | AnonymousUser, store: Store, token: str) -> ReportRequest:
    if len(token) > MAX_TOKEN_LENGTH:
        raise signing.BadSignature
    envelope = ReportRequest.model_validate(
        signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    )
    if (
        envelope.actor_id != actor.pk
        or envelope.store_id != store.pk
        or envelope.client != store.client
    ):
        raise Http404
    return envelope


@dataclass(frozen=True)
class ReviewedReport:
    raw: bytes
    text: str
    sha256: str
    source: outcomes.OutcomeSnapshot
    current: bool | None


def verify(job: Job) -> ReviewedReport:
    if job.workflow_id != "weekly-report":
        raise Http404
    if job.state != "success" or job.cancel_requested:
        reason = "A completed report is required"
        raise services.StoreActionError(reason)
    runner = services.reader()
    if job.inputs != runner.store.get_inputs(job.run_id) or job.store.client != job.inputs.get(
        "client"
    ):
        reason = "Report source differs from this job"
        raise services.StoreActionError(reason)
    inputs, contents = verified_delivery(runner, job.run_id, "weekly-report")
    source = outcomes.OutcomeSnapshot.model_validate_json(inputs["outcomes_snapshot_json"])
    if (
        source.client != job.store.client
        or source.week_start != inputs["week_start"]
        or source.channel != inputs["channel"]
    ):
        reason = "Report scope differs from this job"
        raise services.StoreActionError(reason)
    raw = contents[f"artifacts/{job.run_id}/weekly-report.md"]
    current = None
    try:
        latest = outcome_services.read(job.store, source.week_start, source.channel)
        current = latest.snapshot_sha256 == source.snapshot_sha256
    except (AicmoError, OSError, ValueError, sqlite3.Error):
        pass  # The verified report remains readable when today's ledger is unavailable.
    return ReviewedReport(
        raw, raw.decode("utf-8"), hashlib.sha256(raw).hexdigest(), source, current
    )
