from __future__ import annotations

from http import HTTPStatus
from typing import cast

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from aicmo.errors import AicmoError
from aicmo.store_app import onboarding
from aicmo.store_app.forms import ONBOARDING_FORMS, OnboardingConfirmForm
from aicmo.store_app.models import OnboardingDraft
from aicmo.store_app.services import StoreActionError


def _saved_response(request: HttpRequest, action: str, step: int) -> HttpResponse:
    if action == "save":
        messages.success(request, "가게 정보를 임시 저장했습니다. 다시 이어 쓸 수 있어요.")
        return redirect("home")
    if action == "back":
        return redirect("onboarding-step", step=max(1, step - 1))
    if step == len(ONBOARDING_FORMS):
        return redirect("onboarding-confirm")
    return redirect("onboarding-step", step=step + 1)


def _save(request: HttpRequest, step: int, user: User) -> HttpResponse:
    form_type = ONBOARDING_FORMS[step]
    # Rejected secret-bearing input is neither saved nor echoed in the error page.
    form = form_type(data={})
    try:
        safe = onboarding.partial_values(step, request.POST)
        revision = OnboardingConfirmForm().fields["revision"].clean(request.POST.get("revision"))
        form = form_type(data={**safe, "revision": revision})
        action = request.POST.get("action", "next")
        if action != "next" or form.is_valid():
            onboarding.save_step(user, step, revision, safe, completed=action == "next")
            return _saved_response(request, action, step)
        status = 400
    except (AicmoError, StoreActionError, ValidationError, ValueError):
        form.add_error(None, "저장하지 못했습니다. 입력을 확인하거나 최신 저장 내용을 열어 주세요.")
        status = 409
    return render(request, "store_app/onboarding.html", {"form": form, "step": step}, status=status)


def _unavailable(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "store_app/error.html",
        {"notice": "저장된 가게 정보를 확인할 수 없습니다. 운영자에게 문의해 주세요."},
        status=409,
    )


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def wizard(request: HttpRequest, step: int = 1) -> HttpResponse:
    if not isinstance(request.user, User) or step not in ONBOARDING_FORMS:
        raise Http404
    if not onboarding.new_owner(request.user):
        return redirect("home")
    draft = OnboardingDraft.objects.filter(owner=request.user).first()
    if draft is not None and draft.state != "draft":
        return redirect("onboarding-confirm")
    next_step = 1 if draft is None else min(draft.completed_step + 1, len(ONBOARDING_FORMS))
    if step > next_step:
        return redirect("onboarding-step", step=next_step)
    if request.method == "POST":
        return _save(request, step, request.user)
    try:
        values = {} if draft is None else onboarding.stored_values(draft)
    except (StoreActionError, ValueError):
        return _unavailable(request)
    form = ONBOARDING_FORMS[step](
        initial={**values, "revision": 0 if draft is None else draft.revision}
    )
    return render(request, "store_app/onboarding.html", {"form": form, "step": step})


def _confirm_post(request: HttpRequest, user: User, form: OnboardingConfirmForm) -> int:
    try:
        onboarding.validate_post(request.POST, set(form.fields))
        if not form.is_valid():
            return 400
        onboarding.confirm(user, form.cleaned_data["revision"])
    except (AicmoError, StoreActionError, ValueError):
        form.add_error(None, "확인한 내용이 달라졌습니다. 최신 내용을 다시 확인해 주세요.")
        return 409
    return 200


def _review_rows(values: dict[str, str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for form_type in ONBOARDING_FORMS.values():
        for name, field in form_type().fields.items():
            if name == "revision":
                continue
            value = values.get(name) or "미입력"
            if isinstance(field, forms.ChoiceField):
                choices = cast("list[tuple[str, str]]", field.choices)
                value = dict(choices).get(value, value)
            rows.append((str(field.label), value))
    return rows


@login_required
@require_http_methods(["GET", "POST"])
@never_cache
def confirmation(request: HttpRequest) -> HttpResponse:  # noqa: PLR0911 — explicit state redirects
    if not isinstance(request.user, User):
        raise Http404
    draft = OnboardingDraft.objects.filter(owner=request.user).first()
    if draft is None:
        return redirect("onboarding")
    if draft.state == "complete":
        if draft.store is None:
            raise Http404
        return redirect("create", store_id=draft.store.pk)
    if not onboarding.new_owner(request.user):
        return redirect("home")
    if draft.completed_step != len(ONBOARDING_FORMS):
        return redirect("onboarding-step", step=draft.completed_step + 1)
    form = OnboardingConfirmForm(
        request.POST if request.method == "POST" else None, initial={"revision": draft.revision}
    )
    status = _confirm_post(request, request.user, form) if request.method == "POST" else 200
    if request.method == "POST" and status == HTTPStatus.OK:
        return redirect("onboarding-confirm")
    try:
        rows = _review_rows(onboarding.stored_values(draft))
    except (StoreActionError, ValueError):
        return _unavailable(request)
    return render(
        request,
        "store_app/onboarding_confirm.html",
        {
            "draft": draft,
            "form": form,
            "rows": rows,
        },
        status=status,
    )
