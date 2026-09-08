from __future__ import annotations

import io
import sqlite3
import uuid
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import DatabaseError
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from aicmo.errors import AicmoError
from aicmo.store_app import action_services, guidance, outcome_views, report_services, services

if TYPE_CHECKING:
    from typing import Literal

    from django.http import HttpRequest, HttpResponse


class ActionForm(forms.Form):
    token = forms.CharField(max_length=report_services.MAX_TOKEN_LENGTH, widget=forms.HiddenInput)
    decision = forms.ChoiceField(
        choices=[("selected", "선택"), ("declined", "이번에는 하지 않음")],
        error_messages={"invalid_choice": "선택 방법을 다시 확인해 주세요."},
    )
    reason = forms.CharField(
        label="이유 (선택)",
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_reason(self) -> str:
        try:
            return action_services.clean_reason(str(self.cleaned_data.get("reason", "")))
        except (AicmoError, ValueError, services.StoreActionError):
            reason = "고객 개인정보·비밀 정보 없이 500자 이내로 입력해 주세요."
            raise forms.ValidationError(reason) from None


@login_required
@require_POST
@never_cache
def request_report(request: HttpRequest, store_id: int) -> HttpResponse:
    store = services.owned_store(request.user, store_id)
    form = outcome_views.submitted(
        report_services.ReportForm(request.POST), request.POST, request.FILES
    )
    if not form.is_valid():
        return render(
            request,
            "store_app/report_request.html",
            {"store": store, "notice": "기간·채널과 숫자를 다시 확인한 뒤 요청해 주세요."},
            status=400,
        )
    try:
        envelope = report_services.decode(request.user, store, str(form.cleaned_data["token"]))
    except (signing.BadSignature, ValueError):
        return render(
            request,
            "store_app/report_request.html",
            {
                "store": store,
                "notice": "확인 시간이 지났거나 내용이 달라졌습니다. 숫자를 다시 확인해 주세요.",
            },
            status=409,
        )
    try:
        job = services.submit_weekly_report(
            store,
            uuid.UUID(envelope.request_key),
            envelope.week_start,
            envelope.channel,
            envelope.snapshot_sha256,
            actor=request.user,
        )
    except (
        AicmoError,
        OSError,
        ValueError,
        sqlite3.Error,
        DatabaseError,
        services.StoreActionError,
    ):
        active = None
        # Preserve a same-request retry even while the web DB remains unavailable.
        with suppress(DatabaseError):
            active = guidance.active_job(store)
        return render(
            request,
            "store_app/report_request.html",
            {
                "store": store,
                "form": form,
                "active": active,
                "week_start": envelope.week_start,
                "channel": envelope.channel,
                "notice": (
                    "접수 결과를 확인하지 못했습니다. 진행 중인 작업을 확인하거나 "
                    "같은 요청을 다시 보내 주세요. "
                    "숫자를 정정했다면 최신 기록을 다시 확인해 주세요."
                ),
            },
            status=409,
        )
    return redirect("report", job_id=job.id)


@login_required
@require_GET
@never_cache
def detail(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    if job.workflow_id != "weekly-report":
        raise Http404
    report = None
    notice = str(job.notice)
    status = 200
    if job.state == "success":
        try:
            report = report_services.verify(job)
        except (
            AicmoError,
            OSError,
            ValueError,
            KeyError,
            sqlite3.Error,
            services.StoreActionError,
        ):
            notice = (
                "검토한 보고서를 확인할 수 없습니다. "
                "최신 작업 상태를 확인하거나 운영자에게 문의해 주세요."
            )
            status = 409
    actions = (
        [
            {
                "card": card,
                "form": ActionForm(
                    initial={
                        "token": report_services.action_token(request.user, job, report, card.code)
                    },
                    auto_id=f"action-{card.code}-%s",
                ),
            }
            for card in action_services.cards(report)
        ]
        if report is not None
        else []
    )
    return render(
        request,
        "store_app/report.html",
        {
            "job": job,
            "report": report,
            "notice": notice,
            "actions": actions,
            "totals": [
                {
                    "key": key,
                    "label": outcome_views.METRIC_LABELS[key],
                    "metric": metric,
                    "change": (
                        f"{metric.change_percent:+.1f}%"
                        if metric.change_percent is not None
                        else "비교 불가"
                    ),
                }
                for key, metric in report.source.totals.items()
            ]
            if report is not None
            else [],
        },
        status=status,
    )


@login_required
@require_POST
@never_cache
def download(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse | FileResponse:
    job = services.owned_job(request.user, job_id)
    if job.workflow_id != "weekly-report":
        raise Http404
    try:
        report = report_services.verify(job)
    except (AicmoError, OSError, ValueError, KeyError, sqlite3.Error, services.StoreActionError):
        return render(
            request,
            "store_app/error.html",
            {
                "job": job,
                "notice": (
                    "검토가 완료된 보고서를 확인할 수 없습니다. 최신 작업 상태를 확인해 주세요."
                ),
            },
            status=409,
        )
    return FileResponse(
        io.BytesIO(report.raw),
        as_attachment=True,
        filename=f"주간-성과보고-{report.source.week_start}.md",
        content_type="text/markdown; charset=utf-8",
    )


@login_required
@require_POST
@never_cache
def action(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    if job.workflow_id != "weekly-report":
        raise Http404
    form = outcome_views.submitted(ActionForm(request.POST), request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "store_app/error.html",
            {"job": job, "notice": "선택과 이유를 다시 확인해 주세요. 비밀 정보는 넣지 마세요."},
            status=400,
        )
    try:
        data = form.cleaned_data
        envelope = report_services.decode_action(request.user, job, str(data["token"]))
        report = report_services.verify(job)
        selected = next(
            (card for card in action_services.cards(report) if card.code == envelope.action_code),
            None,
        )
        if selected is None:
            raise Http404
        decision = cast("Literal['selected', 'declined']", data["decision"])
        action_services.record_action(
            job,
            selected.code,
            decision,
            str(data["reason"]),
            uuid.UUID(envelope.request_key),
            envelope.report_sha256,
            envelope.snapshot_sha256,
            actor=request.user,
        )
    except (
        AicmoError,
        OSError,
        ValueError,
        KeyError,
        sqlite3.Error,
        DatabaseError,
        services.StoreActionError,
        signing.BadSignature,
    ):
        return render(
            request,
            "store_app/error.html",
            {
                "job": job,
                "notice": "선택 결과를 확인하지 못했습니다. 보고서를 다시 열어 확인해 주세요.",
            },
            status=409,
        )
    if decision == "declined":
        messages.info(
            request, "이번에는 하지 않기로 기록했습니다. 성과나 문안 학습에 반영하지 않습니다."
        )
        return redirect("report", job_id=job.id)
    messages.info(request, "다음 행동으로 선택했습니다. 실제 실행이나 성과를 기록한 것은 아닙니다.")
    if selected.target == "outcomes":
        return redirect(
            f"{reverse('outcomes', args=[job.store.pk])}"
            f"?week_start={report.source.week_start}&channel={report.source.channel}"
        )
    if selected.target == "archive":
        return redirect(f"{reverse('archive')}?store={job.store.pk}")
    return redirect(f"{reverse('create', args=[job.store.pk])}?intent=news")
