from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal, assert_never

import pytest

from aicmo.runner import WorkflowRunner
from aicmo.spec import load_workflow_spec
from aicmo.store import WorkflowStore
from tests.conftest import write_text

_INPUTS = {"client": "sample-client-a", "topic": "atomic completion"}
_OWNER = "runner-a"
HashMutation = Literal["missing", "mismatch"]

_FAULT_TRIGGERS = (
    pytest.param(
        """
        create trigger fail_success_update
        before update of status on steps
        when new.status = 'success'
        begin select raise(abort, 'fault'); end
        """,
        id="step-status",
    ),
    pytest.param(
        """
        create trigger fail_artifact_insert
        before insert on artifacts
        begin select raise(abort, 'fault'); end
        """,
        id="artifact",
    ),
    pytest.param(
        """
        create trigger fail_hash_insert
        before insert on step_output_hashes
        begin select raise(abort, 'fault'); end
        """,
        id="output-hash",
    ),
    pytest.param(
        """
        create trigger fail_ref_digest_insert
        before insert on step_consumed_ref_digests
        begin select raise(abort, 'fault'); end
        """,
        id="consumed-ref-digest",
    ),
    pytest.param(
        """
        create trigger fail_success_event
        before insert on events
        when new.event_type = 'step.success'
        begin select raise(abort, 'fault'); end
        """,
        id="success-event",
    ),
)


def _seed_running_step(
    repo_root: Path,
    run_id: str,
) -> tuple[WorkflowStore, Path, str, list[str], dict[str, str]]:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    store = WorkflowStore(db_path)
    store.initialize()
    spec = load_workflow_spec(repo_root, "blog-article")
    store.ensure_run(spec=spec, run_id=run_id, inputs=_INPUTS)
    step = spec.steps[0]
    assert store.mark_step_running(run_id, step, _OWNER, 300) is True
    relative = f"artifacts/{run_id}/context.md"
    artifact = repo_root / relative
    write_text(artifact, "safely replaced artifact\n")
    hashes = {relative: hashlib.sha256(artifact.read_bytes()).hexdigest()}
    return store, db_path, step.id, [relative], hashes


@pytest.mark.parametrize("fault_trigger", _FAULT_TRIGGERS)
def test_success_ledger_rolls_back_when_any_internal_write_fails(
    repo_root: Path,
    fault_trigger: str,
) -> None:
    # Given: an owned RUNNING step whose artifact is already safely on disk.
    store, db_path, step_id, outputs, hashes = _seed_running_step(repo_root, "run_rollback")
    with store.connect() as connection:
        connection.execute(fault_trigger)

    # When: any write in the terminal SQLite ledger transaction is forced to abort.
    with pytest.raises(sqlite3.IntegrityError, match="fault"):
        store.complete_step_success(
            "run_rollback",
            step_id,
            outputs,
            hashes,
            consumed_ref_digest="refs-v1",
            owner=_OWNER,
        )

    # Then: every terminal ledger row rolls back while the already-written file remains.
    with closing(sqlite3.connect(db_path)) as connection:
        step = connection.execute(
            "select status, outputs_json, locked_by from steps where run_id = ? and step_id = ?",
            ("run_rollback", step_id),
        ).fetchone()
        counts = tuple(
            connection.execute(
                f"select count(*) from {table} where run_id = ? and step_id = ?",  # noqa: S608
                ("run_rollback", step_id),
            ).fetchone()[0]
            for table in (
                "artifacts",
                "step_output_hashes",
                "step_consumed_ref_digests",
                "events",
            )
        )
    assert step == ("running", "[]", _OWNER)
    assert counts == (0, 0, 0, 0)
    assert (repo_root / outputs[0]).read_text(encoding="utf-8") == "safely replaced artifact\n"


def test_success_ledger_rejects_stale_owner_without_partial_rows(repo_root: Path) -> None:
    # Given: a second runner has reclaimed the first runner's expired lease.
    store, db_path, step_id, outputs, hashes = _seed_running_step(repo_root, "run_stale")
    with store.connect() as connection:
        connection.execute(
            "update steps set locked_at = '2000-01-01 00:00:00' where run_id = ? and step_id = ?",
            ("run_stale", step_id),
        )
    spec = load_workflow_spec(repo_root, "blog-article")
    assert store.mark_step_running("run_stale", spec.steps[0], "runner-b", 1) is True

    # When: the stale owner tries to publish its success ledger.
    completed = store.complete_step_success(
        "run_stale",
        step_id,
        outputs,
        hashes,
        consumed_ref_digest="refs-v1",
        owner=_OWNER,
    )

    # Then: the CAS loses cleanly and runner-b's live lease is untouched.
    with closing(sqlite3.connect(db_path)) as connection:
        step = connection.execute(
            "select status, outputs_json, locked_by from steps where run_id = ? and step_id = ?",
            ("run_stale", step_id),
        ).fetchone()
        terminal_rows = connection.execute(
            "select count(*) from artifacts where run_id = ? and step_id = ?",
            ("run_stale", step_id),
        ).fetchone()[0]
    assert completed is False
    assert step == ("running", "[]", "runner-b")
    assert terminal_rows == 0


@pytest.mark.parametrize("mutation", ["missing", "mismatch"])
def test_resume_reopens_success_when_output_hash_is_untrusted(
    repo_root: Path,
    mutation: HashMutation,
) -> None:
    # Given: a successful run whose draft hash row is absent or disagrees with the file.
    store = WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3")
    runner = WorkflowRunner(repo_root=repo_root, store=store)
    assert runner.run("blog-article", "run_hash_gap", _INPUTS).status == "success"
    attempts_before = {
        str(row["step_id"]): int(row["attempt"]) for row in store.list_steps("run_hash_gap")
    }
    with store.connect() as connection:
        match mutation:
            case "missing":
                connection.execute(
                    "delete from step_output_hashes where run_id = ? and step_id = ?",
                    ("run_hash_gap", "draft"),
                )
            case "mismatch":
                connection.execute(
                    "update step_output_hashes set sha256 = ? where run_id = ? and step_id = ?",
                    ("0" * 64, "run_hash_gap", "draft"),
                )
            case unreachable:
                assert_never(unreachable)

    # When: resume reconciles the supposedly successful rows.
    resumed = runner.resume("run_hash_gap")

    # Then: the untrusted producer and its dependents regenerate deterministically.
    attempts_after = {
        str(row["step_id"]): int(row["attempt"]) for row in store.list_steps("run_hash_gap")
    }
    assert resumed.status == "success"
    assert attempts_after == {
        "load_context": attempts_before["load_context"],
        "keyword_research": attempts_before["keyword_research"],
        "draft": attempts_before["draft"] + 1,
        "review": attempts_before["review"] + 1,
        "report": attempts_before["report"] + 1,
    }
    draft = repo_root / "artifacts" / "run_hash_gap" / "draft.md"
    assert store.get_output_hashes("run_hash_gap", "draft") == {
        "artifacts/run_hash_gap/draft.md": hashlib.sha256(draft.read_bytes()).hexdigest(),
    }
