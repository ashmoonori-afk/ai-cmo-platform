from __future__ import annotations

import sys
from pathlib import Path

from aicmo.adapters import OFFLINE_STUB_MARKER, CommandAdapter
from aicmo.gate import allowed_statuses, evaluate_artifacts
from aicmo.models import GateDecision, StepStatus
from aicmo.reporter import flush_kb_updates
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text

CLEAN = (
    "This is a complete marketing draft with a clear headline, real body copy, and a "
    "call to action. It is well over the soft length threshold and has no open markers."
)


def test_evaluate_fails_on_incomplete_marker() -> None:
    outcome = evaluate_artifacts(["# Draft\n\nTODO: write the introduction"])
    assert outcome.status == GateDecision.FAIL
    assert outcome.reasons


def test_evaluate_fails_on_empty_artifact() -> None:
    assert evaluate_artifacts([""]).status == GateDecision.FAIL
    assert evaluate_artifacts(["   \n  "]).status == GateDecision.FAIL


def test_evaluate_fails_on_unfilled_placeholder() -> None:
    text = "Intro {{offer}} outro that is otherwise long enough to clear the length bar."
    assert evaluate_artifacts([text]).status == GateDecision.FAIL


def test_evaluate_passes_clean_artifact() -> None:
    assert evaluate_artifacts([CLEAN]).status == GateDecision.PASS


def test_evaluate_warns_on_thin_content() -> None:
    assert evaluate_artifacts(["Too short."]).status == GateDecision.WARN


def test_evaluate_warns_on_offline_stub_even_with_marker_words() -> None:
    text = f"# draft\n\n{OFFLINE_STUB_MARKER} It lists TODO and TBD only as forbidden examples."
    assert evaluate_artifacts([text]).status == GateDecision.WARN


def test_allowed_statuses_parsing() -> None:
    assert allowed_statuses("status in ['PASS','WARN']") == frozenset({"PASS", "WARN"})
    assert allowed_statuses(None) == frozenset({"PASS", "WARN"})
    assert allowed_statuses("status == 'PASS'") == frozenset({"PASS"})


def test_runner_gate_fails_run_on_incomplete_artifact(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    script = "print('TODO: not written yet, placeholder draft only')"
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db_path),
        adapter=CommandAdapter(command=(sys.executable, "-c", script)),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_gatefail",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "failed"
    assert result.failed_step_id == "review"


def test_runner_gate_passes_clean_default(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_gatepass",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "success"
    assert runner.store.get_step_status("run_gatepass", "review") == StepStatus.SUCCESS


def test_kb_flush_appends_and_is_idempotent(tmp_path: Path) -> None:
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
    write_text(tmp_path / "clients" / "acme" / "config.md", "client config")
    write_text(tmp_path / "clients" / "acme" / "brand-guidelines.md", "brand rules")
    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
    )
    result = runner.run(workflow_id="seed-kb", run_id="run_kb", inputs={"client": "acme"})
    assert result.status == "success"

    flushed = flush_kb_updates(tmp_path, runner.store, "acme")

    assert flushed == 1
    insights = (tmp_path / "knowledge-base" / "acme" / "insights.md").read_text("utf-8")
    assert "acme" in insights
    assert "KB Update Queue" in insights
    assert flush_kb_updates(tmp_path, runner.store, "acme") == 0
