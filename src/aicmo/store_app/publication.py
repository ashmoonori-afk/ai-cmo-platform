from __future__ import annotations

# Validation failures below share a safe, non-reflecting error response.
# ruff: noqa: TRY301
import sqlite3
import uuid
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import DatabaseError, transaction
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from aicmo.errors import AicmoError
from aicmo.store_app import services
from aicmo.store_app.models import Job, PublicationReport
from aicmo.web_run_lock import web_run_lock

KST = ZoneInfo("Asia/Seoul")
HISTORY_LIMIT = 20


class ReportForm(forms.Form):
    bundle_sha = forms.RegexField(r"^[a-f0-9]{64}$", max_length=64, widget=forms.HiddenInput)
    file_sha = forms.RegexField(r"^[a-f0-9]{64}$", max_length=64, widget=forms.HiddenInput)
    expected_revision = forms.IntegerField(
        min_value=0, max_value=2**63 - 2, widget=forms.HiddenInput
    )
    request_key = forms.UUIDField(widget=forms.HiddenInput)
    action = forms.ChoiceField(choices=[("report", "게시 날짜 기록"), ("cancel", "보고 취소")])
    posted_on = forms.DateField(
        label="직접 게시한 날짜 (한국 시간)",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )


def submitted(data: QueryDict) -> ReportForm:
    """Never bind unvalidated values into an HTML error response."""
    safe: dict[str, object] = {}
    invalid = set(data) - set(ReportForm.base_fields) - {"csrfmiddlewaretoken"}
    limits = {
        "bundle_sha": 64,
        "file_sha": 64,
        "expected_revision": 19,
        "request_key": 36,
        "action": 6,
        "posted_on": 10,
    }
    for name, field in ReportForm.base_fields.items():
        raw = data.get(name, "")
        try:
            if len(data.getlist(name)) > 1 or len(raw) > limits[name]:
                reason = "입력 항목을 다시 확인해 주세요."
                raise forms.ValidationError(reason)
            safe[name] = field.clean(raw)
        except forms.ValidationError:
            safe[name] = ""
            invalid.add(name)
    form = ReportForm(safe)
    form.is_valid()
    if invalid or len(data.getlist("csrfmiddlewaretoken")) > 1:
        form.add_error(None, "입력 항목을 다시 확인해 주세요.")
    if (
        form.is_valid()
        and form.cleaned_data["action"] == "report"
        and not form.cleaned_data["posted_on"]
    ):
        form.add_error("posted_on", "실제로 게시한 날짜를 입력해 주세요.")
    if (
        form.is_valid()
        and form.cleaned_data["action"] == "cancel"
        and form.cleaned_data["posted_on"]
    ):
        form.add_error("posted_on", "오기록 취소에는 게시 날짜를 입력하지 않습니다.")
    return form


def context(job: Job, bundle_sha: str, card_key: str, file_sha: str) -> dict[str, object]:
    history = list(
        PublicationReport.objects.filter(
            job=job, bundle_sha256=bundle_sha, item_key=card_key
        ).order_by("-revision")[: HISTORY_LIMIT + 1]
    )
    latest = history[0] if history else None
    form = ReportForm(
        initial={
            "bundle_sha": bundle_sha,
            "file_sha": file_sha,
            "expected_revision": latest.revision if latest else 0,
            "request_key": uuid.uuid4(),
            "posted_on": latest.posted_on
            if latest and latest.posted_on
            else timezone.localdate(timezone=KST),
        },
        auto_id=f"id_{card_key}_%s",
    )
    form.fields["posted_on"].widget.attrs.update(
        min=timezone.localdate(job.created_at, KST).isoformat(),
        max=timezone.localdate(timezone=KST).isoformat(),
    )
    return {
        "form": form,
        "latest": latest,
        "history": history[:HISTORY_LIMIT],
        "history_more": len(history) > HISTORY_LIMIT,
    }


@login_required
@require_POST
@never_cache
def record(request: HttpRequest, job_id: uuid.UUID, item_key: str) -> HttpResponse:  # noqa: C901 — atomic report/replay boundary
    job = services.owned_pack_job(request.user, job_id)
    form = submitted(request.POST)
    if request.FILES:
        form.add_error(None, "파일 없이 게시 날짜만 입력해 주세요.")
    status = 400
    if form.is_valid():
        try:
            # Import here because the delivery view also uses publication.context.
            from aicmo.store_app import delivery  # noqa: PLC0415 — delivery uses context above

            with web_run_lock(settings.REPO_ROOT, job.run_id, blocking=False), transaction.atomic():
                # Re-read authority after locking; has_perm caches grants on the request user.
                actor = User.objects.filter(pk=request.user.pk, is_active=True).first()
                if actor is None:
                    raise Http404
                job = services.owned_pack_job(actor, job_id)
                snapshot = delivery.snapshot(job)
                card = next((card for card in snapshot.cards if card.key == item_key), None)
                data = form.cleaned_data
                if (
                    card is None
                    or snapshot.bundle_sha != data["bundle_sha"]
                    or card.file_sha != data["file_sha"]
                ):
                    reason = "Delivery changed"
                    raise ValueError(reason)
                posted_on = data["posted_on"] if data["action"] == "report" else None
                if posted_on is not None and not timezone.localdate(
                    job.created_at, KST
                ) <= posted_on <= timezone.localdate(timezone=KST):
                    reason = "Date outside job lifetime"
                    raise ValueError(reason)
                prior = PublicationReport.objects.filter(request_key=data["request_key"]).first()
                if prior is not None:
                    if (
                        prior.job_id != job.pk
                        or prior.bundle_sha256 != snapshot.bundle_sha
                        or prior.item_key != card.key
                        or prior.file_sha256 != card.file_sha
                        or prior.recorded_by_id != request.user.pk
                        or prior.revision != data["expected_revision"] + 1
                        or prior.posted_on != posted_on
                    ):
                        reason = "Conflicting request key"
                        raise ValueError(reason)
                else:
                    latest = (
                        PublicationReport.objects.filter(
                            job=job, bundle_sha256=snapshot.bundle_sha, item_key=card.key
                        )
                        .order_by("-revision")
                        .first()
                    )
                    if (latest.revision if latest else 0) != data["expected_revision"]:
                        reason = "Stale revision"
                        raise ValueError(reason)
                    if posted_on is None and (latest is None or latest.posted_on is None):
                        reason = "No current report to cancel"
                        raise ValueError(reason)
                    PublicationReport.objects.create(
                        job=job,
                        bundle_sha256=snapshot.bundle_sha,
                        item_key=card.key,
                        file_sha256=card.file_sha,
                        revision=data["expected_revision"] + 1,
                        posted_on=posted_on,
                        recorded_by_id=request.user.pk,
                        request_key=data["request_key"],
                    )
            messages.success(
                request, "사용자 보고를 저장했습니다. 외부 게시 여부를 검증한 기록은 아닙니다."
            )
            return redirect("delivery", job_id=job.pk)
        except (
            AicmoError,
            OSError,
            ValueError,
            sqlite3.Error,
            DatabaseError,
            services.StoreActionError,
        ):
            status = 409
    return render(
        request,
        "store_app/error.html",
        {
            "job": job,
            "notice": (
                "보고를 저장하지 못했습니다. 기존 이력은 그대로 남아 있습니다. "
                "승인된 결과 화면을 다시 열고 게시 날짜와 최신 기록을 확인해 주세요."
            ),
        },
        status=status,
    )
