from __future__ import annotations

import sqlite3
import uuid

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from aicmo.errors import AicmoError
from aicmo.local_pack import LocalPack, parse_brief
from aicmo.pack_edits import digest, editable_values, pack_text
from aicmo.photos import parse_photos
from aicmo.store_app import editor, services
from aicmo.store_app.models import EditVersion
from aicmo.store_app.onboarding import validate_post
from aicmo.web_run_lock import web_run_lock

_ERRORS = (AicmoError, OSError, ValueError, sqlite3.Error, services.StoreActionError)


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def edit(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    runner = services.reader()
    asynchronous = request.headers.get("Accept") == "application/json"
    form = None
    pack = draft = base = None
    try:
        if request.method == "POST":
            # The server-owned brief defines the field inventory without reading mutable files.
            # Bind only bounded, sanitized text before attempting locks or base verification.
            form = editor.submitted_form(editor.EditForm(parse_brief(job.inputs)), request.POST)
            action = request.POST.get("action", "checkpoint")
            if action not in ("autosave", "checkpoint"):
                reason = "저장 방법을 확인할 수 없습니다."
                raise services.StoreActionError(reason)
            if form.is_valid():
                saved = editor.save(
                    job,
                    runner,
                    form.cleaned_data["base_token"],
                    form.cleaned_data["revision"],
                    {
                        name: str(form.cleaned_data[name])
                        for name in form.fields
                        if name not in ("base_token", "revision")
                    },
                    checkpoint=action == "checkpoint",
                )
                if asynchronous:
                    return JsonResponse(
                        {
                            "revision": saved.revision,
                            "values": editable_values(LocalPack.model_validate_json(saved.body)),
                            "message": "수정본을 저장했습니다.",
                        }
                    )
                return redirect("edit", job_id=job.id)
            if asynchronous:
                return JsonResponse(
                    {"message": "입력 항목을 확인하고 다시 저장해 주세요."}, status=409
                )
        else:
            with web_run_lock(runner.repo_root, job.run_id, blocking=False):
                job.refresh_from_db()
                base, pack, draft = editor.current(job, runner)
            form = editor.EditForm(
                pack,
                initial={
                    **editable_values(pack),
                    "revision": draft.revision if draft else 0,
                    "base_token": digest(base.model_dump_json()),
                },
            )
    except _ERRORS:
        notice = (
            "수정본을 확인하거나 저장할 수 없습니다. "
            "작업 처리 중인지 확인하고 최신 작업을 별도 탭에서 확인해 주세요."
        )
        if asynchronous:
            return JsonResponse({"message": notice}, status=409)
        if form is None or not form.is_bound:
            return render(
                request, "store_app/error.html", {"job": job, "notice": notice}, status=409
            )
        form.add_error(None, notice + " 안전하게 확인한 입력은 아래에 유지했습니다.")
    versions = (
        EditVersion.objects.filter(draft=draft).order_by("-revision")
        if draft
        else EditVersion.objects.none()
    )
    return render(
        request,
        "store_app/edit.html",
        {
            "job": job,
            "form": form,
            "pack": pack,
            "versions": versions,
            "draft": draft,
            "base_token": digest(base.model_dump_json()) if base else "",
        },
        status=409 if request.method == "POST" else 200,
    )


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def confirmation(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    runner = services.reader()
    try:
        if request.method == "POST":
            validate_post(request.POST, set(editor.EditConfirmation().fields))
            form = editor.EditConfirmation(request.POST)
            if form.is_valid():
                editor.confirm(
                    job,
                    runner,
                    form.cleaned_data["revision"],
                    form.cleaned_data["base_token"],
                    form.cleaned_data["edited_sha"],
                    str(request.user.pk),
                )
                return redirect("job", job_id=job.id)
            return render(
                request,
                "store_app/error.html",
                {"job": job, "notice": "확인 항목에 체크한 뒤 수정본을 다시 확인해 주세요."},
                status=400,
            )
        with web_run_lock(runner.repo_root, job.run_id, blocking=False):
            job.refresh_from_db()
            base, pack, draft = editor.current(job, runner)
        if draft is None:
            return redirect("edit", job_id=job.id)
        form = editor.EditConfirmation(
            initial={
                "revision": draft.revision,
                "base_token": digest(base.model_dump_json()),
                "edited_sha": digest(pack_text(pack)),
            }
        )
    except _ERRORS:
        return render(
            request,
            "store_app/error.html",
            {
                "job": job,
                "notice": (
                    "확인한 수정본이 바뀌었거나 작업을 처리 중입니다. "
                    "최신 수정본을 다시 확인해 주세요."
                ),
            },
            status=409,
        )
    return render(
        request,
        "store_app/edit_confirm.html",
        {
            "job": job,
            "pack": pack,
            "form": form,
            "draft": draft,
            "photos": parse_photos(job.inputs).photos,
        },
        status=400 if request.method == "POST" else 200,
    )


@login_required
@require_POST
@never_cache
def restore(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_job(request.user, job_id)
    try:
        validate_post(request.POST, set(editor.RestoreForm().fields))
        form = editor.RestoreForm(request.POST)
        if form.is_valid():
            editor.save(
                job,
                services.reader(),
                form.cleaned_data["base_token"],
                form.cleaned_data["revision"],
                restore=form.cleaned_data["version"],
            )
            return redirect("edit", job_id=job.id)
    except _ERRORS:
        pass
    return render(
        request,
        "store_app/error.html",
        {
            "job": job,
            "notice": (
                "이전 버전을 복원하지 못했습니다. 현재 수정본은 그대로 남아 있습니다. "
                "최신 화면에서 다시 확인해 주세요."
            ),
        },
        status=409,
    )
