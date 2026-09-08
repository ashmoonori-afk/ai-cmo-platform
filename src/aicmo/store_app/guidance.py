from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import NamedTuple, TypedDict, cast

from django.conf import settings
from django.core.exceptions import ValidationError

from aicmo.errors import AicmoError
from aicmo.local_pack import LOW_CAPACITY_MINUTES
from aicmo.paths import native_io_path, parse_safe_id, resolve_inside_repo
from aicmo.quota import current_period, quota_status
from aicmo.store import WorkflowStore
from aicmo.store_app.forms import StorePurposeForm
from aicmo.store_app.models import Job, Store
from aicmo.store_app.services import StoreActionError, configured_commands

INTENTS = {
    "news": (
        "이번 주 소식",
        "이번 주 실제로 알릴 소식을 적어 주세요. 새 소식이 없으면 만들지 않아도 됩니다.",
    ),
    "menu": (
        "신메뉴·상품",
        "새로 알릴 상품이 있다면 이름·가격·판매 시작일을 직접 확인해 적어 주세요.",
    ),
    "closure": (
        "영업·휴무 안내",
        "영업시간이나 휴무가 바뀐다면 정확한 날짜·시간·다시 여는 날을 확인해 적어 주세요.",
    ),
    "event": (
        "행사·이벤트",
        "실제 행사가 있다면 기간·대상·가격·조건을 확인해 적어 주세요. 없는 혜택을 만들지 마세요.",
    ),
    "review": (
        "소식과 리뷰 답글",
        "현재 리뷰 답글은 실제 이번 주 안내 1건과 함께 준비합니다. "
        "소식 없이 리뷰만 만드는 기능은 아직 없습니다.",
    ),
}
_MAX_PROFILE_BYTES = 64 * 1024


class ProfileHints(NamedTuple):
    objective: str = ""
    minutes: int | None = None


class Allowance(TypedDict):
    code: str
    detail: str
    blocked: bool


def profile_hints(store: Store) -> ProfileHints:  # noqa: PLR0911 — explicit safe fallbacks
    try:
        client = parse_safe_id("client", store.client)
        root = Path(settings.REPO_ROOT)
        expected = root / "clients" / client / "config.md"
        path = resolve_inside_repo(root, f"clients/{client}/config.md", {})
        if path != expected or not native_io_path(path).is_file():
            return ProfileHints()
        with native_io_path(path).open("rb") as stream:
            raw = stream.read(_MAX_PROFILE_BYTES + 1)
        if len(raw) > _MAX_PROFILE_BYTES:
            return ProfileHints()
        content = raw.decode("utf-8-sig")
        if any(
            (
                unicodedata.category(char).startswith("C")
                or unicodedata.category(char) in {"Zl", "Zp"}
            )
            and char not in "\r\n\t"
            for char in content
        ):
            return ProfileHints()
        fields: dict[str, list[str]] = {}
        for line in content.splitlines():
            match = re.fullmatch(
                r"- \*\*(프로필 스키마|이번 목적|주당 마케팅 여력)\*\*: ([^\r\n]+)", line
            )
            if match:
                fields.setdefault(match[1], []).append(match[2])
        if fields.get("프로필 스키마") != ["aicmo.smb-profile.v1"] or any(
            len(fields.get(name, [])) != 1 for name in ("이번 목적", "주당 마케팅 여력")
        ):
            return ProfileHints()
        objective = str(StorePurposeForm().fields["objective"].clean(fields["이번 목적"][0]))
        capacity = re.fullmatch(r"([0-9]{1,3})분", fields["주당 마케팅 여력"][0])
        if capacity is None:
            return ProfileHints()
        minutes = int(capacity[1])
        StorePurposeForm().fields["weekly_capacity"].clean(minutes)
    except (AicmoError, OSError, ValueError, ValidationError):
        return ProfileHints()
    return ProfileHints(objective, minutes)


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        reason = "invalid allowance count"
        raise ValueError(reason)
    return value


def allowance(store: Store) -> Allowance:
    database = Path(settings.REPO_ROOT) / ".aicmo/runs.sqlite3"
    try:
        try:
            database.stat()
        except FileNotFoundError:
            return {
                "code": "not_started",
                "detail": "사용 건수 기록이 아직 없습니다. 작업 시작 시 다시 확인합니다.",
                "blocked": False,
            }
        status = quota_status(
            WorkflowStore(database, read_only=True), store.client, current_period()
        )
        period = str(status["period"])
        if status["mode"] == "unmetered_local":
            return {
                "code": "unmetered",
                "detail": "이 가게의 사용 건수 제한이 설정되지 않았습니다. "
                "사용 범위·요금은 운영자에게 확인해 주세요.",
                "blocked": False,
            }
        if status["pack_limit"] is None:
            return {
                "code": "missing_period",
                "detail": f"{period} 사용 가능 건수가 아직 설정되지 않았습니다. "
                "운영자에게 요청해 주세요.",
                "blocked": True,
            }
        packs = status["packs"]
        if not isinstance(packs, dict):
            return {
                "code": "unavailable",
                "detail": "사용 가능 건수를 확인하지 못했습니다. 운영자에게 문의해 주세요.",
                "blocked": True,
            }
        counts = cast("dict[str, object]", packs)
        reserved, consumed = _count(counts["reserved"]), _count(counts["consumed"])
        remaining = max(0, _count(status["pack_limit"]) - reserved - consumed)
        drafts = max(0, _count(status["draft_limit"]) - _count(status["draft_used"]))
        detail = (
            f"{period} · 새 작업 {remaining}건 가능 · 진행 중 예약 {reserved}건 "
            f"· 저장 완료 {consumed}건 · 작성 시도 {drafts}회 남음."
        )
        blocked = remaining == 0 or drafts == 0
        if blocked:
            detail += " 새 요청에 쓸 건수가 부족합니다. 운영자에게 확인해 주세요."
    except (AicmoError, OSError, ValueError, IndexError, KeyError, TypeError, sqlite3.Error):
        return {
            "code": "unavailable",
            "detail": "사용 가능 건수를 확인하지 못했습니다. 운영자에게 문의해 주세요.",
            "blocked": True,
        }
    return {"code": "exhausted" if blocked else "available", "detail": detail, "blocked": blocked}


def active_job(store: Store) -> Job | None:
    return (
        Job.objects.filter(store=store, state__in=["queued", "running", "waiting_approval"])
        .order_by("created_at")
        .first()
    )


def service_ready() -> bool:
    try:
        configured_commands()
    except StoreActionError:
        return False
    return True


def task_cards(hints: ProfileHints) -> list[dict[str, str]]:
    order = ("news", "closure", "review")
    if hints.objective == "리뷰 답글 준비":
        order = ("review", "news", "closure")
    elif hints.objective == "방문·문의 안내":
        order = ("closure", "news", "review")
    replies = 2 if hints.minutes is not None and hints.minutes < LOW_CAPACITY_MINUTES else 5
    return [
        {
            "intent": key,
            "title": INTENTS[key][0],
            "detail": INTENTS[key][1],
            "scope": f"소식 1건 · 사진 선택 1장 · 입력한 리뷰의 답글 최대 {replies}개",
        }
        for key in order
    ]
