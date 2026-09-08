from __future__ import annotations

import json
import sqlite3
import uuid
from typing import TYPE_CHECKING

from django import forms
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from pydantic import TypeAdapter

from aicmo.errors import AicmoError
from aicmo.local_pack import WORKFLOW_ID, LocalPack, parse_brief
from aicmo.pack_edits import EditBase, digest, inspect_base, pack_text
from aicmo.pack_rewrite import RewriteRequest, facts_sha, parse_rewrite
from aicmo.runner import WorkflowRunner
from aicmo.store_app import editor, guidance, services
from aicmo.store_app.models import EditDraft, Job
from aicmo.store_app.onboarding import clean_value, validate_post
from aicmo.web_run_lock import web_run_lock

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.http import HttpRequest, HttpResponse

_SALT = "aicmo.web-rewrite.v1"
_ERRORS = (AicmoError, OSError, ValueError, sqlite3.Error, services.StoreActionError)


class RewriteForm(forms.Form):
    action = forms.ChoiceField(
        label="어떻게 다시 쓸까요?",
        choices=[("shorten", "짧게"), ("friendly", "친근하게"), ("price", "가격·기간·혜택 수정")],
        error_messages={"invalid_choice": "다시 쓸 방법을 목록에서 선택해 주세요."},
    )
    fact = forms.CharField(
        label="이번 소식의 확인된 사실 전체",
        max_length=1200,
        widget=forms.Textarea(attrs={"rows": 5}),
        help_text="가격을 바꿀 때는 이전 가격을 지우고 새 가격·적용 기간·조건을 직접 확인하세요.",
    )
    checked = forms.BooleanField(label="입력한 사실·가격·기간·혜택을 직접 확인했습니다.")


class ConfirmForm(forms.Form):
    token = forms.CharField(max_length=128000, widget=forms.HiddenInput)
    checked = forms.BooleanField(label="새 작업으로 작성 시도와 사용 건수를 쓰는 데 동의합니다.")


def source(job: Job, runner: WorkflowRunner) -> tuple[EditBase, LocalPack, int]:
    job.refresh_from_db()
    if job.workflow_id != WORKFLOW_ID:
        raise Http404
    if (
        job.state != "cancelled"
        or job.cancel_requested
        or job.approval
        or runner.store.get_run(job.run_id)["status"] != "cancelled"
        or runner.store.approval_for(job.run_id, "owner_gate") is not None
        or runner.store.get_inputs(job.run_id) != job.inputs
        or job.inputs.get("client") != job.store.client
    ):
        reason = "기존 작업의 취소가 완료된 뒤 다시 작성할 수 있습니다."
        raise services.StoreActionError(reason)
    base, original = inspect_base(runner, job.run_id)
    draft = EditDraft.objects.filter(job=job).first()
    if draft is None:
        return base, original, 0
    if EditBase.model_validate_json(json.dumps(draft.base)) != base:
        reason = "저장된 수정본의 기준이 바뀌었습니다."
        raise services.StoreActionError(reason)
    return base, editor.stored_pack(draft, original, runner), draft.revision


def prepare(job: Job, runner: WorkflowRunner, form: RewriteForm, user_id: str) -> dict[str, str]:
    base, pack, revision = source(job, runner)
    brief = parse_brief(job.inputs)
    if len(brief.facts) != 1:
        reason = "소식 한 건인 웹 작업만 다시 작성할 수 있습니다."
        raise services.StoreActionError(reason)
    fact = form.cleaned_data["fact"]
    if form.cleaned_data["action"] != "price" and brief.facts != [fact]:
        reason = "사실을 바꾸려면 가격·기간·혜택 수정을 선택해 주세요."
        raise services.StoreActionError(reason)
    brief = brief.model_copy(update={"facts": [fact]})
    request = RewriteRequest.model_validate(
        {
            "schema_version": "aicmo.pack-rewrite.v1",
            "source_run_id": job.run_id,
            "base": base,
            "revision": revision,
            "edited_sha": digest(pack_text(pack)),
            "source_body": pack_text(pack),
            "action": form.cleaned_data["action"],
            "confirmed_by": f"web-user:{user_id}",
            "facts_sha": facts_sha(brief.facts),
        }
    )
    return {
        "source_id": str(job.id),
        "store_id": str(job.store.pk),
        "user_id": user_id,
        "submission_key": str(uuid.uuid4()),
        "brief_json": brief.model_dump_json(),
        "rewrite_json": request.model_dump_json(),
        "photos_json": job.inputs.get("photos_json", ""),
    }


def submit(
    job: Job, runner: WorkflowRunner, token: str, actor: AbstractBaseUser | AnonymousUser
) -> Job:
    job = services.owned_pack_job(actor, job.pk)
    user_id = str(actor.pk)
    payload = TypeAdapter(dict[str, str]).validate_python(
        signing.loads(token, salt=_SALT, max_age=3600), strict=True
    )
    if (
        set(payload)
        != {
            "source_id",
            "store_id",
            "user_id",
            "submission_key",
            "brief_json",
            "rewrite_json",
            "photos_json",
        }
        or payload["source_id"] != str(job.id)
        or payload["store_id"] != str(job.store.pk)
        or payload["user_id"] != user_id
    ):
        reason = "이 가게에서 확인한 재작성 요청이 아닙니다."
        raise services.StoreActionError(reason)
    request = parse_rewrite(payload["rewrite_json"])
    key = uuid.UUID(payload["submission_key"])
    with web_run_lock(runner.repo_root, job.run_id, blocking=False):
        base, pack, revision = source(job, runner)
        if (
            request.source_run_id != job.run_id
            or request.base != base
            or request.revision != revision
            or request.edited_sha != digest(pack_text(pack))
            or request.confirmed_by != f"web-user:{user_id}"
            or payload["photos_json"] != job.inputs.get("photos_json", "")
        ):
            reason = "미리보기 이후 기준 문안이 바뀌었습니다. 다시 확인해 주세요."
            raise services.StoreActionError(reason)
        prior = Job.objects.filter(store=job.store, submission_key=key).first()
        if prior is None:
            if guidance.allowance(job.store)["blocked"]:
                reason = "새 요청의 사용 가능 건수가 부족합니다."
                raise services.StoreActionError(reason)
            services.engine()  # Validate configuration without generating or charging.
        with transaction.atomic():
            current = services.owned_pack_job(services.fresh_actor(actor), job.pk)
            if (
                current.inputs != job.inputs
                or current.store.pk != job.store.pk
                or current.store.client != job.inputs.get("client")
            ):
                raise Http404
            return services.submit(
                current.store,
                key,
                payload["brief_json"],
                rewrite_json=payload["rewrite_json"],
                photos_json=payload["photos_json"] or None,
                actor=actor,
            )


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def rewrite(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    job = services.owned_pack_job(request.user, job_id)
    runner = services.reader()
    form = None
    context: dict[str, object] = {"job": job, "allowance": guidance.allowance(job.store)}
    try:
        if job.state == "waiting_approval" and request.method == "GET":
            context["cancel_first"] = True
            return render(request, "store_app/rewrite.html", context)
        if request.method == "POST" and request.POST.get("stage") == "confirm":
            validate_post(request.POST, {*ConfirmForm().fields, "stage"})
            confirmation = ConfirmForm(request.POST)
            if not confirmation.is_valid():
                reason = "사용 건수 동의 후 요청을 다시 확인해 주세요."
                raise services.StoreActionError(reason)
            next_job = submit(job, runner, confirmation.cleaned_data["token"], request.user)
            return redirect("job", job_id=next_job.id)
        with web_run_lock(runner.repo_root, job.run_id, blocking=False):
            _, pack, _ = source(job, runner)
            form = RewriteForm(initial={"fact": parse_brief(job.inputs).facts[0]})
            if request.method == "POST":
                validate_post(request.POST, {*form.fields, "stage"})
                if request.POST.get("stage") != "preview":
                    reason = "요청 단계를 확인할 수 없습니다."
                    raise services.StoreActionError(reason)
                form = RewriteForm(
                    {
                        "action": request.POST.get("action", ""),
                        "fact": clean_value(request.POST.get("fact", ""), form.fields["fact"]),
                        "checked": request.POST.get("checked", ""),
                    }
                )
                valid = form.is_valid()
                form.data = dict(form.cleaned_data)  # Render validated values only on errors.
                if valid:
                    payload = prepare(job, runner, form, str(request.user.pk))
                    context.update(
                        fact=form.cleaned_data["fact"],
                        action_label={
                            "shorten": "짧게",
                            "friendly": "친근하게",
                            "price": "가격·기간·혜택 수정",
                        }[form.cleaned_data["action"]],
                        confirmation=ConfirmForm(
                            initial={"token": signing.dumps(payload, salt=_SALT, compress=True)}
                        ),
                    )
            context["pack"] = pack
    except (*_ERRORS, signing.BadSignature):
        context["notice"] = (
            "기준 문안·사용 건수·연결 상태를 확인하지 못했습니다. 최신 화면에서 다시 확인해 주세요."
        )
        context["form"] = form
        return render(request, "store_app/rewrite.html", context, status=409)
    context["form"] = form
    return render(request, "store_app/rewrite.html", context, status=400 if form.errors else 200)
