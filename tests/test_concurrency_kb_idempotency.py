from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from aicmo.models import StepStatus
from aicmo.runner import WorkflowRunner
from aicmo.spec import load_workflow_spec
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


def _kb_workflow(repo_root: Path) -> None:
    write_text(
        repo_root / "workflows" / "kb-demo.workflow.yaml",
        lines(
            "id: kb-demo",
            "name: KB Demo",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: load",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
            "    outputs:",
            "      - artifacts/${run_id}/ctx.md",
            "  - id: kb",
            "    type: kb.update",
            "    depends_on: [load]",
            "    outputs:",
            "      - artifacts/${run_id}/kb-log.md",
        ),
    )


# ---- G001/C1 : WAL + busy_timeout ----


def test_connect_enables_wal_and_busy_timeout(repo_root: Path) -> None:
    store = WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3")
    store.initialize()

    with store.connect() as connection:
        journal_mode = str(connection.execute("pragma journal_mode").fetchone()[0])
        busy_timeout = int(connection.execute("pragma busy_timeout").fetchone()[0])

    assert journal_mode.lower() == "wal"
    assert busy_timeout > 0


# ---- G001/C2 : locked_by/locked_at lifecycle + concurrency ----


def _lock_fields(db_path: Path, run_id: str, step_id: str) -> tuple[object, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "select locked_by, locked_at from steps where run_id = ? and step_id = ?",
            (run_id, step_id),
        ).fetchone()
    return (row["locked_by"], row["locked_at"])


def test_mark_step_running_sets_lock_and_terminal_transitions_clear_it(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    store = WorkflowStore(db_path)
    store.initialize()
    spec = load_workflow_spec(repo_root, "blog-article")
    store.ensure_run(
        spec=spec,
        run_id="r_lock",
        inputs={"client": "sample-client-a", "topic": "t"},
    )
    step = spec.steps[0]

    store.mark_step_running("r_lock", step)
    locked_by, locked_at = _lock_fields(db_path, "r_lock", step.id)
    assert locked_by is not None
    assert locked_at is not None

    store.mark_step_success("r_lock", step.id, [])
    cleared_by, cleared_at = _lock_fields(db_path, "r_lock", step.id)
    assert cleared_by is None
    assert cleared_at is None


def test_concurrent_writers_do_not_hit_database_locked(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    store = WorkflowStore(db_path)
    store.initialize()
    spec = load_workflow_spec(repo_root, "blog-article")
    store.ensure_run(
        spec=spec,
        run_id="r_conc",
        inputs={"client": "sample-client-a", "topic": "t"},
    )
    errors: list[Exception] = []

    def writer(tag: str) -> None:
        try:
            for index in range(25):
                store.record_event("r_conc", None, "probe", f"{tag}-{index}")
        except Exception as exc:  # noqa: BLE001 — capture any 'database is locked' for the assertion
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    with closing(sqlite3.connect(db_path)) as connection:
        written = connection.execute(
            "select count(*) from events where run_id = ? and event_type = ?",
            ("r_conc", "probe"),
        ).fetchone()[0]
    assert written == 50


def test_step_left_running_is_rerunnable_on_resume(repo_root: Path) -> None:
    """Crash-recovery anti-regression: a step stuck in RUNNING must re-run, not be refused."""
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))
    runner.run(
        workflow_id="blog-article",
        run_id="r_crash",
        inputs={"client": "sample-client-a", "topic": "t"},
    )
    # simulate a crash mid-step: force one step back to RUNNING and drop its artifact
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            "update steps set status = 'running' where run_id = ? and step_id = ?",
            ("r_crash", "draft"),
        )
    (repo_root / "artifacts" / "r_crash" / "draft.md").unlink()

    resumed = runner.resume("r_crash")

    assert resumed.status == "success"
    assert (repo_root / "artifacts" / "r_crash" / "draft.md").exists()
    assert runner.store.get_step_status("r_crash", "draft") == StepStatus.SUCCESS


# ---- G002/C1 : kb.update idempotency ----


def _kb_row_count(db_path: Path, run_id: str, step_id: str) -> int:
    with closing(sqlite3.connect(db_path)) as connection:
        return int(
            connection.execute(
                "select count(*) from kb_updates where run_id = ? and step_id = ?",
                (run_id, step_id),
            ).fetchone()[0],
        )


def test_kb_update_rerun_is_idempotent(repo_root: Path) -> None:
    _kb_workflow(repo_root)
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    runner.run(
        workflow_id="kb-demo",
        run_id="r_kb",
        inputs={"client": "sample-client-a"},
    )
    assert _kb_row_count(db_path, "r_kb", "kb") == 1

    (repo_root / "artifacts" / "r_kb" / "kb-log.md").unlink()
    resumed = runner.resume("r_kb")

    assert resumed.status == "success"
    assert _kb_row_count(db_path, "r_kb", "kb") == 1


def test_initialize_dedupes_existing_kb_updates(repo_root: Path) -> None:
    """Migrating a DB that already holds duplicate kb rows must not brick initialize()."""
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            """
            create table kb_updates (
                kb_update_id integer primary key autoincrement,
                run_id text not null,
                step_id text not null,
                client text not null,
                path text not null,
                status text not null,
                content text not null,
                created_at text not null default current_timestamp
            )
            """,
        )
        connection.executemany(
            "insert into kb_updates (run_id, step_id, client, path, status, content) "
            "values (?, ?, ?, ?, ?, ?)",
            [
                ("r", "s", "c", "p/x.md", "queued", "body"),
                ("r", "s", "c", "p/x.md", "queued", "body"),
            ],
        )

    WorkflowStore(db_path).initialize()

    assert _kb_row_count(db_path, "r", "s") == 1
