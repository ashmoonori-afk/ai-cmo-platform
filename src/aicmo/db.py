from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from aicmo.schema import SCHEMA


def _enable_wal(connection: sqlite3.Connection) -> None:
    # WAL persists, so existing databases do not need another mode transition. SQLite
    # may bypass its busy handler during the first transition to avoid a deadlock.
    # Retry only that setup, within one budget rather than stacked busy timeouts.
    connection.execute("pragma busy_timeout = 0")
    deadline = time.monotonic() + 5
    while True:
        try:
            with closing(connection.execute("pragma journal_mode")) as cursor:
                mode = cursor.fetchone()[0]
            if mode != "wal":
                with closing(connection.execute("pragma journal_mode = wal")) as cursor:
                    cursor.fetchone()
        except sqlite3.OperationalError as exc:
            remaining = deadline - time.monotonic()
            # The low byte also recognizes extended BUSY codes such as BUSY_RECOVERY.
            primary_code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            if primary_code != sqlite3.SQLITE_BUSY or remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))
        else:
            return


@dataclass(frozen=True, slots=True)
class StoreDb:
    db_path: Path
    read_only: bool = field(default=False, kw_only=True)

    @contextmanager
    def connect(self: Self) -> Iterator[sqlite3.Connection]:
        # Single-writer-per-run model. WAL lets readers run alongside the one writer, and
        # busy_timeout makes an accidental concurrent writer wait-and-retry instead of
        # failing immediately with "database is locked". Set before any transaction opens.
        if self.read_only:
            connection = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.db_path)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("pragma foreign_keys = on")
            if not self.read_only:
                _enable_wal(connection)
            connection.execute("pragma busy_timeout = 5000")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self: Self) -> None:
        with self.connect() as connection:
            # Serialize schema inspection and migration as one write transaction.
            connection.execute("begin immediate")
            for statement in SCHEMA:
                connection.execute(statement)
            columns = {str(row["name"]) for row in connection.execute("pragma table_info(runs)")}
            if "spec_digest" not in columns:
                connection.execute("alter table runs add column spec_digest text")
            if "spec_revision" not in columns:
                connection.execute("alter table runs add column spec_revision integer")
            policy_columns = {
                str(row["name"]) for row in connection.execute("pragma table_info(run_policies)")
            }
            if "execution_policy_json" not in policy_columns:
                connection.execute("alter table run_policies add column execution_policy_json text")
            approval_columns = {
                str(row["name"]) for row in connection.execute("pragma table_info(approvals)")
            }
            if "photo_manifest_sha256" not in approval_columns:
                connection.execute("alter table approvals add column photo_manifest_sha256 text")
            outcome_columns = {
                str(row["name"]) for row in connection.execute("pragma table_info(manual_outcomes)")
            }
            for column in ("input_kind", "recorded_at", "recorded_by"):
                if column not in outcome_columns:
                    # Fixed schema column names; existing observations and receipts stay intact.
                    connection.execute(f"alter table manual_outcomes add column {column} text")
