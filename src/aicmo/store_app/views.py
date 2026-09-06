from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from aicmo.errors import AicmoError
from aicmo.store_app import onboarding, services
from aicmo.store_app.forms import ApprovalForm, PackForm
from aicmo.store_app.models import Job


@login_required
@require_GET
@never_cache
def home(request: HttpRequest) -> HttpResponse:
    stores = services.allowed_stores(request.user)
    jobs = Job.objects.filter(store__in=stores).select_related("store").order_by("-created_at")[:30]
    return render(
        request,
        "store_app/home.html",
        {
            "stores": stores,
            "jobs": jobs,
            "can_onboard": isinstance(request.user, User) and onboarding.new_owner(request.user),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def create(request: HttpRequest, store_id: int) -> HttpResponse:
    store = services.allowed_stores(request.user).filter(pk=store_id).first()
    if store is None:
        raise Http404
    form = PackForm(
        request.POST if request.method == "POST" else None,
        initial={"submission_key": uuid.uuid4()},
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.engine()  # Require the operator's executor configuration.
            job = services.submit(
                store, form.cleaned_data["submission_key"], form.cleaned_data["brief"]
            )
        except (AicmoError, services.StoreActionError):
            form.add_error(
                None,
                "접수하지 못했습니다. 진행 중인 작업을 확인하거나 운영자에게 문의해 주세요.",
            )
        else:
            return redirect("job", job_id=job.id)
    status = 400 if request.method == "POST" and form.errors else 200
    return render(request, "store_app/create.html", {"store": store, "form": form}, status=status)


@login_required
@require_GET
@never_cache
def detail(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    pack, approval_form, notice = None, None, str(job.notice)
    if job.state in ("waiting_approval", "success", "needs_work"):
        try:
            pack, pack_sha, photo_sha = services.preview(job)
            approval_form = ApprovalForm(initial={"pack_sha": pack_sha, "photo_sha": photo_sha})
        except (AicmoError, OSError, ValueError, sqlite3.Error, services.StoreActionError):
            notice = "내용을 확인할 수 없습니다. 운영자에게 문의해 주세요."
    return render(
        request,
        "store_app/job.html",
        {
            "job": job,
            "pack": pack,
            "approval_form": approval_form,
            "notice": notice,
        },
    )


@login_required
@require_POST
@never_cache
def approve(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    form = ApprovalForm(request.POST)
    job = services.owned_job(request.user, job_id)
    if form.is_valid():
        try:
            services.request_approval(
                job,
                form.cleaned_data["pack_sha"],
                form.cleaned_data["photo_sha"],
                str(request.user.pk),
            )
        except (AicmoError, OSError, ValueError, sqlite3.Error, services.StoreActionError):
            return render(
                request,
                "store_app/error.html",
                {
                    "job": job,
                    "notice": "승인할 버전을 확인할 수 없습니다. 화면을 새로 열어 주세요.",
                },
                status=409,
            )
        return redirect("job", job_id=job.id)
    return render(
        request,
        "store_app/error.html",
        {"job": job, "notice": "확인 항목에 체크한 뒤 다시 승인해 주세요."},
        status=400,
    )


@login_required
@require_POST
@never_cache
def cancel(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    with transaction.atomic():
        job = services.owned_job(request.user, job_id)
        services.request_cancel(job)
    return redirect("job", job_id=job.id)


@login_required
@require_POST
@never_cache
def download(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse | FileResponse:
    job = services.owned_job(request.user, job_id)
    try:
        path: Path = services.download(job)
    except (AicmoError, OSError, ValueError, sqlite3.Error, services.StoreActionError):
        return render(
            request,
            "store_app/error.html",
            {
                "job": job,
                "notice": "현재 승인된 파일을 확인할 수 없습니다. 운영자에게 문의해 주세요.",
            },
            status=409,
        )
    return FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename="가게-실행팩.zip",
        content_type="application/zip",
    )
