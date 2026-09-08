"""Owner preferences about a reviewed report; these are not execution or learning receipts."""

# pyright: reportImportCycles=false
# The report UI attaches cards; the write boundary loads report verification lazily.
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from django.conf import settings
from django.db import transaction
from django.http import Http404
from pydantic import BaseModel, ConfigDict, Field, field_validator

from aicmo.outcomes import DAYS_PER_WEEK
from aicmo.redaction import MAX_KB_ENTRY_CHARS, contains_raw_secret, safe_kb_text
from aicmo.store import WorkflowStore
from aicmo.store_app import services
from aicmo.store_app.models import Job
from aicmo.web_run_lock import web_run_lock

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

    from aicmo.store_app.report_services import ReviewedReport

type ActionCode = Literal["review_records", "check_existing_news", "add_real_news"]
type Decision = Literal["selected", "declined"]
EVENT_TYPE = "owner.action.v1"


@dataclass(frozen=True, slots=True)
class ActionCard:
    code: ActionCode
    title: str
    evidence: str
    target: Literal["outcomes", "archive", "create"]
    intent: Literal["news"] | None = None


def cards(report: ReviewedReport) -> tuple[ActionCard, ...]:
    """Use only the report's frozen observations; never infer new business facts or effects."""
    totals = report.source.totals
    partial = any(
        row.current_days < DAYS_PER_WEEK or row.previous_days < DAYS_PER_WEEK
        for row in totals.values()
    )
    coverage = ", ".join(
        f"{label} {totals[metric].current_days}/7일"
        for metric, label in (
            ("posts", "게시"),
            ("inquiries", "문의"),
            ("reservations", "예약"),
            ("coupon_redemptions", "쿠폰 사용"),
        )
    )
    result = [
        ActionCard(
            "review_records",
            "아직 확인하지 않은 기록 살펴보기" if partial else "다음 기록도 같은 기준으로 확인",
            f"{report.source.week_start} 주 · {report.source.channel}: {coverage}. "
            "확인한 날만 기록하고, 아직 확인하지 않은 날과 미래 날짜를 0으로 채우지 마세요.",
            "outcomes",
        )
    ]
    if report.source.channel == "naver":
        posts = totals["posts"]
        evidence = (
            "이번 주 게시 수를 확인한 날이 없습니다."
            if posts.current is None
            else (
                f"이번 주 게시 입력은 {posts.current_days}/7일, "
                f"관측한 부분합은 {posts.current}건입니다."
            )
        )
        result.extend(
            (
                ActionCard(
                    "check_existing_news",
                    "기존 소식 확인",
                    f"{evidence} 작성 건수와 실제 게시 수는 다릅니다. "
                    "보관함에서 현재 안내가 맞는지 먼저 확인하세요.",
                    "archive",
                ),
                ActionCard(
                    "add_real_news",
                    "실제 새 소식이 있다면 입력",
                    "숫자의 증감으로 새 소식을 만들지 않습니다. "
                    "실제 운영 변경이나 상품 소식이 있을 때만 사실을 입력하세요.",
                    "create",
                    "news",
                ),
            )
        )
    return tuple(result)


def clean_reason(reason: str) -> str:
    if len(reason) > MAX_KB_ENTRY_CHARS or contains_raw_secret(reason):
        message = "이유에는 비밀정보 없이 500자 이내의 짧은 설명만 적어 주세요."
        raise services.StoreActionError(message)
    return safe_kb_text(reason) if reason.strip() else ""


class ActionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)

    schema_version: Literal["aicmo.owner-action.v1"] = "aicmo.owner-action.v1"
    action_code: ActionCode
    decision: Decision
    reason: str = Field(max_length=MAX_KB_ENTRY_CHARS)
    recorded_by: str = Field(pattern=r"^web-user:[1-9][0-9]*$")
    request_key: str = Field(pattern=r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$")
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("reason")
    @classmethod
    def safe_reason(cls, value: str) -> str:
        return clean_reason(value)


def _available(receipt: ActionReceipt, report: ReviewedReport) -> None:
    if (
        receipt.report_sha256 != report.sha256
        or receipt.snapshot_sha256 != report.source.snapshot_sha256
        or receipt.action_code not in {card.code for card in cards(report)}
    ):
        message = "확인한 보고서나 행동이 달라졌습니다. 보고서를 다시 열어 주세요."
        raise services.StoreActionError(message)


def record_action(
    job: Job,
    action_code: ActionCode,
    decision: Decision,
    reason: str,
    request_key: uuid.UUID,
    report_sha256: str,
    snapshot_sha256: str,
    *,
    actor: AbstractBaseUser | AnonymousUser,
) -> ActionReceipt:
    from aicmo.store_app.report_services import (  # noqa: PLC0415 — report UI loads cards
        verify,
    )

    root = Path(settings.REPO_ROOT)
    with web_run_lock(root, job.run_id, blocking=False), transaction.atomic():
        current = services.owned_job(services.fresh_actor(actor), job.pk)
        if (
            current.workflow_id != "weekly-report"
            or current.store.pk != job.store.pk
            or current.inputs != job.inputs
            or current.store.client != job.store.client
        ):
            raise Http404
        try:
            receipt = ActionReceipt(
                action_code=action_code,
                decision=decision,
                reason=reason,
                recorded_by=f"web-user:{actor.pk}",
                request_key=str(request_key),
                report_sha256=report_sha256,
                snapshot_sha256=snapshot_sha256,
            )
        except ValueError:
            message = "행동 선택을 확인할 수 없습니다. 보고서를 다시 열어 주세요."
            raise services.StoreActionError(message) from None
        _available(receipt, verify(current))
        # Reuse the existing event table. Generic record_event applies prose redaction and
        # opens its own connection, so this typed receipt uses the one transaction below.
        with WorkflowStore(root / ".aicmo/runs.sqlite3").connect() as connection:
            connection.execute("begin immediate")
            _available(receipt, verify(current))
            rows = connection.execute(
                "select payload_json from events where run_id=? and event_type=? "
                "and json_extract(payload_json, '$.request_key')=?",
                (job.run_id, EVENT_TYPE, receipt.request_key),
            ).fetchall()
            if rows:
                if len(rows) != 1 or rows[0]["payload_json"] != receipt.model_dump_json():
                    message = "같은 선택 요청에서 내용이 바뀌었습니다. 보고서를 다시 열어 주세요."
                    raise services.StoreActionError(message)
                return receipt
            connection.execute(
                "insert into events(run_id,step_id,event_type,message,payload_json) "
                "values(?,null,?,?,?)",
                (
                    job.run_id,
                    EVENT_TYPE,
                    "사장님이 다음 행동의 선택 여부를 기록했습니다. "
                    "실행·게시·학습 기록이 아닙니다.",
                    receipt.model_dump_json(),
                ),
            )
        return receipt
