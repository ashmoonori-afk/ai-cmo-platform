"""Operator-only aggregate reads; never initialize a database or infer worker liveness."""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from aicmo.db import StoreDb
from aicmo.models import RunStatus, StepStatus

_JOB_STATES = (
    "queued",
    "running",
    "waiting_approval",
    "success",
    "needs_work",
    "failed",
    "cancelled",
)
_WORKFLOWS = ("local-store-pack", "weekly-report", "local-pack-feedback")
_ONBOARDING_STATES = ("draft", "queued", "running", "failed", "complete")
_WEB_COLUMNS = {
    "store_app_job": {"state", "workflow_id", "cancel_requested", "created_at"},
    "store_app_onboardingdraft": {"state"},
}
_ENGINE_COLUMNS = {
    "runs": {"status"},
    "steps": {"status", "locked_at"},
}
_QUERY_SECONDS = 2.0
_BUSY_MILLISECONDS = 1000


def _supports_columns(connection: sqlite3.Connection, tables: dict[str, set[str]]) -> bool:
    actual_tables = {
        row["name"]
        for row in connection.execute("select name from sqlite_master where type='table'")
    }
    for name, columns in tables.items():
        if name not in actual_tables:
            return False
        # These are fixed application table names, never input or schema text.
        actual_columns = {row["name"] for row in connection.execute(f"pragma table_info({name})")}
        if not columns <= actual_columns:
            return False
    return True


def _counts(connection: sqlite3.Connection, query: str, states: tuple[str, ...]) -> dict[str, int]:
    counts = dict.fromkeys(states, 0)
    for row in connection.execute(query):
        if row[0] not in counts:
            reason = "invalid-state"
            raise ValueError(reason)
        counts[row[0]] = int(row[1])
    return counts


def _age(value: object, now: datetime) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) < 19:  # noqa: PLR2004
        reason = "invalid-timestamp"
        raise ValueError(reason)
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    seconds = (now - timestamp).total_seconds()
    if seconds < 0:
        reason = "future-timestamp"
        raise ValueError(reason)
    return int(seconds)


def _ages(connection: sqlite3.Connection, query: str, now: datetime) -> tuple[int, int, int | None]:
    count, missing, oldest = 0, 0, None
    for row in connection.execute(query):
        count += 1
        age = _age(row[0], now)
        if age is None:
            missing += 1
        else:
            oldest = age if oldest is None else max(oldest, age)
    return count, missing, oldest


def _web_summary(connection: sqlite3.Connection, now: datetime) -> dict[str, object]:
    jobs = _counts(
        connection, "select state,count(*) from store_app_job group by state", _JOB_STATES
    )
    workflows = _counts(
        connection,
        "select workflow_id,count(*) from store_app_job group by workflow_id",
        _WORKFLOWS,
    )
    onboarding = _counts(
        connection,
        "select state,count(*) from store_app_onboardingdraft group by state",
        _ONBOARDING_STATES,
    )
    invalid_flags = connection.execute(
        "select count(*) from store_app_job where cancel_requested is null "
        "or cancel_requested not in (0,1)"
    ).fetchone()[0]
    if invalid_flags:
        reason = "invalid-cancel-flag"
        raise ValueError(reason)
    cancellation_pending = connection.execute(
        "select count(*) from store_app_job where cancel_requested=1"
    ).fetchone()[0]
    queued = _ages(connection, "select created_at from store_app_job where state='queued'", now)
    if queued[1]:
        reason = "missing-queue-timestamp"
        raise ValueError(reason)
    return {
        "job_counts": jobs,
        "workflow_counts": workflows,
        "cancellation_pending": cancellation_pending,
        "oldest_queued_age_seconds": queued[2],
        "onboarding_counts": onboarding,
    }


def _engine_summary(connection: sqlite3.Connection, now: datetime) -> dict[str, object]:
    runs = _counts(connection, "select status,count(*) from runs group by status", tuple(RunStatus))
    _counts(connection, "select status,count(*) from steps group by status", tuple(StepStatus))
    running = _ages(connection, "select locked_at from steps where status='running'", now)
    return {
        "run_counts": runs,
        "running_steps": running[0],
        "running_without_heartbeat": running[1],
        "oldest_running_heartbeat_age_seconds": running[2],
    }


def _read_summary(path: Path, *, web: bool, now: datetime | None) -> dict[str, object]:
    try:
        # stat distinguishes an absent file from inaccessible storage; neither is created.
        path.stat()
    except FileNotFoundError:
        return {"query_status": "missing", "summary": None}
    except OSError:
        return {"query_status": "unavailable", "summary": None}
    try:
        with StoreDb(path, read_only=True).connect() as connection:
            connection.execute(f"pragma busy_timeout={_BUSY_MILLISECONDS}")
            deadline = time.monotonic() + _QUERY_SECONDS
            connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            # SELECT alone does not start a Python sqlite3 transaction.
            connection.execute("begin")
            if not _supports_columns(connection, _WEB_COLUMNS if web else _ENGINE_COLUMNS):
                return {"query_status": "schema_unsupported", "summary": None}
            # The first SELECT has established this DB's snapshot. Sampling afterward
            # avoids classifying a just-arrived queued job as a future timestamp.
            read_at = datetime.now(UTC) if now is None else now.astimezone(UTC)
            summary = (
                _web_summary(connection, read_at) if web else _engine_summary(connection, read_at)
            )
            return {"query_status": "available", "summary": summary}
    except (sqlite3.Error, OSError):
        return {"query_status": "unavailable", "summary": None}
    except (ValueError, OverflowError):
        return {"query_status": "invalid_data", "summary": None}


def _wal_reset_fix(version: tuple[int, int, int]) -> str:
    # SQLite's published fixed versions, not a claim about a vendor's unlabelled backport.
    # https://www.sqlite.org/wal.html#walresetbug
    fixed = (
        version >= (3, 51, 3)
        or (3, 50, 7) <= version < (3, 51, 0)
        or (3, 44, 6) <= version < (3, 45, 0)
    )
    return "included" if fixed else "not_confirmed"


def inspect_store(repo: Path, *, now: datetime | None = None) -> dict[str, object]:
    observed_at = datetime.now(UTC) if now is None else now.astimezone(UTC)
    web = _read_summary(repo / ".aicmo/web.sqlite3", web=True, now=now)
    engine = _read_summary(repo / ".aicmo/runs.sqlite3", web=False, now=now)
    return {
        "schema_version": "aicmo.store-inspection.v1",
        "observed_at": observed_at.isoformat(),
        "inspection_status": (
            "available"
            if web["query_status"] == engine["query_status"] == "available"
            else "needs_review"
        ),
        "web": web,
        "engine": engine,
        "runtime": {
            "sqlite_version": sqlite3.sqlite_version,
            "wal_reset_fix": _wal_reset_fix(sqlite3.sqlite_version_info),
        },
        "worker_process": "unverified",
        "provider_cost": "unavailable",
        "snapshot_scope": "separate_read_transactions",
    }
