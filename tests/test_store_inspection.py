from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import cast

import pytest
from scripts import rehearse_store_recovery as recovery
from typer.testing import CliRunner

from aicmo.adapters import CommandAdapter
from aicmo.cli import app
from aicmo.db import StoreDb
from aicmo.paths import native_io_path
from aicmo.store_inspection import inspect_store
from tests.test_store_recovery_rehearsal import (
    rehearsal as rehearsal,  # noqa: PLC0414 — expose pytest fixture
)

WEB, ENGINE = recovery.DB_PATHS
NOW = datetime.now(UTC) + timedelta(days=1)
SECRET = "sk-syntheticInspectionSecretNeverReflect123456789"
JOB_COUNTS = dict.fromkeys(
    ("queued", "running", "waiting_approval", "success", "needs_work", "failed", "cancelled"), 0
)
WORKFLOW_COUNTS = dict.fromkeys(("local-store-pack", "weekly-report", "local-pack-feedback"), 0)
ONBOARDING_COUNTS = dict.fromkeys(("draft", "queued", "running", "failed", "complete"), 0)
RUN_COUNTS = dict.fromkeys(("running", "success", "failed", "waiting_approval", "cancelled"), 0)


def _copy_databases(rehearsal: Path, destination: Path) -> Path:
    # Diagnostic mutations below affect only new copies, never the recovery evidence.
    native_io_path(destination / ".aicmo").mkdir(parents=True)
    for relative in recovery.DB_PATHS:
        native_io_path(destination / relative).write_bytes(
            native_io_path(rehearsal / "restored" / relative).read_bytes()
        )
    return destination


def _bodies(root: Path) -> dict[str, str]:
    return {
        relative: hashlib.sha256(native_io_path(root / relative).read_bytes()).hexdigest()
        for relative in recovery.DB_PATHS
    }


def _state(root: Path) -> dict[str, tuple[str, str]]:
    return {
        relative: recovery.database_state(root / relative) for relative in recovery.DB_PATHS
    }


def test_actual_mixed_fixture_is_read_only_and_does_not_claim_worker_health(
    rehearsal: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = rehearsal / "restored"
    before, logical = _bodies(root), _state(root)
    with closing(recovery.read_database(root / WEB)) as connection:
        queued_at = connection.execute(
            "select created_at from store_app_job where state='queued'"
        ).fetchone()[0]
    now = datetime.fromisoformat(queued_at).replace(tzinfo=UTC) + timedelta(seconds=90)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("inspection must not initialize a database or invoke a provider")

    monkeypatch.setattr(StoreDb, "initialize", forbidden)
    monkeypatch.setattr(CommandAdapter, "generate", forbidden)
    result = inspect_store(root, now=now)
    assert result["schema_version"] == "aicmo.store-inspection.v1"
    assert result["inspection_status"] == "available"
    assert result["web"] == {
        "query_status": "available",
        "summary": {
            "job_counts": JOB_COUNTS | {"queued": 1, "success": 1},
            "workflow_counts": WORKFLOW_COUNTS | {"local-store-pack": 2},
            "cancellation_pending": 0,
            "oldest_queued_age_seconds": 90,
            "onboarding_counts": ONBOARDING_COUNTS,
        },
    }
    assert result["engine"] == {
        "query_status": "available",
        "summary": {
            "run_counts": RUN_COUNTS | {"success": 1},
            "running_steps": 0,
            "running_without_heartbeat": 0,
            "oldest_running_heartbeat_age_seconds": None,
        },
    }
    assert result["worker_process"] == "unverified"
    assert result["provider_cost"] == "unavailable"
    assert result["snapshot_scope"] == "separate_read_transactions"
    assert (_bodies(root), _state(root)) == (before, logical)
    encoded = json.dumps(result)
    assert str(root) not in encoded
    assert "synthetic-recovery-owner" not in encoded


def test_existing_supported_schema_with_no_rows_reports_zero(
    rehearsal: Path, tmp_path: Path
) -> None:
    root = _copy_databases(rehearsal, tmp_path / "empty")
    for relative in recovery.DB_PATHS:
        with closing(sqlite3.connect(native_io_path(root / relative))) as connection:
            tables = connection.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            ).fetchall()
            for (table,) in tables:
                quoted = str(table).replace('"', '""')
                connection.execute(f'DELETE FROM "{quoted}"')  # noqa: S608 — quoted own-fixture identifier
            connection.commit()
    before, logical = _bodies(root), _state(root)
    result = inspect_store(root, now=NOW)
    assert result["inspection_status"] == "available"
    assert result["web"] == {
        "query_status": "available",
        "summary": {
            "job_counts": JOB_COUNTS,
            "workflow_counts": WORKFLOW_COUNTS,
            "cancellation_pending": 0,
            "oldest_queued_age_seconds": None,
            "onboarding_counts": ONBOARDING_COUNTS,
        },
    }
    assert result["engine"] == {
        "query_status": "available",
        "summary": {
            "run_counts": RUN_COUNTS,
            "running_steps": 0,
            "running_without_heartbeat": 0,
            "oldest_running_heartbeat_age_seconds": None,
        },
    }
    assert (_bodies(root), _state(root)) == (before, logical)


def test_missing_databases_are_not_created(tmp_path: Path) -> None:
    root = tmp_path / "not-created"
    result = inspect_store(root, now=NOW)
    assert result["inspection_status"] == "needs_review"
    for component in ("web", "engine"):
        assert result[component] == {"query_status": "missing", "summary": None}
    assert not root.exists()
    assert list(tmp_path.iterdir()) == []


def test_partial_schema_discards_only_its_component_summary(
    rehearsal: Path, tmp_path: Path
) -> None:
    for index, (component, relative, statement) in enumerate(
        (
            ("web", WEB, "alter table store_app_job rename column created_at to legacy_created"),
            ("engine", ENGINE, "alter table steps rename column locked_at to legacy_locked"),
        )
    ):
        root = _copy_databases(rehearsal, tmp_path / str(index))
        with closing(sqlite3.connect(native_io_path(root / relative))) as connection:
            connection.execute(statement)
            connection.commit()
        before, logical = _bodies(root), _state(root)
        result = inspect_store(root, now=NOW)
        assert result["inspection_status"] == "needs_review"
        assert result[component] == {"query_status": "schema_unsupported", "summary": None}
        other = "engine" if component == "web" else "web"
        assert cast("dict[str, object]", result[other])["query_status"] == "available"
        assert (_bodies(root), _state(root)) == (before, logical)


def test_corruption_and_real_exclusive_lock_fail_safely_with_bounded_wait(
    rehearsal: Path, tmp_path: Path
) -> None:
    root = _copy_databases(rehearsal, tmp_path / "unavailable")
    web = native_io_path(root / WEB)
    original = web.read_bytes()
    web.write_bytes(SECRET.encode())
    before = _bodies(root)
    corrupt = inspect_store(root, now=NOW)
    assert corrupt["inspection_status"] == "needs_review"
    assert corrupt["web"] == {"query_status": "unavailable", "summary": None}
    assert cast("dict[str, object]", corrupt["engine"])["query_status"] == "available"
    assert SECRET not in json.dumps(corrupt)
    assert _bodies(root) == before
    web.write_bytes(original)
    with closing(sqlite3.connect(native_io_path(root / ENGINE))) as writer:
        assert writer.execute("pragma journal_mode=delete").fetchone() == ("delete",)
        before, logical = _bodies(root), _state(root)
        writer.execute("begin exclusive")
        try:
            started = time.monotonic()
            locked = inspect_store(root, now=NOW)
            assert time.monotonic() - started < 5
            assert locked["inspection_status"] == "needs_review"
            assert locked["engine"] == {"query_status": "unavailable", "summary": None}
            assert cast("dict[str, object]", locked["web"])["query_status"] == "available"
        finally:
            writer.rollback()
    assert (_bodies(root), _state(root)) == (before, logical)


def test_committed_wal_is_read_without_checkpoint_or_heartbeat_claim(
    rehearsal: Path, tmp_path: Path
) -> None:
    root = _copy_databases(rehearsal, tmp_path / "wal")
    database = native_io_path(root / ENGINE)
    with closing(sqlite3.connect(database)) as writer:
        assert writer.execute("pragma journal_mode=wal").fetchone() == ("wal",)
        writer.execute("pragma wal_autocheckpoint=0")
        steps = writer.execute("select run_id,step_id from steps order by step_order limit 2")
        first, second = steps.fetchall()
        writer.execute("update runs set status='running'")
        writer.execute(
            "update steps set status='running',locked_by='synthetic-worker',locked_at=? "
            "where run_id=? and step_id=?",
            ((NOW - timedelta(seconds=90)).strftime("%Y-%m-%d %H:%M:%S"), *first),
        )
        writer.execute(
            "update steps set status='running',locked_by='synthetic-worker',locked_at=null "
            "where run_id=? and step_id=?",
            second,
        )
        writer.commit()
        wal = native_io_path(root / f"{ENGINE}-wal")
        assert wal.stat().st_size > 32
        before, logical, wal_before = _bodies(root), _state(root), wal.read_bytes()
        result = inspect_store(root, now=NOW)
        assert result["inspection_status"] == "available"
        assert result["engine"] == {
            "query_status": "available",
            "summary": {
                "run_counts": RUN_COUNTS | {"running": 1},
                "running_steps": 2,
                "running_without_heartbeat": 1,
                "oldest_running_heartbeat_age_seconds": 90,
            },
        }
        assert result["worker_process"] == "unverified"
        assert (_bodies(root), _state(root), wal.read_bytes()) == (before, logical, wal_before)


def test_unknown_states_and_invalid_timestamps_are_not_reflected(
    rehearsal: Path, tmp_path: Path
) -> None:
    cases = (
        ("web", WEB, "update store_app_job set state=? where state='queued'", SECRET),
        ("web", WEB, "update store_app_job set created_at=? where state='queued'", SECRET),
        (
            "web",
            WEB,
            "update store_app_job set created_at=? where state='queued'",
            "2999-01-01 00:00:00",
        ),
        ("engine", ENGINE, "update runs set status=?", SECRET),
        (
            "engine",
            ENGINE,
            "update steps set status='running',locked_by='synthetic',locked_at=?",
            SECRET,
        ),
    )
    for index, (component, relative, statement, value) in enumerate(cases):
        root = _copy_databases(rehearsal, tmp_path / str(index))
        with closing(sqlite3.connect(native_io_path(root / relative))) as connection:
            connection.execute(statement, (value,))
            connection.commit()
        before, logical = _bodies(root), _state(root)
        result = inspect_store(root, now=NOW)
        assert result["inspection_status"] == "needs_review"
        assert result[component] == {"query_status": "invalid_data", "summary": None}
        assert value not in json.dumps(result)
        assert (_bodies(root), _state(root)) == (before, logical)


def test_cli_json_exit_status_and_read_only_scope(rehearsal: Path, tmp_path: Path) -> None:
    cli = CliRunner()
    root = rehearsal / "restored"
    before, logical = _bodies(root), _state(root)
    available = cli.invoke(app, ["inspect-store", "--repo", str(root)])
    assert available.exit_code == 0, available.output
    assert json.loads(available.stdout)["inspection_status"] == "available"
    assert (_bodies(root), _state(root)) == (before, logical)
    absent = tmp_path / "missing"
    missing = cli.invoke(app, ["inspect-store", "--repo", str(absent)])
    assert missing.exit_code == 1
    assert json.loads(missing.stdout)["web"] == {"query_status": "missing", "summary": None}
    assert not absent.exists()


def test_query_budget_interrupts_actual_sqlite_work_without_modifying_rows(
    rehearsal: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_databases(rehearsal, tmp_path / "query-budget")
    with closing(sqlite3.connect(native_io_path(root / ENGINE))) as writer:
        writer.executemany(
            "insert into runs(run_id,workflow_id,status,inputs_json) "
            "values(?,'local-store-pack','running','{}')",
            [(f"synthetic-budget-{index}",) for index in range(2000)],
        )
        writer.commit()
    before, logical = _bodies(root), _state(root)
    ticks = count(0.0, 3.0)
    observed: list[float] = []

    def clock() -> float:
        value = next(ticks)
        observed.append(value)
        return value

    with monkeypatch.context() as clock_patch:
        clock_patch.setattr("aicmo.store_inspection.time.monotonic", clock)
        result = inspect_store(root, now=NOW)
    assert len(observed) >= 3  # Two deadlines and at least one real SQLite progress callback.
    assert result["inspection_status"] == "needs_review"
    assert result["engine"] == {"query_status": "unavailable", "summary": None}
    assert "interrupted" not in json.dumps(result)
    assert (_bodies(root), _state(root)) == (before, logical)


def test_sqlite_patch_status_is_reported_without_overclaiming_other_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for version, expected in (
        ((3, 44, 5), "not_confirmed"),
        ((3, 44, 6), "included"),
        ((3, 45, 0), "not_confirmed"),
        ((3, 50, 6), "not_confirmed"),
        ((3, 50, 7), "included"),
        ((3, 50, 99), "included"),
        ((3, 51, 2), "not_confirmed"),
        ((3, 51, 3), "included"),
        ((3, 52, 0), "included"),
    ):
        version_text = ".".join(map(str, version))
        monkeypatch.setattr(sqlite3, "sqlite_version_info", version)
        monkeypatch.setattr(sqlite3, "sqlite_version", version_text)
        result = inspect_store(tmp_path, now=NOW)
        assert result["runtime"] == {"sqlite_version": version_text, "wal_reset_fix": expected}
        assert result["worker_process"] == "unverified"
    assert list(tmp_path.iterdir()) == []
