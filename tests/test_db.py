from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from typing import cast
from unittest.mock import Mock, patch

import pytest

from aicmo import db
from aicmo.db import StoreDb, _enable_wal  # pyright: ignore[reportPrivateUsage]
from aicmo.schema import SCHEMA


@pytest.mark.parametrize("read_only", [False, True])
def test_configuration_failure_closes_connection(tmp_path: Path, read_only: bool) -> None:
    connection = sqlite3.connect(tmp_path / "runs.sqlite3")

    def deny_setup(
        action: int,
        name: str | None,
        _value: str | None,
        _database: str | None,
        _trigger: str | None,
    ) -> int:
        return (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_PRAGMA and name == "foreign_keys"
            else sqlite3.SQLITE_OK
        )

    connection.set_authorizer(deny_setup)
    store = StoreDb(tmp_path / "runs.sqlite3", read_only=read_only)
    with (
        patch("aicmo.db.sqlite3.connect", return_value=connection),
        pytest.raises(sqlite3.DatabaseError, match="not authorized"),
        store.connect(),
    ):
        pytest.fail("Configuration failure must prevent entry into the caller body")
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("select 1")


@pytest.mark.parametrize(
    ("error_code", "injected_statement"),
    [
        (sqlite3.SQLITE_BUSY, "pragma journal_mode = wal"),
        (sqlite3.SQLITE_BUSY_RECOVERY, "pragma journal_mode"),
        (sqlite3.SQLITE_BUSY_SNAPSHOT, "pragma journal_mode"),
        (sqlite3.SQLITE_BUSY_TIMEOUT, "pragma journal_mode = wal"),
        (sqlite3.SQLITE_LOCKED, "pragma journal_mode = wal"),
        (sqlite3.SQLITE_IOERR, "pragma journal_mode"),
    ],
)
def test_first_wal_setup_retries_only_busy(
    tmp_path: Path,
    error_code: int,
    injected_statement: str,
) -> None:
    error = sqlite3.OperationalError("synthetic journal setup failure")
    error.sqlite_errorcode = error_code
    with closing(sqlite3.connect(tmp_path / "runs.sqlite3")) as connection:
        attempts = 0
        mode_changes = 0

        def execute(statement: str) -> sqlite3.Cursor:
            nonlocal attempts, mode_changes
            if statement == injected_statement:
                attempts += 1
                if attempts == 1:
                    raise error
            if statement == "pragma journal_mode = wal":
                mode_changes += 1
            return connection.execute(statement)

        proxy = Mock(wraps=connection)
        proxy.execute.side_effect = execute
        if error_code & 0xFF == sqlite3.SQLITE_BUSY:
            _enable_wal(cast("sqlite3.Connection", proxy))
            assert attempts == 2
            assert connection.execute("pragma journal_mode").fetchone()[0] == "wal"
            # A later connection setup reads the persistent mode without setting it again.
            _enable_wal(cast("sqlite3.Connection", proxy))
            assert mode_changes == 1
        else:
            with pytest.raises(sqlite3.OperationalError) as caught:
                _enable_wal(cast("sqlite3.Connection", proxy))
            assert caught.value is error
            assert attempts == 1


def test_first_wal_busy_budget_preserves_original_error(tmp_path: Path) -> None:
    error = sqlite3.OperationalError("synthetic persistent busy")
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
    with closing(sqlite3.connect(tmp_path / "runs.sqlite3")) as connection:

        def execute(statement: str) -> sqlite3.Cursor:
            if statement == "pragma journal_mode = wal":
                raise error
            return connection.execute(statement)

        proxy = Mock(wraps=connection)
        proxy.execute.side_effect = execute
        with (
            patch("aicmo.db.time.monotonic", side_effect=[10.0, 15.0]),
            patch("aicmo.db.time.sleep") as sleep,
            pytest.raises(sqlite3.OperationalError) as caught,
        ):
            _enable_wal(cast("sqlite3.Connection", proxy))
        assert caught.value is error
        sleep.assert_not_called()


def test_simultaneous_legacy_migrations_preserve_existing_row(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "create table manual_outcomes (client text, observed_on text, channel text, "
            "payload_json text, source_sha256 text, revision integer, "
            "primary key (client, observed_on, channel))"
        )
        connection.execute(
            "insert into manual_outcomes values (?, ?, ?, ?, ?, ?)",
            ("synthetic", "2026-08-31", "naver", '{"posts":1}', "a" * 64, 1),
        )
    start = Barrier(2)

    def initialize() -> None:
        start.wait(timeout=10)
        StoreDb(path).initialize()

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(initialize) for _ in range(2)]
        for job in jobs:
            job.result(timeout=15)
    with StoreDb(path).connect() as connection:
        rows = connection.execute("select * from manual_outcomes").fetchall()
        assert len(rows) == 1
        assert tuple(rows[0]) == (
            "synthetic",
            "2026-08-31",
            "naver",
            '{"posts":1}',
            "a" * 64,
            1,
            None,
            None,
            None,
        )
        assert connection.execute("pragma journal_mode").fetchone()[0] == "wal"
        assert connection.execute("pragma busy_timeout").fetchone()[0] == 5000
        assert connection.execute("pragma foreign_keys").fetchone()[0] == 1


def test_failed_initialization_rolls_back_schema(tmp_path: Path) -> None:
    store = StoreDb(tmp_path / "runs.sqlite3")
    with (
        patch.object(db, "SCHEMA", (*SCHEMA, "select * from synthetic_missing_table")),
        pytest.raises(sqlite3.OperationalError, match="synthetic_missing_table"),
    ):
        store.initialize()
    with store.connect() as connection:
        assert (
            connection.execute("select name from sqlite_master where type='table'").fetchall() == []
        )
    store.initialize()
    with store.connect() as connection:
        assert connection.execute("select count(*) from manual_outcomes").fetchone()[0] == 0


def test_readonly_connection_never_changes_mode_schema_or_creates_database(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("create table legacy (value text)")
        connection.execute("insert into legacy values ('synthetic')")
    before = path.read_bytes()
    reader = StoreDb(path, read_only=True)
    with reader.connect() as connection:
        assert connection.execute("select value from legacy").fetchone()[0] == "synthetic"
        assert connection.execute("pragma journal_mode").fetchone()[0] == "delete"
        assert connection.execute("pragma busy_timeout").fetchone()[0] == 5000
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("insert into legacy values ('rejected')")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        reader.initialize()
    assert path.read_bytes() == before
    missing = tmp_path / "absent" / "runs.sqlite3"
    with (
        pytest.raises(sqlite3.OperationalError, match="unable to open"),
        StoreDb(
            missing,
            read_only=True,
        ).connect(),
    ):
        pytest.fail("A readonly connection must not create a missing database")
    assert not missing.parent.exists()
