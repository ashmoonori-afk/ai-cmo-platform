from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from aicmo import cli
from aicmo.cli import app
from aicmo.errors import WorkflowExecutionError, WorkflowSpecError
from aicmo.models import StepStatus
from aicmo.paths import resolve_inside_repo
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


def test_runs_steps_when_dependency_declared_after_dependent(repo_root: Path) -> None:
    """A valid DAG whose dependency is declared later must still execute (topological order)."""
    write_text(
        repo_root / "workflows" / "out-of-order.workflow.yaml",
        lines(
            "id: out-of-order",
            "name: Out Of Order",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: second",
            "    type: agent",
            "    role: reporter",
            "    depends_on: [first]",
            "    outputs:",
            "      - artifacts/${run_id}/second.md",
            "  - id: first",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
            "    outputs:",
            "      - artifacts/${run_id}/first.md",
        ),
    )
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    result = runner.run(
        workflow_id="out-of-order",
        run_id="run_out_of_order",
        inputs={"client": "sample-client-a"},
    )

    assert result.status == "success"
    assert (repo_root / "artifacts" / "run_out_of_order" / "first.md").exists()
    assert (repo_root / "artifacts" / "run_out_of_order" / "second.md").exists()


def test_resume_reruns_successful_step_when_output_missing(repo_root: Path) -> None:
    """Resume must regenerate a vanished artifact instead of crashing on a SUCCESS step."""
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    runner.run(
        workflow_id="blog-article",
        run_id="run_missing_output",
        inputs={"client": "sample-client-a", "topic": "corporate flower subscription"},
    )
    context_artifact = repo_root / "artifacts" / "run_missing_output" / "context.md"
    context_artifact.unlink()

    resumed = runner.resume("run_missing_output")

    assert resumed.status == "success"
    assert context_artifact.exists()


def test_resolve_inside_repo_rejects_unresolved_variable(tmp_path: Path) -> None:
    with pytest.raises(WorkflowExecutionError):
        resolve_inside_repo(tmp_path, "artifacts/${client}/file.md", {"run_id": "r1"})


def test_resolve_inside_repo_substitutes_known_variables(tmp_path: Path) -> None:
    resolved = resolve_inside_repo(tmp_path, "artifacts/${run_id}/file.md", {"run_id": "r1"})

    assert resolved == (tmp_path / "artifacts" / "r1" / "file.md").resolve()


def test_cli_run_exits_nonzero_when_run_fails(repo_root: Path) -> None:
    (repo_root / "playbooks" / "03-content" / "blog-article.md").unlink()

    result = CliRunner().invoke(
        app,
        [
            "run",
            "blog-article",
            "--client",
            "sample-client-a",
            "--topic",
            "corporate flower subscription",
            "--run-id",
            "run_cli_fail",
            "--repo",
            str(repo_root),
        ],
    )

    assert result.exit_code == 1


def test_cli_run_exits_tempfail_when_waiting_for_approval(repo_root: Path) -> None:
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
            "  - id: owner_gate",
            "    type: gate",
            "    depends_on: [load_context]",
            "    requires_approval: true",
            "    outputs:",
            "      - artifacts/${run_id}/owner-gate.json",
        ),
    )

    result = CliRunner().invoke(
        app,
        [
            "run",
            "approval-demo",
            "--client",
            "sample-client-a",
            "--run-id",
            "run_cli_waiting",
            "--repo",
            str(repo_root),
        ],
    )

    assert result.exit_code == 75


def test_main_reports_unexpected_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unexpected (non-Aicmo) errors exit 1 with a one-line message and NO traceback/frames."""

    def boom() -> None:
        msg = "boom from deep in the stack"
        raise RuntimeError(msg)

    monkeypatch.setattr(cli, "app", boom)

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert excinfo.value.code == 1
    assert "error:" in captured.out
    assert "boom from deep in the stack" in captured.out
    # the contract: a clean message, not a leaked traceback or internal frames
    assert "Traceback (most recent call last)" not in combined
    assert "RuntimeError" not in combined


def test_non_workflow_error_in_step_is_recorded_as_failed(repo_root: Path) -> None:
    """A non-WorkflowExecutionError (e.g. UnicodeDecodeError) must fail the run, not strand it."""
    (repo_root / "clients" / "sample-client-a" / "logo.bin").write_bytes(b"\xff\xfe\x00\x01\x80")
    write_text(
        repo_root / "workflows" / "binary-load.workflow.yaml",
        lines(
            "id: binary-load",
            "name: Binary Load",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: load_bin",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/logo.bin",
            "    outputs:",
            "      - artifacts/${run_id}/loaded.md",
        ),
    )
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    result = runner.run(
        workflow_id="binary-load",
        run_id="run_binary",
        inputs={"client": "sample-client-a"},
    )

    assert result.status == "failed"
    assert result.failed_step_id == "load_bin"
    assert str(runner.store.get_run("run_binary")["status"]) == "failed"
    assert runner.store.get_step_status("run_binary", "load_bin") == StepStatus.FAILED


def test_resume_reconciles_spec_that_gained_a_step(repo_root: Path) -> None:
    """Resume must create rows for steps added to the spec after the run started."""
    spec_path = repo_root / "workflows" / "growing.workflow.yaml"
    write_text(
        spec_path,
        lines(
            "id: growing",
            "name: Growing",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: first",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
            "    outputs:",
            "      - artifacts/${run_id}/first.md",
        ),
    )
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    first_run = runner.run(
        workflow_id="growing",
        run_id="run_growing",
        inputs={"client": "sample-client-a"},
    )
    assert first_run.status == "success"

    write_text(
        spec_path,
        lines(
            "id: growing",
            "name: Growing",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: first",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
            "    outputs:",
            "      - artifacts/${run_id}/first.md",
            "  - id: second",
            "    type: agent",
            "    role: reporter",
            "    depends_on: [first]",
            "    outputs:",
            "      - artifacts/${run_id}/second.md",
        ),
    )

    resumed = runner.resume("run_growing")

    assert resumed.status == "success"
    assert (repo_root / "artifacts" / "run_growing" / "second.md").exists()
    assert runner.store.get_step_status("run_growing", "second") == StepStatus.SUCCESS


def test_spec_loader_rejects_empty_output_template(repo_root: Path) -> None:
    write_text(
        repo_root / "workflows" / "empty-output.workflow.yaml",
        lines(
            "id: empty-output",
            "name: Empty Output",
            "steps:",
            "  - id: writer",
            "    type: agent",
            "    outputs:",
            "      - ' '",
        ),
    )
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    with pytest.raises(WorkflowSpecError):
        runner.run(workflow_id="empty-output", run_id="run_empty_out", inputs={})


def test_spec_loader_rejects_unknown_input_requirement(repo_root: Path) -> None:
    write_text(
        repo_root / "workflows" / "bad-req.workflow.yaml",
        lines(
            "id: bad-req",
            "name: Bad Requirement",
            "inputs:",
            "  client: mandatory",
            "steps:",
            "  - id: writer",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/out.md",
        ),
    )
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    with pytest.raises(WorkflowSpecError):
        runner.run(workflow_id="bad-req", run_id="run_bad_req", inputs={"client": "x"})
