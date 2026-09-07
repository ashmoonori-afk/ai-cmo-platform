from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING

from django import forms
from django.db import transaction
from django.utils import timezone

from aicmo.local_pack import LocalPack, PackBrief, validate_pack
from aicmo.models import StepStatus
from aicmo.pack_edits import (
    EditApproval,
    EditBase,
    digest,
    editable_values,
    inspect_base,
    merge_edit,
    pack_text,
)
from aicmo.runner import WorkflowRunner
from aicmo.store_app.models import EditDraft, EditVersion, Job
from aicmo.store_app.onboarding import clean_value, validate_post
from aicmo.store_app.services import StoreActionError
from aicmo.web_run_lock import web_run_lock

if TYPE_CHECKING:
    from django.http import QueryDict

# ponytail: 100 explicit checkpoints per job; add an archival policy if owners reach this limit.
MAX_CHECKPOINTS = 100


class EditForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    base_token = forms.RegexField(r"^[a-f0-9]{64}$", widget=forms.HiddenInput)

    def __init__(
        self,
        pack: LocalPack | PackBrief,
        data: Mapping[str, str] | None = None,
        *,
        initial: dict[str, object] | None = None,
    ) -> None:
        super().__init__(data=data, initial=initial)
        labels = {"title": "제목", "body": "본문", "cta": "손님에게 안내할 행동", "period": "기간"}
        for index in range(pack.news_count if isinstance(pack, PackBrief) else len(pack.news)):
            for name, label in labels.items():
                self.fields[f"news_{index}_{name}"] = forms.CharField(
                    label=f"소식 {index + 1} · {label}",
                    max_length=1200,
                    widget=forms.Textarea(attrs={"rows": 5 if name == "body" else 2}),
                )
        for index in range(pack.reply_count if isinstance(pack, PackBrief) else len(pack.replies)):
            self.fields[f"reply_{index}"] = forms.CharField(
                label=f"리뷰 {index + 1} · 답글",
                max_length=1200,
                widget=forms.Textarea(attrs={"rows": 3}),
            )


class EditConfirmation(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    base_token = forms.RegexField(r"^[a-f0-9]{64}$", widget=forms.HiddenInput)
    edited_sha = forms.RegexField(r"^[a-f0-9]{64}$", widget=forms.HiddenInput)
    checked = forms.BooleanField(
        label="수정한 문안이 확인한 사실·가격·기간과 일치하며 사용 권리를 확인했습니다."
    )


class RestoreForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    base_token = forms.RegexField(r"^[a-f0-9]{64}$", widget=forms.HiddenInput)
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


def editable(job: Job, runner: WorkflowRunner) -> None:
    if (
        job.state != "waiting_approval"
        or job.cancel_requested
        or job.approval != {}
        or runner.store.get_step_status(job.run_id, "owner_gate") != StepStatus.WAITING_APPROVAL
        or runner.store.approval_for(job.run_id, "owner_gate") is not None
    ):
        reason = "현재 작업은 수정할 수 없습니다. 진행 상태를 확인해 주세요."
        raise StoreActionError(reason)


def stored_pack(draft: EditDraft, original: LocalPack, runner: WorkflowRunner) -> LocalPack:
    inputs = runner.store.get_inputs(draft.job.run_id)
    pack = validate_pack(draft.body, inputs)
    if pack_text(merge_edit(original, editable_values(pack), inputs)) != draft.body:
        reason = "저장된 수정본을 확인하지 못했습니다. 운영자에게 문의해 주세요."
        raise StoreActionError(reason)
    return pack


def current(job: Job, runner: WorkflowRunner) -> tuple[EditBase, LocalPack, EditDraft | None]:
    editable(job, runner)
    base, original = inspect_base(runner, job.run_id)
    draft = EditDraft.objects.filter(job=job).first()
    if draft is None:
        return base, original, None
    if EditBase.model_validate_json(json.dumps(draft.base)) != base:
        reason = "생성된 기준 문안이 바뀌었습니다. 운영자에게 문의해 주세요."
        raise StoreActionError(reason)
    return base, stored_pack(draft, original, runner), draft


def submitted_form(form: EditForm, post: QueryDict) -> EditForm:
    # Reuse the same bounded/secret-aware entry boundary as onboarding; never echo raw secrets.
    validate_post(post, {*form.fields, "action"})
    # Hashes/revisions are identifiers, not customer prose. A digit sequence in a SHA
    # may look like a phone number; validate metadata without redacting its identity.
    try:
        metadata = {
            name: str(form.fields[name].clean(post.get(name, "")))
            for name in ("revision", "base_token")
        }
    except forms.ValidationError:
        reason = "수정본 번호와 기준 문안을 확인할 수 없습니다."
        raise StoreActionError(reason) from None
    form.data = {
        **metadata,
        **{
            name: clean_value(post.get(name, ""), field)
            for name, field in form.fields.items()
            if name not in metadata
        },
    }
    form.is_bound = True
    return form


def _checkpoint(draft: EditDraft) -> None:
    if EditVersion.objects.filter(draft=draft, revision=draft.revision).exists():
        return
    if EditVersion.objects.filter(draft=draft).count() >= MAX_CHECKPOINTS:
        reason = (
            "저장한 버전 100개에 도달했습니다. "
            "현재 자동저장 문안은 남아 있으며 확인·승인할 수 있습니다."
        )
        raise StoreActionError(reason)
    EditVersion.objects.create(draft=draft, revision=draft.revision, body=draft.body)


def save(  # noqa: C901 — atomic revision/replay/checkpoint/restore contract
    job: Job,
    runner: WorkflowRunner,
    base_token: str,
    revision: int,
    values: dict[str, str] | None = None,
    *,
    checkpoint: bool = False,
    restore: int | None = None,
) -> EditDraft:
    # Lock order: per-run OS lock -> short Django transaction. Never invert it.
    with web_run_lock(runner.repo_root, job.run_id, blocking=False):
        job.refresh_from_db()
        base, original = inspect_base(runner, job.run_id)
        if digest(base.model_dump_json()) != base_token:
            reason = "기준 문안이 바뀌었습니다. 최신 화면을 확인해 주세요."
            raise StoreActionError(reason)
        inputs = runner.store.get_inputs(job.run_id)
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job.pk)
            editable(job, runner)
            draft = EditDraft.objects.select_for_update().filter(job=job).first()
            if draft is None:
                if revision != 0 or restore is not None:
                    reason = "저장된 버전을 확인할 수 없습니다."
                    raise StoreActionError(reason)
                draft = EditDraft.objects.create(
                    job=job, base=base.model_dump(mode="json"), body=pack_text(original)
                )
                _checkpoint(draft)
            if EditBase.model_validate_json(json.dumps(draft.base)) != base:
                reason = "수정본의 기준 문안이 바뀌었습니다."
                raise StoreActionError(reason)
            stored_pack(draft, original, runner)
            if restore is not None:
                version = EditVersion.objects.filter(draft=draft, revision=restore).first()
                if version is None:
                    reason = "이 작업의 저장된 버전이 아닙니다."
                    raise StoreActionError(reason)
                values = editable_values(validate_pack(version.body, inputs))
                if pack_text(merge_edit(original, values, inputs)) != version.body:
                    reason = "저장된 버전의 보호 항목이 바뀌었습니다."
                    raise StoreActionError(reason)
            if values is None:
                reason = "수정할 문안을 입력해 주세요."
                raise StoreActionError(reason)
            body = pack_text(merge_edit(original, values, inputs))
            replay = revision == draft.revision - 1 and body == draft.body
            if revision != draft.revision and not replay:
                reason = (
                    "다른 화면에서 저장한 내용이 있습니다. 입력은 유지했습니다. "
                    "최신 버전을 별도로 확인해 주세요."
                )
                raise StoreActionError(reason)
            if not replay and body != draft.body:
                if restore is not None:
                    _checkpoint(draft)  # Preserve the current autosaved text before restoration.
                draft.body = body
                draft.revision += 1
                draft.save(update_fields=["body", "revision", "updated_at"])
            if checkpoint or restore is not None:
                _checkpoint(draft)
            return draft


def confirm(
    job: Job, runner: WorkflowRunner, revision: int, base_token: str, edited_sha: str, user_id: str
) -> Job:
    with web_run_lock(runner.repo_root, job.run_id, blocking=False):
        job.refresh_from_db()
        if job.approval:
            prior = EditApproval.model_validate_json(json.dumps(job.approval))
            if (
                not job.cancel_requested
                and job.state != "cancelled"
                and prior.revision == revision
                and prior.edited_sha == edited_sha
                and digest(prior.base.model_dump_json()) == base_token
                and prior.reviewer == f"web-user:{user_id}"
            ):
                return job
            reason = "이미 확인한 버전과 다른 요청입니다."
            raise StoreActionError(reason)
        base, pack, draft = current(job, runner)
        if (
            draft is None
            or draft.revision != revision
            or digest(draft.body) != edited_sha
            or digest(base.model_dump_json()) != base_token
        ):
            reason = "확인 화면 이후 문안이 바뀌었습니다. 다시 확인해 주세요."
            raise StoreActionError(reason)
        receipt = EditApproval(
            schema_version="aicmo.web-edit-approval.v1",
            base=base,
            revision=revision,
            edited_sha=digest(pack_text(pack)),
            reviewer=f"web-user:{user_id}",
            requested_at=timezone.now(),
        )
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job.pk)
            editable(job, runner)
            head = EditDraft.objects.select_for_update().get(pk=draft.pk)
            if head.revision != revision or head.body != draft.body or head.base != draft.base:
                reason = "저장된 수정본이 바뀌었습니다. 다시 확인해 주세요."
                raise StoreActionError(reason)
            job.approval = receipt.model_dump(mode="json")
            job.state = "queued"
            job.save(update_fields=["approval", "state", "updated_at"])
        return job
