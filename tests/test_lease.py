from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from aicmo.runner import WorkflowRunner
from aicmo.spec import load_workflow_spec
from aicmo.store import WorkflowStore

_INPUTS = {"client": "sample-client-a", "topic": "t"}


def _setup(repo_root: Path):  # noqa: ANN202 — test helper
    store = WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3")
    store.initialize()
    spec = load_workflow_spec(repo_root, "blog-article")
    store.ensure_run(spec=spec, run_id="r", inputs=_INPUTS)
    return store, spec


def test_claim_blocks_live_foreign_lease(repo_root: Path) -> None:
    store, spec = _setup(repo_root)
    step = spec.steps[0]

    assert store.mark_step_running("r", step, "owner_a", 300) is True
    # A live foreign owner with a fresh lease cannot steal the claim.
    assert store.mark_step_running("r", step, "owner_b", 300) is False
    # A stale lease (ttl 0 -> everything past TTL) is reclaimable.
    assert store.mark_step_running("r", step, "owner_b", 0) is True


def test_claim_allows_unlocked_running(repo_root: Path) -> None:
    store, spec = _setup(repo_root)
    step = spec.steps[0]
    store.mark_step_running("r", step, "owner_a", 300)
    db = repo_root / ".aicmo" / "runs.sqlite3"
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute(
            "update steps set locked_by = null, locked_at = null "
            "where run_id = 'r' and step_id = ?",
            (step.id,),
        )

    # Crash leaves a RUNNING step with no live owner -> reclaimable.
    assert store.mark_step_running("r", step, "owner_b", 300) is True


def test_renew_lease_refreshes_own_lease_only(repo_root: Path) -> None:
    store, spec = _setup(repo_root)
    step = spec.steps[0]
    store.mark_step_running("r", step, "owner_a", 300)

    store.renew_lease("r", step.id, "owner_other")  # wrong owner -> no-op
    store.renew_lease("r", step.id, "owner_a")  # owner renews, no error
    # The lease is still held by owner_a; nobody else can claim it.
    assert store.mark_step_running("r", step, "owner_c", 300) is False


def test_concurrent_runner_cannot_double_execute(repo_root: Path) -> None:
    db = repo_root / ".aicmo" / "runs.sqlite3"
    runner_a = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db))
    runner_a.run(workflow_id="blog-article", run_id="r_dbl", inputs=_INPUTS)

    # Simulate runner A actively re-executing 'draft' (a fresh, live foreign lease).
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute(
            "update steps set status = 'running', locked_by = 'live_a', "
            "locked_at = current_timestamp where run_id = 'r_dbl' and step_id = 'draft'",
        )

    runner_b = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db),
        runner_token="runner_b",  # noqa: S106 — a test runner id, not a secret
    )
    result = runner_b.resume("r_dbl")

    assert result.status == "failed"
    assert result.failed_step_id == "draft"
