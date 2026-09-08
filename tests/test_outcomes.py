from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from aicmo.cli import app
from aicmo.errors import WorkflowExecutionError
from aicmo.outcomes import (
    CSV_COLUMNS,
    DailyOutcome,
    OutcomeImportSource,
    OutcomeSnapshot,
    daily_outcome_csv,
    import_outcomes,
    import_outcomes_bytes,
    parse_channel,
    preview_outcomes,
    preview_outcomes_bytes,
    read_weekly_outcomes,
    weekly_outcomes_report,
)
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import write_text
from tests.test_llm_integration import VerdictAdapter

REPO = Path(__file__).resolve().parents[1]
WEEK = "2026-08-31"


@pytest.fixture
def store(tmp_path: Path) -> WorkflowStore:
    write_text(tmp_path / "clients/shop/config.md", "# Synthetic store\nVerified synthetic facts.")
    write_text(
        tmp_path / "clients/shop/brand-guidelines.md", "# Brand\nUse clear factual language."
    )
    return WorkflowStore(tmp_path / ".aicmo/runs.sqlite3")


def _csv(root: Path, rows: list[str], name: str = "counts.csv") -> Path:
    path = root / name
    write_text(path, ",".join(CSV_COLUMNS) + "\n" + "\n".join(rows) + "\n")
    return path


def _save(root: Path, store: WorkflowStore, rows: list[str], week: str = WEEK) -> Path:
    path = _csv(root, rows)
    preview = preview_outcomes(root, store, "shop", week, "naver", path)
    import_outcomes(root, store, "shop", week, "naver", path, preview.confirmation_sha256)
    return path


def test_preview_import_correction_and_replay_preserve_null_and_other_dates(
    tmp_path: Path,
    store: WorkflowStore,
) -> None:
    source = _csv(tmp_path, ["2026-08-31,naver,0,,2,0", "2026-09-01,naver,1,3,,0"])
    source.write_bytes(b"\xef\xbb\xbf" + source.read_bytes())
    preview = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source)
    assert preview.encoding == "UTF-8 BOM"
    assert preview.rows[0].posts == 0
    assert preview.rows[0].inquiries is None
    assert preview.existing == ()
    assert (
        import_outcomes(tmp_path, store, "shop", WEEK, "naver", source, preview.confirmation_sha256)
        == 2
    )
    assert (
        import_outcomes(tmp_path, store, "shop", WEEK, "naver", source, preview.confirmation_sha256)
        == 0
    )
    correction = _csv(tmp_path, ["2026-08-31,naver,0,5,2,0"], "correction.csv")
    changed = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", correction)
    with pytest.raises(WorkflowExecutionError, match="--replace"):
        import_outcomes(
            tmp_path, store, "shop", WEEK, "naver", correction, changed.confirmation_sha256
        )
    assert (
        import_outcomes(
            tmp_path,
            store,
            "shop",
            WEEK,
            "naver",
            correction,
            changed.confirmation_sha256,
            replace=True,
        )
        == 1
    )
    with pytest.raises(WorkflowExecutionError, match="preview again"):
        import_outcomes(
            tmp_path,
            store,
            "shop",
            WEEK,
            "naver",
            source,
            preview.confirmation_sha256,
            replace=True,
        )
    existing = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", correction).existing
    assert len(existing) == 2
    assert existing[0].inquiries == 5
    assert existing[0].revision == 2
    assert existing[1].inquiries == 3
    assert existing[1].revision == 1


@pytest.mark.parametrize(
    "bad",
    [
        "2026-08-31,naver,-1,0,0,0",
        "2026-08-31,naver,1.0,0,0,0",
        "2026-08-31,naver,True,0,0,0",
        "2026-08-31,naver,1000001,0,0,0",
        "2026-08-31,naver,=1+1,0,0,0",
        "2026-08-31,naver,\x000,0,0,0",
        "2026-08-31,naver,\ufeff0,0,0,0",
        "2026-08-31,naver,0,0,0",
        "2026-08-31,naver,0,0,0,0,customer-name",
        "2026-09-07,naver,0,0,0,0",
        "20260831,naver,0,0,0,0",
        "2026-02-30,naver,0,0,0,0",
        "2026-08-31,other,0,0,0,0",
        "2026-08-31,instagram,0,0,0,0",
    ],
)
def test_invalid_csv_is_rejected_without_echoing_cells(
    tmp_path: Path,
    store: WorkflowStore,
    bad: str,
) -> None:
    with pytest.raises(WorkflowExecutionError) as caught:
        preview_outcomes(tmp_path, store, "shop", WEEK, "naver", _csv(tmp_path, [bad]))
    assert bad not in str(caught.value)


@pytest.mark.parametrize("bad", [True, -1, 1.2, "1", 1_000_001])
def test_common_schema_rejects_invalid_numeric_types(bad: object) -> None:
    with pytest.raises(ValidationError):
        DailyOutcome.model_validate({"date": WEEK, "channel": "naver", "posts": bad})


def test_duplicate_header_dates_encoding_and_size_are_rejected(
    tmp_path: Path,
    store: WorkflowStore,
) -> None:
    header = ",".join(CSV_COLUMNS)
    for content in (
        (header + "\n" + "2026-08-31,naver,0,0,0,0\n" * 2).encode(),
        (header.replace("posts", "inquiries") + "\n2026-08-31,naver,0,0,0,0").encode(),
        "한글".encode("cp949"),
        b"x" * (32 * 1024 + 1),
        b"",
        header.encode(),
    ):
        source = tmp_path / "bad.csv"
        source.write_bytes(content)
        with pytest.raises(WorkflowExecutionError):
            preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source)


def test_stale_preview_and_transaction_rollback(tmp_path: Path, store: WorkflowStore) -> None:
    _save(tmp_path, store, ["2026-09-01,naver,1,1,1,1"])
    source = _csv(tmp_path, ["2026-08-31,naver,1,1,1,1", "2026-09-01,naver,2,2,2,2"])
    preview = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source)
    with pytest.raises(WorkflowExecutionError, match="--replace"):
        import_outcomes(tmp_path, store, "shop", WEEK, "naver", source, preview.confirmation_sha256)
    assert len(preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source).existing) == 1
    source.write_text(source.read_text().replace("2,2,2,2", "3,3,3,3"))
    with pytest.raises(WorkflowExecutionError, match="preview again"):
        import_outcomes(
            tmp_path,
            store,
            "shop",
            WEEK,
            "naver",
            source,
            preview.confirmation_sha256,
            replace=True,
        )


def test_concurrent_duplicate_imports_commit_once(tmp_path: Path, store: WorkflowStore) -> None:
    source = _csv(tmp_path, ["2026-08-31,naver,1,1,1,1"])
    preview = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(
                import_outcomes,
                tmp_path,
                store,
                "shop",
                WEEK,
                "naver",
                source,
                preview.confirmation_sha256,
            )
            for _ in range(2)
        ]
        assert sorted(job.result() for job in jobs) == [0, 1]
    assert (
        preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source).existing[0].revision == 1
    )


def test_other_writer_invalidates_preview_and_unknown_channel_fails(
    tmp_path: Path,
    store: WorkflowStore,
) -> None:
    source = _csv(tmp_path, ["2026-08-31,naver,1,1,1,1"])
    preview = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source)
    second = _csv(tmp_path, ["2026-09-01,naver,2,2,2,2"], "second.csv")
    other = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", second)
    import_outcomes(tmp_path, store, "shop", WEEK, "naver", second, other.confirmation_sha256)
    with pytest.raises(WorkflowExecutionError, match="preview again"):
        import_outcomes(tmp_path, store, "shop", WEEK, "naver", source, preview.confirmation_sha256)
    shown = CliRunner().invoke(
        app,
        [
            "outcomes",
            "--client",
            "shop",
            "--week-start",
            WEEK,
            "--from",
            str(source),
            "--repo",
            str(tmp_path),
        ],
    )
    assert shown.exit_code == 0
    assert "source_sha256:" in shown.output
    assert "confirmation_sha256:" in shown.output
    with pytest.raises(WorkflowExecutionError, match="channel must"):
        parse_channel("Customer name: Jane Doe")


def test_partial_zero_and_complete_week_comparisons(tmp_path: Path, store: WorkflowStore) -> None:
    report = weekly_outcomes_report(tmp_path, store, "shop", WEEK, "naver")
    assert "미입력 | 0/7" in report
    assert "%" not in report
    _save(tmp_path, store, ["2026-08-31,naver,0,,2,0"])
    report = weekly_outcomes_report(tmp_path, store, "shop", WEEK, "naver")
    assert "| 게시 | 0 | 1/7" in report
    assert "| 문의 | 미입력 | 0/7" in report
    for week, value in (("2026-08-24", 1), (WEEK, 2)):
        rows = [
            f"{date.fromisoformat(week) + timedelta(days=i)},naver,{value},0,2,0" for i in range(7)
        ]
        source = _csv(tmp_path, rows)
        preview = preview_outcomes(tmp_path, store, "shop", week, "naver", source)
        import_outcomes(
            tmp_path,
            store,
            "shop",
            week,
            "naver",
            source,
            preview.confirmation_sha256,
            replace=True,
        )
    report = weekly_outcomes_report(tmp_path, store, "shop", WEEK, "naver")
    assert "| 게시 | 14 | 7/7 | 7 | 7/7 | +100.0% |" in report
    assert "| 문의 | 0 | 7/7 | 0 | 7/7 | 비교 불가" in report
    assert "AI의 매출 기여나 원인과 결과를 판단할 수 없습니다" in report
    write_text(tmp_path / "clients/other/config.md", "# Other synthetic store")
    assert "미입력 | 0/7" in weekly_outcomes_report(tmp_path, store, "other", WEEK, "naver")
    assert "미입력 | 0/7" in weekly_outcomes_report(tmp_path, store, "shop", WEEK, "offline")


def test_cli_preview_import_and_native_report_review(tmp_path: Path, store: WorkflowStore) -> None:
    source = _csv(tmp_path, ["2026-08-31,naver,1,0,2,0"])
    args = [
        "outcomes",
        "--client",
        "shop",
        "--week-start",
        WEEK,
        "--from",
        str(source),
        "--repo",
        str(tmp_path),
    ]
    shown = CliRunner().invoke(app, [*args, "--json"])
    assert shown.exit_code == 0
    confirmation = json.loads(shown.output)["confirmation_sha256"]
    saved = CliRunner().invoke(app, [*args, "--confirm-sha", confirmation])
    assert saved.exit_code == 0
    assert "1 daily row(s) saved" in saved.output
    shown_again = CliRunner().invoke(app, [*args, "--json"])
    assert shown_again.exit_code == 0
    existing = json.loads(shown_again.output)["existing"][0]
    assert existing["input_kind"] == "cli_csv"
    assert isinstance(existing["recorded_at"], str)
    assert existing["recorded_by"] is None
    for directory in ("workflows", "agents", "prompts", "playbooks"):
        shutil.copytree(REPO / directory, tmp_path / directory)
    reviewer = VerdictAdapter(
        '{"schema_version":"aicmo.reviewer-decision.v1","verdict":"PASS",'
        '"reason":"Synthetic arithmetic review"}'
    )
    runner = WorkflowRunner(tmp_path, store, review_adapter=reviewer)
    assert (
        runner.run("weekly-report", "week-one", {"client": "shop", "week_start": WEEK}).status
        == "success"
    )
    path = tmp_path / "artifacts/week-one/weekly-report.md"
    before = path.read_bytes()
    manifest = json.loads((path.parent / "delivery-review.json").read_text())
    assert manifest["deliverable"] is True
    assert manifest["generator"] == "native"
    correction = _csv(tmp_path, ["2026-08-31,naver,9,0,2,0"])
    preview = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", correction)
    import_outcomes(
        tmp_path,
        store,
        "shop",
        WEEK,
        "naver",
        correction,
        preview.confirmation_sha256,
        replace=True,
    )
    assert runner.resume("week-one").status == "success"
    assert path.read_bytes() == before
    assert (
        runner.run("weekly-report", "week-two", {"client": "shop", "week_start": WEEK}).status
        == "success"
    )
    assert "| 게시 | 9 | 1/7" in (tmp_path / "artifacts/week-two/weekly-report.md").read_text(
        encoding="utf-8"
    )
    no_reviewer = WorkflowRunner(tmp_path, store)
    no_reviewer.run("weekly-report", "unreviewed", {"client": "shop", "week_start": WEEK})
    assert (
        json.loads((tmp_path / "artifacts/unreviewed/delivery-review.json").read_text())[
            "deliverable"
        ]
        is False
    )


def test_bytes_and_path_preserve_original_bytes_and_v1_confirmation(
    tmp_path: Path, store: WorkflowStore
) -> None:
    raw = (
        b"\xef\xbb\xbfdate,channel,posts,inquiries,reservations,coupon_redemptions\r\n"
        b"2026-08-31,naver,0,,2,0\r\n"
    )
    source = tmp_path / "original.csv"
    source.write_bytes(raw)
    path_preview = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", source)
    bytes_preview = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", raw)
    assert bytes_preview == path_preview
    assert bytes_preview.source_sha256 == hashlib.sha256(raw).hexdigest()
    # Captured v1 field order/compact encoding; nullable observation fields stay present.
    v1_json = (
        '{"schema_version":"aicmo.outcome-preview.v1","client":"shop",'
        '"week_start":"2026-08-31","channel":"naver","encoding":"UTF-8 BOM",'
        f'"source_sha256":"{hashlib.sha256(raw).hexdigest()}",'
        '"rows":[{"date":"2026-08-31","channel":"naver","posts":0,"inquiries":null,'
        '"reservations":2,"coupon_redemptions":0}],"existing":[]}'
    )
    assert bytes_preview.confirmation_sha256 == hashlib.sha256(v1_json.encode()).hexdigest()
    canonical = daily_outcome_csv(bytes_preview.rows[0])
    assert canonical == raw.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
    normalized = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", canonical)
    assert normalized.rows == bytes_preview.rows
    assert normalized.source_sha256 != bytes_preview.source_sha256
    assert normalized.confirmation_sha256 != bytes_preview.confirmation_sha256
    assert not store.db_path.exists()
    for invalid in (b"x" * (32 * 1024 + 1), raw + raw.split(b"\r\n")[1] + b"\r\n"):
        with pytest.raises(WorkflowExecutionError):
            preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", invalid)
    assert not store.db_path.exists()


def test_readonly_missing_legacy_and_migrated_ledgers_keep_v1_hashes(
    tmp_path: Path, store: WorkflowStore
) -> None:
    raw = daily_outcome_csv(DailyOutcome(date=WEEK, channel="naver", posts=0))
    with patch.object(
        WorkflowStore, "initialize", side_effect=AssertionError("read initialized DB")
    ):
        empty = read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver")
        assert empty.current == empty.previous == ()
        assert empty.totals["posts"].current is None
        assert not store.db_path.parent.exists()
    store.db_path.parent.mkdir()
    with closing(sqlite3.connect(store.db_path)) as connection, connection:
        connection.execute("create table unrelated (id integer)")
    before = store.db_path.read_bytes()
    assert read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver").current == ()
    assert store.db_path.read_bytes() == before
    # A genuine old schema has no provenance columns and must remain readable without ALTER.
    with closing(sqlite3.connect(store.db_path)) as connection, connection:
        connection.execute(
            "create table manual_outcomes (client text, observed_on text, channel text, "
            "payload_json text, source_sha256 text, revision integer, "
            "primary key(client, observed_on, channel))"
        )
        connection.execute(
            "insert into manual_outcomes values (?, ?, ?, ?, ?, ?)",
            (
                "shop",
                WEEK,
                "naver",
                '{"date":"2026-08-31","channel":"naver","posts":0}',
                "1" * 64,
                3,
            ),
        )
    before = store.db_path.read_bytes()
    with patch.object(WorkflowStore, "initialize", side_effect=AssertionError("read migrated DB")):
        legacy = read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver")
        preview = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", raw)
        report = weekly_outcomes_report(tmp_path, store, "shop", WEEK, "naver")
    assert store.db_path.read_bytes() == before
    assert legacy.current[0].input_kind is None
    assert legacy.current[0].recorded_at is None
    assert legacy.current[0].recorded_by is None
    assert "이전 기록 · 입력경로/기록시각 미확인" in report
    v1_existing = (
        '{"date":"2026-08-31","channel":"naver","posts":0,"inquiries":null,'
        '"reservations":null,"coupon_redemptions":null,"source_sha256":"'
        + "1" * 64
        + '","revision":3}'
    )
    v1_preview = (
        '{"schema_version":"aicmo.outcome-preview.v1","client":"shop",'
        '"week_start":"2026-08-31","channel":"naver","encoding":"UTF-8",'
        f'"source_sha256":"{hashlib.sha256(raw).hexdigest()}",'
        '"rows":[{"date":"2026-08-31","channel":"naver","posts":0,"inquiries":null,'
        '"reservations":null,"coupon_redemptions":null}],"existing":[' + v1_existing + "]}"
    )
    assert preview.confirmation_sha256 == hashlib.sha256(v1_preview.encode()).hexdigest()
    v1_snapshot = json.dumps(
        {
            "schema_version": "aicmo.manual-outcomes.v1",
            "client": "shop",
            "week_start": WEEK,
            "channel": "naver",
            "current": [json.loads(v1_existing)],
            "previous": [],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert f"집계 스냅샷 SHA-256: `{hashlib.sha256(v1_snapshot.encode()).hexdigest()}`" in report
    store.initialize()
    assert preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", raw) == preview
    assert read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver") == legacy
    assert weekly_outcomes_report(tmp_path, store, "shop", WEEK, "naver") == report
    with store.connect() as connection:
        row = connection.execute("select * from manual_outcomes").fetchone()
        assert row["source_sha256"] == "1" * 64
        assert row["revision"] == 3
        assert all(row[name] is None for name in ("input_kind", "recorded_at", "recorded_by"))


@pytest.mark.parametrize("damage", ["corrupt", "missing-column", "invalid-provenance"])
def test_readonly_does_not_present_damaged_ledger_as_empty(
    tmp_path: Path, store: WorkflowStore, damage: str
) -> None:
    store.db_path.parent.mkdir()
    if damage == "corrupt":
        store.db_path.write_bytes(b"synthetic invalid sqlite data")
    elif damage == "missing-column":
        with closing(sqlite3.connect(store.db_path)) as connection, connection:
            connection.execute("create table manual_outcomes (client text)")
    else:
        _save(tmp_path, store, ["2026-08-31,naver,0,0,0,0"])
        with store.connect() as connection:
            connection.execute("update manual_outcomes set recorded_by='not-a-web-recorder'")
    with pytest.raises((sqlite3.DatabaseError, WorkflowExecutionError)):
        read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver")


def test_provenance_noops_and_mixed_empty_csv_replays_preserve_real_zero(
    tmp_path: Path, store: WorkflowStore
) -> None:
    source = OutcomeImportSource(kind="web_csv", recorded_by="web-user:10155550123")
    first_blank = daily_outcome_csv(DailyOutcome(date=WEEK, channel="naver"))
    first = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", first_blank)
    assert not store.db_path.exists()
    assert (
        import_outcomes_bytes(
            tmp_path,
            store,
            "shop",
            WEEK,
            "naver",
            first_blank,
            first.confirmation_sha256,
            provenance=source,
        )
        == 0
    )
    with store.connect() as connection:
        assert connection.execute("select count(*) from manual_outcomes").fetchone()[0] == 0
        assert connection.execute("select count(*) from manual_outcome_imports").fetchone()[0] == 0
    raw = (",".join(CSV_COLUMNS) + "\n2026-08-31,naver,,,,\n2026-09-01,naver,0,0,0,0\n").encode()
    preview = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", raw)
    args = (tmp_path, store, "shop", WEEK, "naver", raw, preview.confirmation_sha256)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(import_outcomes_bytes, *args, provenance=source) for _ in range(2)]
        assert sorted(job.result() for job in jobs) == [0, 1]
    saved = read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver")
    assert len(saved.current) == 1
    row = saved.current[0]
    assert row.date == "2026-09-01"
    assert row.posts == 0
    assert row.recorded_at is not None
    assert row.input_kind == "web_csv"
    assert row.recorded_by == "web-user:10155550123"
    assert import_outcomes_bytes(*args, provenance=source) == 0
    # A different transport/recorder cannot overwrite provenance when observations are equal.
    assert import_outcomes_bytes(*args, provenance=OutcomeImportSource(kind="cli_csv")) == 0
    assert read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver") == saved
    _save(tmp_path, store, ["2026-08-31,naver,1,0,0,0"])
    with pytest.raises(WorkflowExecutionError, match="preview again"):
        import_outcomes_bytes(*args, provenance=source, replace=True)
    blank = daily_outcome_csv(DailyOutcome(date="2026-09-01", channel="naver"))
    change = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", blank)
    with pytest.raises(WorkflowExecutionError, match="--replace"):
        import_outcomes_bytes(
            tmp_path,
            store,
            "shop",
            WEEK,
            "naver",
            blank,
            change.confirmation_sha256,
            provenance=source,
        )
    assert (
        import_outcomes_bytes(
            tmp_path,
            store,
            "shop",
            WEEK,
            "naver",
            blank,
            change.confirmation_sha256,
            provenance=source,
            replace=True,
        )
        == 1
    )
    corrected = next(
        item
        for item in read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver").current
        if item.date == "2026-09-01"
    )
    assert corrected.posts is None
    assert corrected.revision == 2
    assert corrected.recorded_at is not None
    assert corrected.recorded_at >= row.recorded_at
    # A new, entirely blank date creates neither an observation nor an import receipt.
    empty_raw = daily_outcome_csv(DailyOutcome(date="2026-09-02", channel="naver"))
    empty = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", empty_raw)
    with store.connect() as connection:
        count = connection.execute("select count(*) from manual_outcome_imports").fetchone()[0]
    assert (
        import_outcomes_bytes(
            tmp_path,
            store,
            "shop",
            WEEK,
            "naver",
            empty_raw,
            empty.confirmation_sha256,
            provenance=source,
        )
        == 0
    )
    with store.connect() as connection:
        assert (
            connection.execute("select count(*) from manual_outcome_imports").fetchone()[0] == count
        )
    assert len(read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver").current) == 2


def test_v2_snapshot_totals_scope_provenance_and_frozen_report(
    tmp_path: Path, store: WorkflowStore
) -> None:
    for week, value in (("2026-08-24", 1), (WEEK, 2)):
        _save(
            tmp_path,
            store,
            [
                f"{date.fromisoformat(week) + timedelta(days=i)},naver,{value},0,,0"
                for i in range(7)
            ],
            week,
        )
    snapshot = read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver")
    assert snapshot.totals["posts"] == (14, 7, 7, 7, 100.0)
    assert snapshot.totals["inquiries"].change_percent is None
    assert snapshot.totals["reservations"] == (None, 0, None, 0, None)
    assert OutcomeSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    legacy_preview_source = daily_outcome_csv(DailyOutcome(date=WEEK, channel="naver", posts=2))
    before = preview_outcomes_bytes(tmp_path, store, "shop", WEEK, "naver", legacy_preview_source)
    with store.connect() as connection:
        connection.execute(
            "update manual_outcomes set input_kind='web_manual', recorded_by='web-user:2'"
        )
    changed_source = read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver")
    assert changed_source.snapshot_sha256 != snapshot.snapshot_sha256
    assert (
        preview_outcomes_bytes(
            tmp_path, store, "shop", WEEK, "naver", legacy_preview_source
        ).confirmation_sha256
        == before.confirmation_sha256
    )
    report = weekly_outcomes_report(tmp_path, store, "shop", WEEK, "naver", snapshot=snapshot)
    assert snapshot.snapshot_sha256 in report
    correction = _csv(tmp_path, ["2026-08-31,naver,9,0,,0"])
    preview = preview_outcomes(tmp_path, store, "shop", WEEK, "naver", correction)
    import_outcomes(
        tmp_path,
        store,
        "shop",
        WEEK,
        "naver",
        correction,
        preview.confirmation_sha256,
        replace=True,
    )
    assert (
        weekly_outcomes_report(tmp_path, store, "shop", WEEK, "naver", snapshot=snapshot) == report
    )
    assert (
        read_weekly_outcomes(tmp_path, store, "shop", WEEK, "naver").snapshot_sha256
        != snapshot.snapshot_sha256
    )
    for changes in (
        {"current": [snapshot.current[0], snapshot.current[0]]},
        {"current": snapshot.previous},
        {"previous": snapshot.current},
        {"channel": "offline"},
        {"current": [*snapshot.current, snapshot.current[-1]]},
    ):
        with pytest.raises(ValidationError):
            OutcomeSnapshot.model_validate({**snapshot.model_dump(), **changes})
    with pytest.raises(WorkflowExecutionError, match="scope differs"):
        weekly_outcomes_report(tmp_path, store, "shop", WEEK, "offline", snapshot=snapshot)
    for source in ({"kind": "web_csv"}, {"kind": "cli_csv", "recorded_by": "web-user:1"}):
        with pytest.raises(ValidationError):
            OutcomeImportSource.model_validate(source)
