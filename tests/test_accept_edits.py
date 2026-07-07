"""Approval-gate edit flow: pre-edit snapshots and --accept-edits blessing."""

from __future__ import annotations

from pathlib import Path

import pytest

from aicmo.cli import parse_input_pairs
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore

_EDIT_MARKER = "EDITED BY OWNER: keep this wording."


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.fixture
def approval_repo(repo_root: Path) -> Path:
    _write(
        repo_root / "workflows" / "approval-edit.workflow.yaml",
        "\n".join(
            [
                "id: approval-edit",
                "name: Approval Edit Flow",
                "inputs:",
                "  client: required",
                "steps:",
                "  - id: load_context",
                "    type: file.load",
                "    paths:",
                "      - clients/${client}/config.md",
                "    outputs:",
                "      - artifacts/${run_id}/context.md",
                "  - id: draft",
                "    type: agent",
                "    role: copywriter",
                "    depends_on: [load_context]",
                "    prompt: playbooks/03-content/blog-article.md",
                "    outputs:",
                "      - artifacts/${run_id}/draft.md",
                "  - id: owner_gate",
                "    type: gate",
                "    requires_approval: true",
                "    depends_on: [draft]",
                "    outputs:",
                "      - artifacts/${run_id}/owner-approval.json",
                "  - id: report",
                "    type: agent",
                "    role: reporter",
                "    depends_on: [owner_gate]",
                "    outputs:",
                "      - artifacts/${run_id}/content-log.md",
            ],
        ),
    )
    return repo_root


def _runner(repo_root: Path) -> WorkflowRunner:
    return WorkflowRunner(repo_root=repo_root, store=WorkflowStore(repo_root / "runs.sqlite3"))


def _start_waiting_run(repo_root: Path, run_id: str) -> WorkflowRunner:
    runner = _runner(repo_root)
    result = runner.run("approval-edit", run_id, {"client": "sample-client-a"})
    assert result.status == "waiting_approval"
    return runner


def test_pre_edit_snapshot_captures_original_and_is_write_once(approval_repo: Path) -> None:
    runner = _start_waiting_run(approval_repo, "run_snap")
    draft = approval_repo / "artifacts" / "run_snap" / "draft.md"
    snapshot = approval_repo / "artifacts" / "run_snap" / "_pre_edit" / "draft__draft.md"
    original = draft.read_text(encoding="utf-8")
    assert snapshot.read_text(encoding="utf-8") == original

    # A crash-resume while still waiting must not re-snapshot (write-once).
    assert runner.resume("run_snap").status == "waiting_approval"
    draft.write_text(_EDIT_MARKER, encoding="utf-8")
    runner.approve("run_snap", "owner_gate", "owner", "ok", accept_edits=True)
    assert runner.resume("run_snap").status == "success"
    assert snapshot.read_text(encoding="utf-8") == original


def test_edit_without_accept_edits_is_regenerated(approval_repo: Path) -> None:
    runner = _start_waiting_run(approval_repo, "run_plain")
    draft = approval_repo / "artifacts" / "run_plain" / "draft.md"
    draft.write_text(_EDIT_MARKER, encoding="utf-8")
    changed = runner.approve("run_plain", "owner_gate", "owner", "ok")
    assert changed == []
    assert runner.resume("run_plain").status == "success"
    # Tamper detection keeps its default behavior: the edited file was regenerated.
    assert _EDIT_MARKER not in draft.read_text(encoding="utf-8")


def test_accept_edits_preserves_owner_changes(approval_repo: Path) -> None:
    runner = _start_waiting_run(approval_repo, "run_bless")
    draft = approval_repo / "artifacts" / "run_bless" / "draft.md"
    draft.write_text(_EDIT_MARKER, encoding="utf-8")
    changed = runner.approve("run_bless", "owner_gate", "owner", "ok", accept_edits=True)
    assert changed == ["artifacts/run_bless/draft.md"]
    assert runner.resume("run_bless").status == "success"
    assert draft.read_text(encoding="utf-8").strip() == _EDIT_MARKER


def test_accept_edits_without_changes_reports_nothing(approval_repo: Path) -> None:
    runner = _start_waiting_run(approval_repo, "run_clean")
    changed = runner.approve("run_clean", "owner_gate", "owner", "ok", accept_edits=True)
    assert changed == []
    assert runner.resume("run_clean").status == "success"


def test_parse_input_pairs() -> None:
    assert parse_input_pairs(["source_url=https://a.b/c?x=1", "k= v "]) == {
        "source_url": "https://a.b/c?x=1",
        "k": " v ",
    }
    with pytest.raises(Exception, match="key=value"):
        parse_input_pairs(["no-separator"])
