from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


def test_blog_workflow_run_is_idempotent_and_records_artifacts(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_test_blog",
        inputs={"client": "sample-client-a", "topic": "corporate flower subscription"},
    )
    second_result = runner.resume("run_test_blog")

    assert result.status == "success"
    assert second_result.status == "success"
    artifacts_dir = repo_root / "artifacts" / "run_test_blog"
    assert (artifacts_dir / "context.md").exists()
    assert (artifacts_dir / "keyword-brief.md").exists()
    # Content, not just existence: the offline LocalAdapter sentinel and a real gate status.
    draft = (artifacts_dir / "draft.md").read_text("utf-8")
    assert "Local deterministic adapter completed." in draft
    review = (artifacts_dir / "review.json").read_text("utf-8")
    assert '"status":' in review

    with closing(sqlite3.connect(db_path)) as connection, connection:
        steps = connection.execute(
            "select step_id, status, attempt from steps where run_id = ? order by step_order",
            ("run_test_blog",),
        ).fetchall()
        artifacts_count = connection.execute(
            "select count(*) from artifacts where run_id = ?",
            ("run_test_blog",),
        ).fetchone()[0]

    assert steps == [
        ("load_context", "success", 1),
        ("keyword_research", "success", 1),
        ("draft", "success", 1),
        ("review", "success", 1),
        ("report", "success", 1),
    ]
    assert artifacts_count == 5


def test_resume_continues_from_failed_step_without_repeating_successes(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    prompt = repo_root / "playbooks" / "03-content" / "blog-article.md"
    prompt.unlink()
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    failed = runner.run(
        workflow_id="blog-article",
        run_id="run_retry",
        inputs={"client": "sample-client-a", "topic": "corporate flower subscription"},
    )

    assert failed.status == "failed"
    assert failed.failed_step_id == "draft"

    write_text(prompt, "# Blog Article\n\nDraft the article.\n")
    resumed = runner.resume("run_retry")

    assert resumed.status == "success"

    with closing(sqlite3.connect(db_path)) as connection, connection:
        attempts = dict(
            connection.execute(
                "select step_id, attempt from steps where run_id = ?",
                ("run_retry",),
            ).fetchall(),
        )

    assert attempts["load_context"] == 1
    assert attempts["keyword_research"] == 1
    assert attempts["draft"] == 2


def test_manual_gate_blocks_until_approval(repo_root: Path) -> None:
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
            "  - id: report",
            "    type: agent",
            "    role: reporter",
            "    depends_on: [owner_gate]",
            "    outputs:",
            "      - artifacts/${run_id}/approved-report.md",
        ),
    )
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db_path))

    blocked = runner.run(
        workflow_id="approval-demo",
        run_id="run_needs_approval",
        inputs={"client": "sample-client-a"},
    )
    runner.approve("run_needs_approval", "owner_gate", reviewer="owner", notes="Approved")
    resumed = runner.resume("run_needs_approval")

    assert blocked.status == "waiting_approval"
    assert resumed.status == "success"
    assert (repo_root / "artifacts" / "run_needs_approval" / "approved-report.md").exists()

    gate_payload = json.loads(
        (repo_root / "artifacts" / "run_needs_approval" / "owner-gate.json").read_text(
            encoding="utf-8",
        ),
    )
    assert gate_payload["status"] == "PASS"
