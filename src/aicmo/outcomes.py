from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal, Never

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from aicmo.errors import WorkflowExecutionError
from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.source_input import source_checked_date
from aicmo.store import WorkflowStore

type Channel = Literal["naver", "google-business", "instagram", "offline"]
type Count = Annotated[int, Field(strict=True, ge=0, le=1_000_000)]
METRICS = ("posts", "inquiries", "reservations", "coupon_redemptions")
CSV_COLUMNS = ("date", "channel", *METRICS)
MAX_CSV_BYTES = 32 * 1024
DAYS_PER_WEEK = 7
_CHANNEL: TypeAdapter[Channel] = TypeAdapter(Channel)
_LABELS = ("게시", "문의", "예약", "쿠폰 사용")
_STEP_ID = "outcomes"


def _fail(reason: str) -> Never:
    raise WorkflowExecutionError(_STEP_ID, reason) from None


def parse_channel(value: str) -> Channel:
    try:
        return _CHANNEL.validate_python(value)
    except ValueError:
        _fail("channel must be naver, google-business, instagram, or offline")


def _day(value: str) -> date:
    if re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", value) is None:
        reason = "date must be YYYY-MM-DD within 2000-2099"
        raise ValueError(reason)
    result = date.fromisoformat(value)
    if result > source_checked_date():
        reason = "future observations are not allowed (Asia/Seoul)"
        raise ValueError(reason)
    return result


def week_start_date(value: str) -> date:
    try:
        start = _day(value)
    except ValueError:
        _fail("week_start must be a past/current Monday, YYYY-MM-DD (Asia/Seoul)")
    if start.weekday() != 0:
        _fail("week must start on Monday")
    return start


class DailyOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    date: str
    channel: Channel
    posts: Count | None = None
    inquiries: Count | None = None
    reservations: Count | None = None
    coupon_redemptions: Count | None = None

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        _day(value)
        return value


class StoredOutcome(DailyOutcome):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(strict=True, ge=1)


class OutcomePreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["aicmo.outcome-preview.v1"] = "aicmo.outcome-preview.v1"

    client: str
    week_start: str
    channel: Channel
    encoding: Literal["UTF-8", "UTF-8 BOM"]
    source_sha256: str
    rows: tuple[DailyOutcome, ...]
    existing: tuple[StoredOutcome, ...]

    @property
    def confirmation_sha256(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


def _client(root: Path, client: str) -> None:
    parse_safe_id("client", client)
    config = resolve_inside_repo(root, "clients/${client}/config.md", {"client": client})
    if not config.is_file():
        _fail("client config is missing; onboard the store first")


def _csv_record(row: list[str], index: int) -> DailyOutcome:
    if len(row) != len(CSV_COLUMNS):
        _fail(f"invalid column count at CSV row {index}")
    counts = row[2:]
    if any(value and re.fullmatch(r"[0-9]{1,7}", value) is None for value in counts):
        _fail(f"invalid count at CSV row {index}")
    try:
        return DailyOutcome.model_validate(
            {
                "date": row[0],
                "channel": row[1],
                **dict(
                    zip(METRICS, [int(value) if value else None for value in counts], strict=True)
                ),
            }
        )
    except ValueError:
        _fail(f"invalid CSV row {index}; check date/channel/counts")


def _read_csv(
    source: Path, week_start: str, channel: Channel
) -> tuple[bytes, tuple[DailyOutcome, ...]]:
    start = week_start_date(week_start)
    try:
        with source.open("rb") as stream:
            raw = stream.read(MAX_CSV_BYTES + 1)
        if len(raw) > MAX_CSV_BYTES:
            _fail("CSV exceeds 32 KiB")
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    except (OSError, UnicodeError, csv.Error):
        _fail("cannot read CSV; use comma-separated UTF-8 or UTF-8 BOM")
    if not rows or tuple(rows[0]) != CSV_COLUMNS:
        _fail("CSV columns must be exactly: " + ",".join(CSV_COLUMNS))
    if not 1 <= len(rows) - 1 <= DAYS_PER_WEEK:
        _fail("CSV must contain 1-7 daily rows for one week and channel")
    parsed: list[DailyOutcome] = []
    for index, row in enumerate(rows[1:], start=2):
        record = _csv_record(row, index)
        if record.channel != channel or not start <= _day(record.date) < start + timedelta(days=7):
            _fail(f"wrong period/channel at CSV row {index}")
        if any(item.date == record.date for item in parsed):
            _fail(f"duplicate date at CSV row {index}")
        parsed.append(record)
    return raw, tuple(sorted(parsed, key=lambda item: item.date))


def _stored(
    connection: sqlite3.Connection,
    client: str,
    start: date,
    channel: Channel,
) -> tuple[StoredOutcome, ...]:
    rows = connection.execute(
        "select observed_on, payload_json, source_sha256, revision from manual_outcomes "
        "where client = ? and channel = ? and observed_on >= ? and observed_on < ? "
        "order by observed_on",
        (client, channel, start.isoformat(), (start + timedelta(days=7)).isoformat()),
    ).fetchall()
    result: list[StoredOutcome] = []
    for row in rows:
        try:
            item = DailyOutcome.model_validate_json(row["payload_json"])
            if item.date != row["observed_on"] or item.channel != channel:
                _fail("stored scope mismatch")
            result.append(
                StoredOutcome.model_validate(
                    {
                        **item.model_dump(),
                        "source_sha256": row["source_sha256"],
                        "revision": row["revision"],
                    }
                )
            )
        except ValueError:
            _fail("stored outcome is invalid; restore verified data before reporting")
    return tuple(result)


def _preview(
    connection: sqlite3.Connection,
    client: str,
    week_start: str,
    channel: Channel,
    raw: bytes,
    records: tuple[DailyOutcome, ...],
) -> OutcomePreview:
    return OutcomePreview(
        client=client,
        week_start=week_start,
        channel=channel,
        encoding="UTF-8 BOM" if raw.startswith(b"\xef\xbb\xbf") else "UTF-8",
        source_sha256=hashlib.sha256(raw).hexdigest(),
        rows=records,
        existing=_stored(connection, client, week_start_date(week_start), channel),
    )


def preview_outcomes(
    root: Path,
    store: WorkflowStore,
    client: str,
    week_start: str,
    channel: Channel,
    source: Path,
) -> OutcomePreview:
    _client(root, client)
    channel = parse_channel(channel)
    raw, records = _read_csv(source, week_start, channel)
    store.initialize()
    with store.connect() as connection:
        return _preview(connection, client, week_start, channel, raw, records)


def import_outcomes(
    root: Path,
    store: WorkflowStore,
    client: str,
    week_start: str,
    channel: Channel,
    source: Path,
    confirmation_sha256: str,
    *,
    replace: bool = False,
) -> int:
    _client(root, client)
    channel = parse_channel(channel)
    raw, records = _read_csv(source, week_start, channel)
    store.initialize()
    with store.connect() as connection:
        connection.execute("begin immediate")
        preview = _preview(connection, client, week_start, channel, raw, records)
        existing = {item.date: item for item in preview.existing}
        receipt = connection.execute(
            "select 1 from manual_outcome_imports where confirmation_sha256 = ? "
            "and client = ? and week_start = ? and channel = ? and source_sha256 = ?",
            (confirmation_sha256, client, week_start, channel, preview.source_sha256),
        ).fetchone()
        if receipt and all(
            item.date in existing
            and item.model_dump()
            == existing[item.date].model_dump(exclude={"revision", "source_sha256"})
            for item in records
        ):
            return 0
        if confirmation_sha256 != preview.confirmation_sha256:
            _fail("CSV or stored data changed; preview again before importing")
        changed = 0
        for item in records:
            old = existing.get(item.date)
            if old is not None:
                if item.model_dump() == old.model_dump(exclude={"revision", "source_sha256"}):
                    continue
                if not replace:
                    _fail("existing daily values differ; preview and use --replace to correct")
            connection.execute(
                "insert into manual_outcomes "
                "(client, observed_on, channel, payload_json, source_sha256, revision) "
                "values (?, ?, ?, ?, ?, ?) on conflict(client, observed_on, channel) "
                "do update set payload_json=excluded.payload_json, "
                "source_sha256=excluded.source_sha256, revision=excluded.revision",
                (
                    client,
                    item.date,
                    channel,
                    item.model_dump_json(),
                    preview.source_sha256,
                    old.revision + 1 if old else 1,
                ),
            )
            changed += 1
        if changed:
            connection.execute(
                "insert into manual_outcome_imports values (?, ?, ?, ?, ?)",
                (confirmation_sha256, client, week_start, channel, preview.source_sha256),
            )
    return changed


def _total(rows: tuple[StoredOutcome, ...], metric: str) -> tuple[int | None, int]:
    values = [getattr(item, metric) for item in rows if getattr(item, metric) is not None]
    return (sum(values) if values else None), len(values)


def weekly_outcomes_report(
    root: Path,
    store: WorkflowStore,
    client: str,
    week_start: str,
    channel: Channel,
) -> str:
    _client(root, client)
    channel = parse_channel(channel)
    start = week_start_date(week_start)
    store.initialize()
    with store.connect() as connection:
        connection.execute("begin")
        current = _stored(connection, client, start, channel)
        previous = _stored(connection, client, start - timedelta(days=7), channel)
    snapshot = json.dumps(
        {
            "schema_version": "aicmo.manual-outcomes.v1",
            "client": client,
            "week_start": week_start,
            "channel": channel,
            "current": [row.model_dump() for row in current],
            "previous": [row.model_dump() for row in previous],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(snapshot.encode()).hexdigest()
    lines = [
        f"# 수기 성과 주간 보고서 — {client}",
        "",
        "## 한 장 요약",
        "",
        f"기간: {week_start} ~ {(start + timedelta(days=6)).isoformat()} / {channel} / Asia/Seoul",
        "출처: 로컬 CLI에 저장된 사용자 제공 일별 수기 기록. 독립 검증된 실적이 아닙니다.",
        "기록자의 가게 권한과 현장 실적은 별도 확인 대상입니다.",
        "빈칸은 미입력이고 0은 확인한 0건입니다. 자료가 없는 날은 0으로 합산하지 않습니다.",
        "이 기록만으로 AI의 매출 기여나 원인과 결과를 판단할 수 없습니다.",
        "",
        "## 이번 주와 지난주",
        "",
        "| 지표 | 이번 주 관측 부분합 | 입력 일수 | 지난주 관측 부분합 | 입력 일수 | 증감률 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for metric, label in zip(METRICS, _LABELS, strict=True):
        total, days = _total(current, metric)
        prior, prior_days = _total(previous, metric)
        change = "비교 불가 (미입력 또는 지난주 0)"
        if days == prior_days == DAYS_PER_WEEK and prior and total is not None:
            change = f"{(total - prior) / prior * 100:+.1f}%"
        lines.append(
            f"| {label} | {total if total is not None else '미입력'} | {days}/7 | "
            f"{prior if prior is not None else '미입력'} | {prior_days}/7 | {change} |"
        )
    lines += [
        "",
        "## 일별 근거",
        "",
        "| 날짜 | 게시 | 문의 | 예약 | 쿠폰 사용 |",
        "|---|---:|---:|---:|---:|",
    ]
    by_date = {item.date: item for item in (*previous, *current)}
    for offset in range(-7, 7):
        day = (start + timedelta(days=offset)).isoformat()
        row = by_date.get(day)
        values = [getattr(row, metric) if row else None for metric in METRICS]
        lines.append(
            f"| {day} | "
            + " | ".join("미입력" if value is None else str(value) for value in values)
            + " |"
        )
    lines += [
        "",
        "## 자료 버전",
        "",
        f"집계 스냅샷 SHA-256: `{digest}`",
        "보고서는 생성 시점의 기록을 보존합니다. 자료 정정 후에는 새 run으로 다시 작성하세요.",
    ]
    for row in (*previous, *current):
        lines.append(f"- {row.date} / 수정 {row.revision} / CSV SHA-256 `{row.source_sha256}`")
    lines += [
        "",
        "## 다음 단계",
        "",
        "1. 사장님은 이번 주 빈칸을 확인하고 실제로 관측한 값만 보완하세요.",
        "2. 사장님은 숫자가 다르면 새 미리보기에서 기존값과 대조한 뒤 정정하세요.",
        "3. 검토자는 전달 전에 기간·채널·수기 근거를 확인하세요. "
        "원인 추정은 별도 증거가 필요합니다.",
    ]
    return "\n".join(lines) + "\n"
