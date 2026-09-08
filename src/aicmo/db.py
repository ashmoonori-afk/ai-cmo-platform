from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from aicmo.schema import SCHEMA


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
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        connection.execute("pragma busy_timeout = 5000")
        if not self.read_only:
            connection.execute("pragma journal_mode = wal")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self: Self) -> None:
        with self.connect() as connection:
            for statement in SCHEMA:
                connection.execute(statement)
            columns = {str(row["name"]) for row in connection.execute("pragma table_info(runs)")}
            if "spec_digest" not in columns:
                connection.execute("alter table runs add column spec_digest text")
            if "spec_revision" not in columns:
                connection.execute("alter table runs add column spec_revision integer")
            policy_columns = {
                str(row["name"])
                for row in connection.execute("pragma table_info(run_policies)")
            }
            if "execution_policy_json" not in policy_columns:
                connection.execute("alter table run_policies add column execution_policy_json text")
            approval_columns = {
                str(row["name"]) for row in connection.execute("pragma table_info(approvals)")
            }
            if "photo_manifest_sha256" not in approval_columns:
                connection.execute("alter table approvals add column photo_manifest_sha256 text")
