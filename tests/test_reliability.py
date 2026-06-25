from __future__ import annotations

from pathlib import Path

import pytest

from aicmo.errors import WorkflowExecutionError
from aicmo.reporter import flush_kb_updates
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


def _seed_kb(tmp_path: Path) -> WorkflowRunner:
    write_text(
        tmp_path / "workflows" / "seed-kb.workflow.yaml",
        lines(
            "id: seed-kb",
            "name: Seed KB",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: kb",
            "    type: kb.update",
            "    outputs:",
            "      - artifacts/${run_id}/kb.md",
        ),
    )
    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
    )
    runner.run(workflow_id="seed-kb", run_id="run_kb", inputs={"client": "acme"})
    return runner


def test_kb_flush_idempotent_under_replay(tmp_path: Path) -> None:
    runner = _seed_kb(tmp_path)
    assert flush_kb_updates(tmp_path, runner.store, "acme") == 1

    # Simulate the crash window: the row was appended but never marked consumed.
    with runner.store.connect() as connection:
        connection.execute("update kb_updates set status = 'queued'")

    # The replay appends nothing (marker already present), so the count is 0.
    assert flush_kb_updates(tmp_path, runner.store, "acme") == 0

    insights = (tmp_path / "knowledge-base" / "acme" / "insights.md").read_text("utf-8")
    assert insights.count("KB Update Queue") == 1, "replay duplicated the KB block"


def test_resume_rejects_tampered_output(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))
    runner.run(
        workflow_id="blog-article",
        run_id="run_tamper",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    draft = repo_root / "artifacts" / "run_tamper" / "draft.md"
    draft.write_text("PARTIAL", encoding="utf-8")

    result = runner.resume("run_tamper")

    assert result.status == "success"
    restored = draft.read_text("utf-8")
    assert "PARTIAL" not in restored
    assert "Agent Step: draft" in restored


def test_gate_fails_closed_on_empty_text(tmp_path: Path) -> None:
    write_text(
        tmp_path / "workflows" / "empty-gate.workflow.yaml",
        lines(
            "id: empty-gate",
            "name: Empty Gate",
            "steps:",
            "  - id: g1",
            "    type: gate",
            "    outputs:",
            "      - artifacts/${run_id}/g1.json",
        ),
    )
    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
    )

    result = runner.run(workflow_id="empty-gate", run_id="run_eg", inputs={})

    assert result.status == "failed"
    assert result.failed_step_id == "g1"


def test_reject_undeclared_input(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    with pytest.raises(WorkflowExecutionError):
        runner.run(
            workflow_id="blog-article",
            run_id="run_badinput",
            inputs={"client": "sample-client-a", "topic": "x", "unexpected": "typo"},
        )
