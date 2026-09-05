from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.errors import RunConflictError
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


class CountingAdapter:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    def generate(self, request: AgentRequest, /) -> AgentResult:
        self.requests.append(request)
        return AgentResult(text=f"completed {request.step_id}")


def _write_workflow(
    repo_root: Path,
    *,
    outputs: tuple[str, ...] = ("artifacts/${run_id}/primary.md",),
    reverse_inputs: bool = False,
    windows_paths: bool = False,
) -> None:
    separator = "\\" if windows_paths else "/"
    input_names = ("topic", "client") if reverse_inputs else ("client", "topic")
    write_text(
        repo_root / "workflows" / "resume-lock.workflow.yaml",
        lines(
            "id: resume-lock",
            "name: Resume Lock",
            "inputs:",
            *(f"  {name}: required" for name in input_names),
            "steps:",
            "  - id: writer",
            "    type: agent",
            "    role: reporter",
            f"    prompt: playbooks{separator}03-content{separator}blog-article.md",
            "    outputs:",
            *(f"      - {output.replace('/', separator)}" for output in outputs),
        ),
    )


def _write_step_set(repo_root: Path, step_ids: tuple[str, ...]) -> None:
    step_lines: list[str] = []
    for step_id in step_ids:
        step_lines.extend(
            [
                f"  - id: {step_id}",
                "    type: agent",
                "    role: reporter",
                "    outputs:",
                f"      - artifacts/${{run_id}}/{step_id}.md",
            ],
        )
    write_text(
        repo_root / "workflows" / "resume-lock.workflow.yaml",
        lines(
            "id: resume-lock",
            "name: Resume Lock",
            "inputs:",
            "  client: required",
            "  topic: required",
            "steps:",
            *step_lines,
        ),
    )


def _new_runner(repo_root: Path) -> tuple[WorkflowRunner, CountingAdapter, Path]:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    adapter = CountingAdapter()
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path), adapter=adapter)
    return runner, adapter, db_path


def _run_to_completion(runner: WorkflowRunner) -> None:
    result = runner.run(
        workflow_id="resume-lock",
        run_id="run_resume_lock",
        inputs={"client": "sample-client-a", "topic": "launch"},
    )
    assert result.status == "success"


def _completed_run(
    repo_root: Path,
    *,
    outputs: tuple[str, ...] = ("artifacts/${run_id}/primary.md",),
) -> tuple[WorkflowRunner, CountingAdapter, Path]:
    _write_workflow(repo_root, outputs=outputs)
    runner, adapter, db_path = _new_runner(repo_root)
    _run_to_completion(runner)
    return runner, adapter, db_path


def _attempts(runner: WorkflowRunner) -> dict[str, int]:
    return {
        str(row["step_id"]): int(row["attempt"])
        for row in runner.store.list_steps("run_resume_lock")
    }


def _ledger_state(db_path: Path) -> tuple[str, ...]:
    with closing(sqlite3.connect(db_path)) as connection:
        return tuple(connection.iterdump())


def _update_run(db_path: Path, statement: str, *values: str | int) -> None:
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(statement, (*values, "run_resume_lock"))


def _assert_resume_rejected_before_work(
    runner: WorkflowRunner,
    adapter: CountingAdapter,
    db_path: Path,
) -> None:
    calls_before = len(adapter.requests)
    attempts_before = _attempts(runner)
    ledger_before = _ledger_state(db_path)

    with pytest.raises(RunConflictError, match="start a new run"):
        runner.resume("run_resume_lock")

    assert len(adapter.requests) == calls_before
    assert _attempts(runner) == attempts_before
    assert _ledger_state(db_path) == ledger_before


def test_initialize_adds_nullable_specification_identity_to_legacy_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            """
            create table runs (
                run_id text primary key,
                workflow_id text not null,
                status text not null,
                inputs_json text not null,
                current_step_id text,
                failed_step_id text,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp,
                completed_at text
            )
            """,
        )
        connection.execute(
            "insert into runs (run_id, workflow_id, status, inputs_json) values (?, ?, ?, ?)",
            ("legacy_run", "resume-lock", "success", "{}"),
        )

    WorkflowStore(db_path).initialize()

    with closing(sqlite3.connect(db_path)) as connection:
        columns = {str(row[1]) for row in connection.execute("pragma table_info(runs)")}
        policy_columns = {
            str(row[1]) for row in connection.execute("pragma table_info(run_policies)")
        }
        identity = connection.execute(
            "select spec_digest, spec_revision from runs where run_id = ?",
            ("legacy_run",),
        ).fetchone()
    assert {"spec_digest", "spec_revision"} <= columns
    assert "execution_policy_json" in policy_columns
    assert identity == (None, None)


def test_resume_succeeds_without_new_adapter_call_when_specification_is_unchanged(
    repo_root: Path,
) -> None:
    runner, adapter, _db_path = _completed_run(repo_root)
    calls_before = len(adapter.requests)
    attempts_before = _attempts(runner)

    result = runner.resume("run_resume_lock")

    assert result.status == "success"
    assert len(adapter.requests) == calls_before
    assert _attempts(runner) == attempts_before


@pytest.mark.parametrize(
    "changed_outputs",
    [
        ("artifacts/${run_id}/primary.md", "artifacts/${run_id}/added.md"),
        (),
    ],
    ids=["output-added", "output-removed"],
)
def test_resume_rejects_before_work_when_declared_outputs_drift(
    repo_root: Path,
    changed_outputs: tuple[str, ...],
) -> None:
    runner, adapter, db_path = _completed_run(repo_root)
    _write_workflow(repo_root, outputs=changed_outputs)

    _assert_resume_rejected_before_work(runner, adapter, db_path)


@pytest.mark.parametrize(
    ("initial_steps", "changed_steps"),
    [
        (("first",), ("first", "second")),
        (("first", "second"), ("first",)),
    ],
    ids=["step-added", "step-removed"],
)
def test_resume_rejects_before_work_when_step_set_drifts(
    repo_root: Path,
    initial_steps: tuple[str, ...],
    changed_steps: tuple[str, ...],
) -> None:
    _write_step_set(repo_root, initial_steps)
    runner, adapter, db_path = _new_runner(repo_root)
    _run_to_completion(runner)
    _write_step_set(repo_root, changed_steps)

    _assert_resume_rejected_before_work(runner, adapter, db_path)

    assert tuple(_attempts(runner)) == initial_steps


@pytest.mark.parametrize(
    "relative_path",
    [
        "playbooks/03-content/blog-article.md",
        "agents/reporter.md",
    ],
    ids=["prompt-bytes", "role-bytes"],
)
def test_resume_rejects_before_work_when_referenced_bytes_drift(
    repo_root: Path,
    relative_path: str,
) -> None:
    runner, adapter, db_path = _completed_run(repo_root)
    path = repo_root / relative_path
    path.write_bytes(path.read_bytes() + b"\nchanged")

    _assert_resume_rejected_before_work(runner, adapter, db_path)


def test_resume_rejects_before_work_when_persisted_inputs_drift(repo_root: Path) -> None:
    runner, adapter, db_path = _completed_run(repo_root)
    changed_inputs = json.dumps({"client": "sample-client-a", "topic": "changed"})
    _update_run(db_path, "update runs set inputs_json = ? where run_id = ?", changed_inputs)

    _assert_resume_rejected_before_work(runner, adapter, db_path)


def test_resume_ignores_mapping_order_and_platform_path_separator_differences(
    repo_root: Path,
) -> None:
    runner, adapter, db_path = _completed_run(repo_root)
    calls_before = len(adapter.requests)
    attempts_before = _attempts(runner)
    _write_workflow(repo_root, reverse_inputs=True, windows_paths=True)
    reordered_inputs = json.dumps({"topic": "launch", "client": "sample-client-a"})
    _update_run(db_path, "update runs set inputs_json = ? where run_id = ?", reordered_inputs)

    result = runner.resume("run_resume_lock")

    assert result.status == "success"
    assert len(adapter.requests) == calls_before
    assert _attempts(runner) == attempts_before


@pytest.mark.parametrize(
    "identity_change",
    [
        "update runs set spec_digest = null where run_id = ?",
        "update runs set spec_revision = null where run_id = ?",
        "update runs set spec_revision = 2 where run_id = ?",
    ],
    ids=["missing-digest", "missing-revision", "unsupported-revision"],
)
def test_resume_rejects_persisted_specification_identity_mismatch(
    repo_root: Path,
    identity_change: str,
) -> None:
    runner, adapter, db_path = _completed_run(repo_root)
    _update_run(db_path, identity_change)

    _assert_resume_rejected_before_work(runner, adapter, db_path)


def test_rejected_resume_does_not_mutate_registry_or_ledger(repo_root: Path) -> None:
    runner, adapter, db_path = _completed_run(repo_root)
    workflow_path = repo_root / "workflows" / "resume-lock.workflow.yaml"
    changed = workflow_path.read_text(encoding="utf-8").replace(
        "name: Resume Lock", "name: Resume Lock Changed"
    )
    workflow_path.write_text(changed, encoding="utf-8")

    _assert_resume_rejected_before_work(runner, adapter, db_path)


def test_resume_wraps_invalid_utf8_as_new_run_guidance(repo_root: Path) -> None:
    runner, adapter, db_path = _completed_run(repo_root)
    workflow_path = repo_root / "workflows" / "resume-lock.workflow.yaml"
    workflow_path.write_bytes(b"\xff\xfe\x80")

    _assert_resume_rejected_before_work(runner, adapter, db_path)
