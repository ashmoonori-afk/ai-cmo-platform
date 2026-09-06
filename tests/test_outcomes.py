from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from aicmo.cli import app
from aicmo.errors import WorkflowExecutionError
from aicmo.outcomes import (
    CSV_COLUMNS,
    DailyOutcome,
    import_outcomes,
    parse_channel,
    preview_outcomes,
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
