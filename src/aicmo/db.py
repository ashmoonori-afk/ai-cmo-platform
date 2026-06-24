from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from aicmo.schema import SCHEMA


@dataclass(frozen=True, slots=True)
class StoreDb:
    db_path: Path

    @contextmanager
    def connect(self: Self) -> Iterator[sqlite3.Connection]:
        # Single-writer-per-run model. WAL lets readers run alongside the one writer, and
        # busy_timeout makes an accidental concurrent writer wait-and-retry instead of
        # failing immediately with "database is locked". Set before any transaction opens.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        connection.execute("pragma busy_timeout = 5000")
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
