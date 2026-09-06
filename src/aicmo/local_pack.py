from __future__ import annotations

import json
import re
import unicodedata
from html import escape
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from aicmo.errors import WorkflowExecutionError
from aicmo.source_input import JsonValue

WORKFLOW_ID = "local-store-pack"
MAX_PACK_BYTES = 12 * 1024
LOW_CAPACITY_MINUTES = 20
INPUT_STEP = "inputs"
DRAFT_STEP = "drafts"


def _visible_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if (
        not any(unicodedata.category(char)[0] in "LNPS" for char in normalized)
        or any(unicodedata.category(char) == "Cc" and char not in "\r\n\t" for char in normalized)
    ):
        reason = "text must contain visible content without control characters"
        raise ValueError(reason)
    return value


Text = Annotated[str, Field(min_length=1, max_length=1200), AfterValidator(_visible_text)]


class PackBrief(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    channel: Literal["naver"] = "naver"
    owner_minutes: int = Field(ge=5, le=240)
    photo_available: bool = False
    facts: list[Text] = Field(min_length=1, max_length=2)
    reviews: list[Text] = Field(default_factory=list, max_length=5)

    @property
    def news_count(self) -> int:
        # ponytail: conservative product capacity, tune only from observed owner effort.
        return min(
            len(self.facts),
            1 if self.owner_minutes < LOW_CAPACITY_MINUTES or not self.photo_available else 2,
        )

    @property
    def reply_count(self) -> int:
        return min(len(self.reviews), 2 if self.owner_minutes < LOW_CAPACITY_MINUTES else 5)


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    title: Text
    body: Text
    cta: Text
    period: Text
    source_index: int = Field(ge=0, le=1)
    photo_instruction: Literal["사진 파일이 없습니다. 실제 사진은 직접 선택하세요."]
    visual_asset_status: Literal["unavailable"]
    status: Literal["draft"]


class ReplyItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    review_index: int = Field(ge=0, le=4)
    body: Text
    status: Literal["draft"]


class WeeklyAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    action: Text
    when: Text
    minutes: int = Field(ge=1, le=240)


class LocalPack(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    schema_version: Literal["aicmo.local-pack.v1"]
    summary: Text
    channel: Literal["naver"]
    sources: list[Text] = Field(min_length=1, max_length=2)
    news: list[NewsItem] = Field(min_length=1, max_length=2)
    replies: list[ReplyItem] = Field(max_length=5)
    weekly_actions: list[WeeklyAction] = Field(min_length=2, max_length=3)
    next_steps: list[Text] = Field(min_length=2, max_length=3)


def _unique_pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            reason = "duplicate JSON key"
            raise ValueError(reason)
        result[key] = value
    return result


def read_brief_file(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_PACK_BYTES + 4)
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeError):
        raise WorkflowExecutionError(INPUT_STEP, "cannot read UTF-8 local pack brief") from None
    parse_brief({"brief_json": text})
    return text


def parse_brief(inputs: dict[str, str]) -> PackBrief:
    raw = inputs.get("brief_json", "")
    if len(raw.encode("utf-8")) > MAX_PACK_BYTES:
        raise WorkflowExecutionError(INPUT_STEP, "local pack brief exceeds 12 KiB")
    try:
        json.loads(raw, object_pairs_hook=_unique_pairs)
        return PackBrief.model_validate_json(raw)
    except (ValueError, RecursionError):
        # Never echo raw customer input from Pydantic's error payload.
        raise WorkflowExecutionError(
            INPUT_STEP,
            "invalid local pack brief: check channel, capacity, facts and review limits",
        ) from None


def validate_pack(text: str, inputs: dict[str, str]) -> LocalPack:
    brief = parse_brief(inputs)
    if len(text.encode("utf-8")) > MAX_PACK_BYTES:
        raise WorkflowExecutionError(
            DRAFT_STEP, "local pack exceeds 12 KiB; shorten and regenerate"
        )
    try:
        json.loads(text, object_pairs_hook=_unique_pairs)
        pack = LocalPack.model_validate_json(text)
    except (ValueError, RecursionError):
        raise WorkflowExecutionError(DRAFT_STEP, "invalid local pack JSON contract") from None
    if (
        pack.sources != brief.facts
        or len(pack.news) != brief.news_count
        or [item.source_index for item in pack.news] != list(range(brief.news_count))
        or [item.review_index for item in pack.replies] != list(range(brief.reply_count))
        or sum(item.minutes for item in pack.weekly_actions) > brief.owner_minutes
    ):
        raise WorkflowExecutionError(
            DRAFT_STEP, "local pack differs from supplied facts or capacity"
        )
    return pack


def _markdown_text(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", escape(text, quote=False))


def render_pack(pack: LocalPack) -> dict[str, str]:
    sections = [
        "# 가게 주간 실행팩",
        "## 한 장 요약",
        _markdown_text(pack.summary),
        "AI가 작성하고 검토·승인한 문안입니다. 외부 게시 완료를 뜻하지 않습니다.",
        "채널: 네이버 스마트플레이스 / 사진 파일: 제공되지 않음",
    ]
    files: dict[str, str] = {}
    for index, item in enumerate(pack.news, 1):
        copy = f"{item.title}\n\n{item.body}\n\n{item.cta}\n"
        files[f"news-{index}.txt"] = copy
        sections.extend(
            [
                f"## 소식 {index}",
                _markdown_text(copy),
                f"기간: {_markdown_text(item.period)}",
                f"출처: {_markdown_text(pack.sources[item.source_index])}",
                f"사진 안내: {_markdown_text(item.photo_instruction)}",
                "상태: 승인된 문안 / 직접 게시 전 최종 확인",
            ]
        )
    for item in pack.replies:
        files[f"reply-{item.review_index + 1}.txt"] = item.body + "\n"
        sections.extend([f"## 리뷰 {item.review_index + 1} 답글", _markdown_text(item.body)])
    if not pack.replies:
        sections.extend(["## 리뷰 답글", "입력된 리뷰가 없어 답글을 만들지 않았습니다."])
    sections.append("## 주간 실행 카드")
    sections.extend(
        f"- {_markdown_text(a.when)}: {_markdown_text(a.action)} ({a.minutes}분 계획)"
        for a in pack.weekly_actions
    )
    sections.extend(
        [
            "## 게시 안내",
            "사장님 계정으로 https://smartplace.naver.com/ 에 접속해 내 업체를 선택하세요. "
            "새소식 또는 해당 리뷰의 답글 화면에서 텍스트를 붙여 넣고 가격·기간·대상을 확인하세요. "
            "사진은 사용 권리를 확인한 실제 파일을 직접 선택하세요. "
            "최종 등록은 사장님이 직접 누릅니다. 답글 등록 시 고객에게 알림이 갈 수 있습니다.",
            "리뷰 원문을 별도 파일로 첨부하지 않습니다. 문안의 잔여 개인정보도 확인하세요.",
            "## 다음 단계",
            *(f"- {_markdown_text(step)}" for step in pack.next_steps),
        ]
    )
    files["guide.md"] = "\n\n".join(sections) + "\n"
    return files
