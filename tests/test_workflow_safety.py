from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest

from aicmo import cli
from aicmo.errors import (
    RunConflictError,
    StepTransitionError,
    WorkflowExecutionError,
    WorkflowSpecError,
)
from aicmo.models import StepStatus
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


def test_generated_run_ids_do_not_collide_with_same_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FixedDatetime:
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            assert tz == UTC
            return datetime(2026, 6, 24, 1, 2, 3, 456789, tzinfo=UTC)

    monkeypatch.setattr(cli, "datetime", FixedDatetime)

    run_ids = {cli.generated_run_id() for _ in range(20)}

    assert len(run_ids) == 20
    assert all(run_id.startswith("run_20260624_010203_456789_") for run_id in run_ids)


def test_same_run_id_rejects_different_inputs(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    runner.run(
        workflow_id="blog-article",
        run_id="run_input_guard",
        inputs={"client": "sample-client-a", "topic": "corporate flower subscription"},
    )

    with pytest.raises(RunConflictError):
        runner.run(
            workflow_id="blog-article",
            run_id="run_input_guard",
            inputs={"client": "sample-client-a", "topic": "different topic"},
        )

    write_text(
        repo_root / "workflows" / "approval-demo.workflow.yaml",
        lines(
            "id: approval-demo",
            "name: Approval Demo",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: load_context",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
        ),
    )
    with pytest.raises(RunConflictError):
        runner.run(
            workflow_id="approval-demo",
            run_id="run_input_guard",
            inputs={"client": "sample-client-a"},
        )


def test_rejects_unsafe_workflow_and_run_ids(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    with pytest.raises(WorkflowExecutionError):
        runner.run(
            workflow_id="../../outside",
            run_id="safe_run",
            inputs={"client": "sample-client-a", "topic": "corporate flower subscription"},
        )

    with pytest.raises(WorkflowExecutionError):
        runner.run(
            workflow_id="blog-article",
            run_id="../docs/system",
            inputs={"client": "sample-client-a", "topic": "corporate flower subscription"},
        )


def test_rejects_invalid_workflow_graphs(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))
    invalid_specs = {
        "duplicate-step": lines(
            "id: duplicate-step",
            "name: Duplicate Step",
            "steps:",
            "  - id: same",
            "    type: file.load",
            "  - id: same",
            "    type: agent",
        ),
        "missing-dependency": lines(
            "id: missing-dependency",
            "name: Missing Dependency",
            "steps:",
            "  - id: second",
            "    type: agent",
            "    depends_on: [first]",
        ),
        "duplicate-dependency": lines(
            "id: duplicate-dependency",
            "name: Duplicate Dependency",
            "steps:",
            "  - id: first",
            "    type: agent",
            "  - id: second",
            "    type: agent",
            "    depends_on: [first, first]",
        ),
        "cycle": lines(
            "id: cycle",
            "name: Cycle",
            "steps:",
            "  - id: first",
            "    type: agent",
            "    depends_on: [second]",
            "  - id: second",
            "    type: agent",
            "    depends_on: [first]",
        ),
        "duplicate-output": lines(
            "id: duplicate-output",
            "name: Duplicate Output",
            "steps:",
            "  - id: first",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/same.md",
            "  - id: second",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/same.md",
        ),
        "unsafe-step": lines(
            "id: unsafe-step",
            "name: Unsafe Step",
            "steps:",
            "  - id: ../bad",
            "    type: agent",
        ),
        "id-mismatch": lines(
            "id: different-id",
            "name: Id Mismatch",
            "steps:",
            "  - id: first",
            "    type: agent",
        ),
    }

    for workflow_id, spec in invalid_specs.items():
        write_text(repo_root / "workflows" / f"{workflow_id}.workflow.yaml", spec)
        with pytest.raises(WorkflowSpecError):
            runner.run(workflow_id=workflow_id, run_id=f"run_{workflow_id}", inputs={})


def test_rejects_output_path_traversal(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))
    write_text(
        repo_root / "workflows" / "bad-output.workflow.yaml",
        lines(
            "id: bad-output",
            "name: Bad Output",
            "steps:",
            "  - id: writer",
            "    type: agent",
            "    outputs:",
            "      - ../docs/system/escaped.md",
        ),
    )

    result = runner.run(workflow_id="bad-output", run_id="run_bad_output", inputs={})

    assert result.status == "failed"
    assert result.failed_step_id == "writer"
    assert not (repo_root / "docs" / "system" / "escaped.md").exists()


def test_rejects_invalid_retry_and_approval_transitions(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    runner.run(
        workflow_id="blog-article",
        run_id="run_transition_guard",
        inputs={"client": "sample-client-a", "topic": "corporate flower subscription"},
    )

    with pytest.raises(StepTransitionError):
        runner.retry("run_transition_guard", "missing_step")

    with pytest.raises(StepTransitionError):
        runner.approve("run_transition_guard", "missing_step", reviewer="owner", notes="bad")

    with pytest.raises(StepTransitionError):
        runner.reject("run_transition_guard", "missing_step", reviewer="owner", notes="bad")

    with pytest.raises(StepTransitionError):
        runner.retry("run_transition_guard", "draft")

    with pytest.raises(StepTransitionError):
        runner.approve("run_transition_guard", "draft", reviewer="owner", notes="bad")

    with pytest.raises(StepTransitionError):
        runner.reject("run_transition_guard", "draft", reviewer="owner", notes="bad")


def test_rejected_gate_cannot_be_overwritten(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))
    write_text(
        repo_root / "workflows" / "approval-demo.workflow.yaml",
        lines(
            "id: approval-demo",
            "name: Approval Demo",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: load_context",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
            "    outputs:",
            "      - artifacts/${run_id}/context.md",
            "  - id: owner_gate",
            "    type: gate",
            "    depends_on: [load_context]",
            "    requires_approval: true",
            "    outputs:",
            "      - artifacts/${run_id}/owner-gate.json",
            "  - id: report",
            "    type: agent",
            "    role: reporter",
            "    depends_on: [owner_gate]",
            "    outputs:",
            "      - artifacts/${run_id}/approved-report.md",
        ),
    )

    result = runner.run(
        workflow_id="approval-demo",
        run_id="run_reject_terminal",
        inputs={"client": "sample-client-a"},
    )

    assert result.status == "waiting_approval"
    runner.reject("run_reject_terminal", "owner_gate", reviewer="owner", notes="no")
    assert runner.store.get_step_status("run_reject_terminal", "owner_gate") == StepStatus.FAILED

    with pytest.raises(StepTransitionError):
        runner.approve("run_reject_terminal", "owner_gate", reviewer="owner", notes="yes")

    with pytest.raises(StepTransitionError):
        runner.retry("run_reject_terminal", "owner_gate")

    result = runner.resume("run_reject_terminal")

    assert result.status == "failed"
    assert result.failed_step_id == "owner_gate"
