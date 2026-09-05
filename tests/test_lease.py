from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from queue import SimpleQueue
from threading import Event, Thread
from typing import TYPE_CHECKING

from aicmo.adapters import OFFLINE_STUB_MARKER, AgentRequest, AgentResult, LocalAdapter
from aicmo.models import RunResult
from aicmo.runner import WorkflowRunner
from aicmo.spec import load_workflow_spec
from aicmo.store import WorkflowStore

if TYPE_CHECKING:
    import pytest

_INPUTS = {"client": "sample-client-a", "topic": "t"}


class _WaitForRenewalAdapter:
    def __init__(self, renewal_attempted: Event) -> None:
        self.renewal_attempted = renewal_attempted

    def generate(self, request: AgentRequest, /) -> AgentResult:
        assert self.renewal_attempted.wait(timeout=5), request.step_id
        return AgentResult(text="stale output after renewal failure")


class _BlockingAdapter:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def generate(self, request: AgentRequest, /) -> AgentResult:
        self.started.set()
        assert self.release.wait(timeout=5), request.step_id
        return AgentResult(text="stale runner output")


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

    assert store.renew_lease("r", step.id, "owner_other") is False
    assert store.renew_lease("r", step.id, "owner_a") is True
    # The lease is still held by owner_a; nobody else can claim it.
    assert store.mark_step_running("r", step, "owner_c", 300) is False


def test_heartbeat_exception_aborts_before_artifact_write(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: renewal raises while an agent adapter is still executing.
    db = repo_root / ".aicmo" / "runs.sqlite3"
    store = WorkflowStore(db)
    renewal_attempted = Event()
    renew_lease = WorkflowStore.renew_lease

    def raise_for_agent_step(
        self: WorkflowStore,
        run_id: str,
        step_id: str,
        owner: str,
    ) -> bool:
        if step_id == "keyword_research":
            renewal_attempted.set()
            message = "injected renewal failure"
            raise sqlite3.OperationalError(message)
        return renew_lease(self, run_id, step_id, owner)

    monkeypatch.setattr(WorkflowStore, "renew_lease", raise_for_agent_step)
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=store,
        adapter=_WaitForRenewalAdapter(renewal_attempted),
        heartbeat_interval_seconds=0.001,
    )

    # When: the adapter returns after the heartbeat worker observed the exception.
    result = runner.run("blog-article", "r_renew_error", _INPUTS)

    # Then: the step fails without publishing or claiming terminal success.
    step = next(
        row for row in store.list_steps("r_renew_error") if row["step_id"] == "keyword_research"
    )
    assert result.status == "failed"
    assert result.failed_step_id == "keyword_research"
    assert step["status"] == "failed"
    assert step["attempt"] == 1
    assert not (repo_root / "artifacts" / "r_renew_error" / "keyword-brief.md").exists()


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


def test_stolen_lease_allows_only_new_owner_to_reach_success(repo_root: Path) -> None:
    # Given: runner A holds an agent step while runner B is allowed to reclaim it.
    db = repo_root / ".aicmo" / "runs.sqlite3"
    blocker = _BlockingAdapter()
    runner_a = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db),
        adapter=blocker,
        runner_token="runner_a",  # noqa: S106 - test runner id, not a secret
        heartbeat_interval_seconds=60,
    )
    runner_b = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db),
        adapter=LocalAdapter(),
        runner_token="runner_b",  # noqa: S106 - test runner id, not a secret
        lease_ttl_seconds=0,
    )
    results: SimpleQueue[RunResult] = SimpleQueue()
    thread = Thread(target=lambda: results.put(runner_a.run("blog-article", "r_stolen", _INPUTS)))
    thread.start()

    try:
        assert blocker.started.wait(timeout=5)

        # When: runner B steals the stale lease and completes before A returns.
        winner = runner_b.resume("r_stolen", allow_policy_change=True)
    finally:
        blocker.release.set()
        thread.join(timeout=5)

    # Then: A's zero-row renewal aborts it; B alone succeeds and owns the artifact.
    assert not thread.is_alive()
    stale = results.get_nowait()
    step = next(
        row for row in runner_b.store.list_steps("r_stolen") if row["step_id"] == "keyword_research"
    )
    artifact = repo_root / "artifacts" / "r_stolen" / "keyword-brief.md"
    assert [stale.status, winner.status].count("success") == 1
    assert stale.status == "failed"
    assert stale.failed_step_id == "keyword_research"
    assert winner.status == "success"
    assert step["status"] == "success"
    assert step["attempt"] == 2
    assert "stale runner output" not in artifact.read_text(encoding="utf-8")


def test_lease_loss_after_prewrite_check_cannot_replace_winner(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: runner A pauses after its lease check but before writing its temp artifact.
    db = repo_root / ".aicmo" / "runs.sqlite3"
    stale_adapter = _BlockingAdapter()
    stale_adapter.release.set()
    before_stale_write = Event()
    release_stale_write = Event()
    write_text = Path.write_text

    def pause_stale_write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if self.name.startswith("keyword-brief.md") and "stale runner output" in data:
            before_stale_write.set()
            assert release_stale_write.wait(timeout=5)
        return write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    monkeypatch.setattr(Path, "write_text", pause_stale_write)
    runner_a = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db),
        adapter=stale_adapter,
        runner_token="runner_a",  # noqa: S106 - test runner id, not a secret
        heartbeat_interval_seconds=60,
    )
    runner_b = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db),
        adapter=LocalAdapter(),
        runner_token="runner_b",  # noqa: S106 - test runner id, not a secret
        lease_ttl_seconds=0,
    )
    results: SimpleQueue[RunResult] = SimpleQueue()
    thread = Thread(
        target=lambda: results.put(runner_a.run("blog-article", "r_write_race", _INPUTS))
    )
    thread.start()

    try:
        assert before_stale_write.wait(timeout=5)

        # When: runner B reclaims and completes while A remains before replacement.
        winner = runner_b.resume("r_write_race", allow_policy_change=True)
        artifact = repo_root / "artifacts" / "r_write_race" / "keyword-brief.md"
        assert OFFLINE_STUB_MARKER in artifact.read_text(encoding="utf-8")
    finally:
        release_stale_write.set()
        thread.join(timeout=5)

    # Then: A fails ownership and cannot replace B's successful artifact.
    assert not thread.is_alive()
    stale = results.get_nowait()
    step = next(
        row
        for row in runner_b.store.list_steps("r_write_race")
        if row["step_id"] == "keyword_research"
    )
    content = artifact.read_text(encoding="utf-8")
    assert [stale.status, winner.status].count("success") == 1
    assert stale.status == "failed"
    assert stale.failed_step_id == "keyword_research"
    assert winner.status == "success"
    assert step["status"] == "success"
    assert step["attempt"] == 2
    assert OFFLINE_STUB_MARKER in content
    assert "stale runner output" not in content


def test_gate_wait_survives_heartbeat_shutdown_race(repo_root: Path) -> None:
    # Given: an approval gate run whose heartbeat renews at sub-millisecond cadence.
    workflow = repo_root / "workflows" / "blog-article.workflow.yaml"
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "  - id: review\n    type: gate\n",
            "  - id: review\n    type: gate\n    requires_approval: true\n",
        ),
        encoding="utf-8",
    )
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
        adapter=LocalAdapter(),
        heartbeat_interval_seconds=0.001,
    )

    # When: the run parks at the approval gate and the heartbeat tears down.
    result = runner.run("blog-article", "r_gate_wait", _INPUTS)

    # Then: the released lease is not renewed into a false lease-lost failure.
    step = next(row for row in runner.store.list_steps("r_gate_wait") if row["step_id"] == "review")
    assert result.status == "waiting_approval"
    assert step["status"] == "waiting_approval"
    assert step["locked_by"] is None
