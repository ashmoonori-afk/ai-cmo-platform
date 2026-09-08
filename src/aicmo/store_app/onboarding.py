from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from pydantic import TypeAdapter

from aicmo.onboarding import validate_answers
from aicmo.store_app.forms import ONBOARDING_FORMS, onboarding_answers
from aicmo.store_app.forms import (
    clean_value as clean_value,  # noqa: PLC0414 — preserve public import
)
from aicmo.store_app.models import OnboardingDraft, Store
from aicmo.store_app.services import StoreActionError, fresh_actor

if TYPE_CHECKING:
    from django.contrib.auth.models import User
    from django.http import QueryDict


def new_owner(user: User) -> bool:
    return (
        user.is_active
        and not user.has_perm("store_app.operate_stores")
        and not Store.objects.filter(owner=user).exists()
    )


def partial_values(step: int, post: QueryDict) -> dict[str, str]:
    fields = ONBOARDING_FORMS[step]().fields
    validate_post(post, {*fields, "action"})
    if post.get("action", "next") not in ("next", "back", "save"):
        reason = "저장 방법을 확인할 수 없습니다."
        raise StoreActionError(reason)
    return {
        name: clean_value(post.get(name, ""), field)
        for name, field in fields.items()
        if name != "revision"
    }


def validate_post(post: QueryDict, fields: set[str]) -> None:
    allowed = {*fields, "csrfmiddlewaretoken"}
    if set(post) - allowed or any(len(post.getlist(key)) != 1 for key in post):
        reason = "입력 항목을 확인할 수 없습니다. 화면을 다시 열어 주세요."
        raise StoreActionError(reason)


def stored_values(draft: OnboardingDraft) -> dict[str, str]:
    values = TypeAdapter(dict[str, str]).validate_python(draft.data, strict=True)
    fields = {
        name: field
        for form in ONBOARDING_FORMS.values()
        for name, field in form().fields.items()
        if name != "revision"
    }
    if set(values) - fields.keys():
        reason = "저장된 입력을 확인할 수 없습니다. 운영자에게 문의해 주세요."
        raise StoreActionError(reason)
    for name, value in values.items():
        if clean_value(value, fields[name]) != value:
            reason = "저장된 입력의 개인정보 처리를 확인할 수 없습니다."
            raise StoreActionError(reason)
    return values


def validated_values(draft: OnboardingDraft) -> dict[str, str]:
    values = stored_values(draft)
    for form_type in ONBOARDING_FORMS.values():
        form = form_type(data={**values, "revision": str(draft.revision)})
        if not form.is_valid():
            reason = "입력 항목을 다시 확인해 주세요."
            raise StoreActionError(reason)
    validate_answers(onboarding_answers(values, draft.client, ""))
    return values


def save_step(
    user: User, step: int, revision: int, values: dict[str, str], *, completed: bool
) -> OnboardingDraft:
    with transaction.atomic():
        user = fresh_actor(user)
        if not new_owner(user):
            reason = "이미 연결된 가게를 이용해 주세요."
            raise StoreActionError(reason)
        draft, _ = OnboardingDraft.objects.get_or_create(owner=user)
        if draft.state != "draft" or draft.revision != revision or step > draft.completed_step + 1:
            reason = "다른 화면에서 내용이 바뀌었습니다. 최신 내용을 확인한 뒤 다시 저장해 주세요."
            raise StoreActionError(reason)
        draft.data = {**stored_values(draft), **values}
        draft.revision += 1
        if completed:
            draft.completed_step = max(draft.completed_step, step)
        draft.save(update_fields=["data", "revision", "completed_step", "updated_at"])
        return draft


def confirm(user: User, revision: int) -> OnboardingDraft:
    # Validate outside the SQLite write transaction, then compare its exact revision.
    draft = OnboardingDraft.objects.get(owner=user)
    validated_values(draft)
    with transaction.atomic():
        user = fresh_actor(user)
        current = get_object_or_404(OnboardingDraft, pk=draft.pk, owner=user)
        if (
            current.revision != revision
            or current.revision != draft.revision
            or current.completed_step != len(ONBOARDING_FORMS)
            or not new_owner(user)
        ):
            reason = "확인한 내용이 달라졌습니다. 최신 내용을 확인해 주세요."
            raise StoreActionError(reason)
        if current.state in ("queued", "running"):
            return current
        if current.state not in ("draft", "failed"):
            reason = "현재 상태에서는 다시 제출할 수 없습니다."
            raise StoreActionError(reason)
        if current.stage_id is None and current.attempts >= OnboardingDraft.MAX_ATTEMPTS:
            reason = "가게 준비 재시도 횟수를 초과했습니다. 운영자에게 문의해 주세요."
            raise StoreActionError(reason)
        current.state = "queued"
        current.failure_code = ""
        current.confirmed_at = current.confirmed_at or timezone.now()
        current.save(update_fields=["state", "failure_code", "confirmed_at", "updated_at"])
        return current
