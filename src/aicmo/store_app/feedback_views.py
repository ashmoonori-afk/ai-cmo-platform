from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date
from typing import TYPE_CHECKING, cast

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import DatabaseError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from aicmo.errors import AicmoError
from aicmo.learning import PackFeedback
from aicmo.redaction import safe_kb_text
from aicmo.source_input import source_checked_date
from aicmo.store_app import feedback_services, outcome_views, services

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

INPUT_ERROR = "입력 항목을 다시 확인해 주세요."
_ERRORS = (
    AicmoError,
    OSError,
    ValueError,
    KeyError,
    sqlite3.Error,
    DatabaseError,
    services.StoreActionError,
)


class SummaryField(forms.CharField):
    def __init__(self, label: str) -> None:
        super().__init__(label=label, max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self, value: object) -> str:
        text = super().clean(value)
        try:
            return safe_kb_text(text)
        except AicmoError:
            reason = "고객 개인정보·비밀 정보 없이 500자 이내로 입력해 주세요."
            raise forms.ValidationError(reason) from None


class FeedbackForm(forms.Form):
    token = forms.CharField(max_length=feedback_services.MAX_TOKEN_LENGTH, widget=forms.HiddenInput)
    observed_on = forms.DateField(
        label="이 문안을 확인한 날짜 (한국 시간)",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    adoption = forms.ChoiceField(
        label="이 문안을 사용했나요?",
        choices=[
            ("not_recorded", "아직 기록하지 않음"),
            ("used", "사용했다고 직접 보고"),
            ("not_used", "사용하지 않음"),
        ],
        error_messages={"invalid_choice": INPUT_ERROR},
    )
    reason = SummaryField("사용·수정 여부의 이유")
    insight = SummaryField("다음 문안에 참고할 제안")
    weekly_report = forms.ChoiceField(
        label="함께 확인할 네이버 주간 보고서 (선택)",
        required=False,
        error_messages={"invalid_choice": INPUT_ERROR},
    )
    checked = forms.BooleanField(label="실제 사용 여부와 입력한 이유·제안을 직접 확인했습니다.")

    def clean_observed_on(self) -> date:
        observed = cast("date", self.cleaned_data["observed_on"])
        if observed > source_checked_date():
            reason = "한국 시간 오늘까지 실제로 확인한 날짜를 입력해 주세요."
            raise forms.ValidationError(reason)
        return observed


class CandidateForm(forms.Form):
    candidate_sha256 = forms.RegexField(
        r"^[a-f0-9]{64}$",
        max_length=64,
        widget=forms.HiddenInput,
        error_messages={"invalid": INPUT_ERROR},
    )
    checked = forms.BooleanField(label="원본·승인 문안과 이유·제안·연결한 근거를 확인했습니다.")


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def create(request: HttpRequest, job_id: uuid.UUID, item_key: str) -> HttpResponse:
    job = services.owned_pack_job(request.user, job_id)
    if request.method == "POST" and (
        set(request.POST) - set(FeedbackForm.base_fields) - {"csrfmiddlewaretoken"}
        or any(len(request.POST.getlist(key)) != 1 for key in request.POST)
        or request.FILES
    ):
        return render(
            request, "store_app/error.html", {"job": job, "notice": INPUT_ERROR}, status=400
        )
    try:
        if request.method == "POST":
            envelope = feedback_services.decode(
                request.user, job, item_key, request.POST.get("token", "")
            )
            approved = feedback_services.source(job, item_key)
            token = request.POST.get("token", "")
        else:
            approved, envelope, token = feedback_services.prepare(request.user, job, item_key)
    except (*_ERRORS, signing.BadSignature):
        return render(
            request,
            "store_app/error.html",
            {
                "job": job,
                "notice": (
                    "확인한 문안이나 보고서가 달라졌거나 확인 시간이 지났습니다. "
                    "화면을 다시 열어 주세요."
                ),
            },
            status=409,
        )
    form = FeedbackForm(
        request.POST if request.method == "POST" else None,
        initial={"token": token, "observed_on": source_checked_date(), "adoption": "not_recorded"},
    )
    cast("forms.ChoiceField", form.fields["weekly_report"]).choices = [
        ("", "보고서 연결 안 함")
    ] + [(item.job_id, f"{item.week_start} 주 · 네이버") for item in envelope.reports]
    form.fields["observed_on"].widget.attrs.update(
        min=approved.created_on.isoformat(), max=source_checked_date().isoformat()
    )
    notice = ""
    status = 200
    if request.method == "POST":
        outcome_views.submitted(form, request.POST, request.FILES)
        if form.is_valid():
            try:
                data = form.cleaned_data
                feedback = PackFeedback(
                    schema_version="aicmo.pack-feedback.v1",
                    source_run_id=job.run_id,
                    item=f"{item_key}.txt",
                    observed_on=cast("date", data["observed_on"]).isoformat(),
                    adoption=data["adoption"],
                    reason=data["reason"],
                    insight=data["insight"],
                    weekly_report_run_id=f"web-{uuid.UUID(data['weekly_report']).hex}"
                    if data["weekly_report"]
                    else None,
                )
                requested = feedback_services.submit(request.user, job, item_key, token, feedback)
            except (*_ERRORS, signing.BadSignature):
                notice = (
                    "접수하지 못했습니다. 승인 문안과 연결한 보고서의 기간·채널, "
                    "진행 중인 작업을 확인해 주세요. "
                    "전체 근거가 6,000자를 넘으면 줄여 검토할 수 없으므로 운영자에게 문의해 주세요."
                )
                status = 409
            else:
                return redirect("feedback", job_id=requested.id)
        else:
            status = 400
    return render(
        request,
        "store_app/feedback_form.html",
        {"job": job, "item_key": item_key, "source": approved, "form": form, "notice": notice},
        status=status,
    )


@login_required
@require_GET
@never_cache
def detail(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    if job.workflow_id != "local-pack-feedback":
        raise Http404
    candidate, digest, form = None, "", None
    learned, notice, status = False, str(job.notice), 200
    if job.state in ("waiting_approval", "success", "needs_work"):
        try:
            raw, digest = feedback_services.verified_candidate(job)
            candidate = json.loads(raw)
            form = CandidateForm(initial={"candidate_sha256": digest})
            if job.state == "success":
                learned = services.feedback_is_learned(job)
        except _ERRORS:
            candidate, form = None, None
            notice = "피드백 근거를 확인할 수 없습니다. 최신 작업 상태를 확인해 주세요."
            status = 409
    return render(
        request,
        "store_app/feedback.html",
        {
            "job": job,
            "candidate": candidate,
            "candidate_sha256": digest,
            "form": form,
            "learned": learned,
            "notice": notice,
        },
        status=status,
    )


@login_required
@require_POST
@never_cache
def approve(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    if job.workflow_id != "local-pack-feedback":
        raise Http404
    form = outcome_views.submitted(CandidateForm(request.POST), request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request, "store_app/error.html", {"job": job, "notice": INPUT_ERROR}, status=400
        )
    try:
        services.request_feedback_approval(
            job, str(form.cleaned_data["candidate_sha256"]), actor=request.user
        )
    except _ERRORS:
        return render(
            request,
            "store_app/error.html",
            {"job": job, "notice": "확인한 피드백이 달라졌습니다. 화면을 다시 확인해 주세요."},
            status=409,
        )
    return redirect("feedback", job_id=job.id)


@login_required
@require_POST
@never_cache
def learn(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    if job.workflow_id != "local-pack-feedback":
        raise Http404
    form = outcome_views.submitted(CandidateForm(request.POST), request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request, "store_app/error.html", {"job": job, "notice": INPUT_ERROR}, status=400
        )
    try:
        services.learn_web_feedback(
            job, str(form.cleaned_data["candidate_sha256"]), actor=request.user
        )
    except _ERRORS:
        return render(
            request,
            "store_app/error.html",
            {
                "job": job,
                "notice": (
                    "반영 결과를 확인하지 못했습니다. "
                    "같은 피드백 화면에서 다시 확인해 주세요."
                ),
            },
            status=409,
        )
    messages.success(request, "확인한 피드백을 다음 문안에 참고하도록 반영했습니다.")
    return redirect("feedback", job_id=job.id)
