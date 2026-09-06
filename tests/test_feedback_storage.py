from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from aicmo import reporter
from aicmo.cli import app
from aicmo.errors import WorkflowExecutionError
from aicmo.feedback import prepare_feedback, record_artifact_feedback
from aicmo.paths import resolve_inside_repo
from aicmo.redaction import safe_kb_text
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import write_text
from tests.test_reliability import seed_kb


def test_feedback_preserves_original_bytes_and_deduplicates_normalized_replay(
    tmp_path: Path,
) -> None:
    target = tmp_path / "knowledge-base/_engine-improvements/artifact-feedback.md"
    target.parent.mkdir(parents=True)
    before = b"\xef\xbb\xbf# Existing\r\nKeep these bytes without final newline"
    target.write_bytes(before)
    record_artifact_feedback(tmp_path, "shop", "run-one", "markdown", "Shorter CTA.\r\nKeep facts.")
    first = target.read_bytes()
    assert first.startswith(before)
    record_artifact_feedback(tmp_path, "shop", "run-one", "markdown", "Shorter CTA.\nKeep facts.")
    assert target.read_bytes() == first
    record_artifact_feedback(tmp_path, "shop", "run-one", "markdown", "Different feedback.")
    assert target.read_bytes().startswith(first)
    assert target.read_text(encoding="utf-8-sig").count("<!-- feedback:v1:") == 2


def test_new_feedback_and_kb_rows_minimize_pii_and_secrets(tmp_path: Path) -> None:
    secret = "Bearer sk-test-feedback-credential-0123456789"
    raw = f"Customer name: Jane Doe\nCustomer phone: +1 (212) 555-0123\n{secret}"
    safe = safe_kb_text(raw)
    assert safe_kb_text(safe) == safe
    target = record_artifact_feedback(tmp_path, "shop", "r", raw, raw)
    runner = seed_kb(tmp_path)
    runner.store.record_kb_update("run_kb", "kb", "acme", "artifacts/run_kb/insight.md", raw)
    rows = runner.store.pending_kb_updates("acme")
    persisted = "\n".join(str(row["content"]) for row in rows)
    reporter.flush_kb_updates(tmp_path, runner.store, "acme")
    persisted += target.read_text(encoding="utf-8")
    persisted += (tmp_path / "knowledge-base/acme/insights.md").read_text(encoding="utf-8")
    for value in ("Jane Doe", "212", "sk-test-feedback-credential-0123456789"):
        assert value not in persisted


@pytest.mark.parametrize(
    "content", ["", " \n\t", "\u200b", "\u0301", "safe\x1btext", "x\u202ey", "x" * 501]
)
def test_invalid_feedback_fails_before_persistence(tmp_path: Path, content: str) -> None:
    with pytest.raises(WorkflowExecutionError):
        record_artifact_feedback(tmp_path, "shop", "r", "markdown", content)
    assert not (tmp_path / "knowledge-base").exists()


def test_marker_text_in_feedback_cannot_suppress_later_record(tmp_path: Path) -> None:
    body = prepare_feedback("shop", "r", "markdown", "Later record")
    digest = hashlib.sha256(body.encode()).hexdigest()
    forged = f"A quoted marker:\n<!-- feedback:v1:{digest} -->"
    target = record_artifact_feedback(tmp_path, "shop", "r", "markdown", forged)
    record_artifact_feedback(tmp_path, "shop", "r", "markdown", "Later record")
    result = target.read_text(encoding="utf-8")
    assert "    <!-- feedback:v1:" in result
    assert "- feedback: Later record" in result


def test_invalid_existing_encoding_and_replace_failure_preserve_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "knowledge-base/_engine-improvements/artifact-feedback.md"
    target.parent.mkdir(parents=True)
    before = b"\xff\xfeunchanged"
    target.write_bytes(before)
    with pytest.raises(WorkflowExecutionError, match="not UTF-8"):
        record_artifact_feedback(tmp_path, "shop", "r", "markdown", "Safe feedback")
    assert target.read_bytes() == before
    before = b"# Good existing file\r\n"
    target.write_bytes(before)
    monkeypatch.setattr(
        Path, "replace", Mock(side_effect=PermissionError("synthetic replace failure"))
    )
    with pytest.raises(PermissionError):
        record_artifact_feedback(tmp_path, "shop", "r", "markdown", "Safe feedback")
    assert target.read_bytes() == before
    assert list(target.parent.glob("*.tmp")) == []


def test_reporter_preserves_prefix_and_failed_append_does_not_consume(
    tmp_path: Path,
) -> None:
    runner = seed_kb(tmp_path)
    target = tmp_path / "knowledge-base/acme/insights.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xffbad UTF8")
    with pytest.raises(WorkflowExecutionError):
        reporter.flush_kb_updates(tmp_path, runner.store, "acme")
    assert len(runner.store.pending_kb_updates("acme")) == 1
    before = b"\xef\xbb\xbf# Existing\r\nLast line"
    target.write_bytes(before)
    assert reporter.flush_kb_updates(tmp_path, runner.store, "acme") == 1
    first = target.read_bytes()
    assert first.startswith(before)
    with runner.store.connect() as connection:
        connection.execute("update kb_updates set status='queued'")
    assert reporter.flush_kb_updates(tmp_path, runner.store, "acme") == 0
    assert target.read_bytes() == first


def test_feedback_rejects_link_without_touching_external_file(tmp_path: Path) -> None:
    target = tmp_path / "knowledge-base/_engine-improvements/artifact-feedback.md"
    target.parent.mkdir(parents=True)
    outside = tmp_path / "external.md"
    outside.write_bytes(b"Keep original")
    try:
        target.symlink_to(outside)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows host does not permit creating symbolic links")
        raise
    with pytest.raises(WorkflowExecutionError, match="symbolic link"):
        record_artifact_feedback(tmp_path, "shop", "r", "markdown", "Safe feedback")
    assert target.is_symlink()
    assert outside.read_bytes() == b"Keep original"


def test_reporter_recognizes_legacy_marker_without_rewriting(tmp_path: Path) -> None:
    runner = seed_kb(tmp_path)
    # A record already appended by an older version need not be rewritten to replay it.
    with runner.store.connect() as connection:
        connection.execute("update kb_updates set content = ?", ("x" * 600,))
    row = runner.store.pending_kb_updates("acme")[0]
    marker = f"<!-- kb:{row['run_id']}:{row['step_id']}:{row['path']} -->"
    target = tmp_path / "knowledge-base/acme/insights.md"
    target.parent.mkdir(parents=True)
    before = f"# Existing\r\n{marker}\r\nLegacy record".encode("utf-8-sig")
    target.write_bytes(before)
    assert reporter.flush_kb_updates(tmp_path, runner.store, "acme") == 0
    assert target.read_bytes() == before
    assert runner.store.pending_kb_updates("acme") == []


def test_kb_workflow_accepts_maximum_length_identifiers(tmp_path: Path) -> None:
    identifier = "a" * 128
    write_text(tmp_path / "clients" / identifier / "config.md", "client config")
    write_text(tmp_path / "clients" / identifier / "brand-guidelines.md", "brand rules")
    write_text(
        tmp_path / "workflows/long-ids.workflow.yaml",
        f"id: long-ids\nname: Long IDs\ninputs:\n  client: required\nsteps:\n"
        f"  - id: {identifier}\n    type: kb.update\n"
        "    outputs:\n      - artifacts/kb.md\n",
    )
    runner = WorkflowRunner(
        repo_root=tmp_path, store=WorkflowStore(tmp_path / ".aicmo/runs.sqlite3")
    )
    runner.run(workflow_id="long-ids", run_id=identifier, inputs={"client": identifier})
    rows = runner.store.pending_kb_updates(identifier)
    assert len(rows) == 1
    assert rows[0]["run_id"] == rows[0]["step_id"] == rows[0]["client"] == identifier
    assert reporter.flush_kb_updates(tmp_path, runner.store, identifier) == 1


def test_feedback_concurrent_processes_keep_unique_records(tmp_path: Path) -> None:
    script = (
        "from pathlib import Path; from aicmo.feedback import record_artifact_feedback; "
        "import sys; record_artifact_feedback("
        "Path(sys.argv[1]), 'shop', 'r', 'markdown', sys.argv[2])"
    )
    with (
        subprocess.Popen(  # noqa: S603 — fixed script and argument vector, no shell
            [sys.executable, "-c", script, str(tmp_path), "First"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as first,
        subprocess.Popen(  # noqa: S603 — fixed script and argument vector, no shell
            [sys.executable, "-c", script, str(tmp_path), "Second"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as second,
        subprocess.Popen(  # noqa: S603 — fixed script and argument vector, no shell
            [sys.executable, "-c", script, str(tmp_path), "First"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as duplicate,
    ):
        for process in (first, second, duplicate):
            _stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr.decode()
    text = (tmp_path / "knowledge-base/_engine-improvements/artifact-feedback.md").read_text(
        encoding="utf-8"
    )
    assert text.count("- feedback: First") == text.count("- feedback: Second") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows byte-range locking")
def test_windows_lock_uses_offset_zero_even_for_nonempty_lock_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = tmp_path / "knowledge-base/_engine-improvements/artifact-feedback.md.lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"existing lock bytes")
    offsets: list[int] = []
    real = importlib.import_module("msvcrt")

    def locking(fd: int, mode: int, count: int) -> None:
        offsets.append(os.lseek(fd, 0, os.SEEK_CUR))
        real.locking(fd, mode, count)

    wrapper = Mock(LK_LOCK=real.LK_LOCK, LK_UNLCK=real.LK_UNLCK, locking=locking)
    monkeypatch.setattr("aicmo.reporter.importlib.import_module", Mock(return_value=wrapper))
    record_artifact_feedback(tmp_path, "shop", "r", "markdown", "Safe feedback")
    assert lock.read_bytes() == b"existing lock bytes"
    assert offsets == [0, 0]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows resolved path namespaces")
@pytest.mark.parametrize("base", ["C:\\repo", "\\\\server\\share\\repo"])
def test_windows_resolved_namespace_preserves_containment(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    root = Path(base)

    def resolved(path: Path) -> Path:
        if path == root:
            return root
        raw = str(path)
        extended = "\\\\?\\UNC\\" + raw[2:] if raw.startswith("\\\\") else "\\\\?\\" + raw
        return Path(extended)

    monkeypatch.setattr(Path, "resolve", resolved)
    assert resolve_inside_repo(root, "knowledge-base", {}) == root / "knowledge-base"
    external = root.parent / "outside"

    def resolved_external(path: Path) -> Path:
        return root if path == root else resolved(external)

    monkeypatch.setattr(Path, "resolve", resolved_external)
    with pytest.raises(WorkflowExecutionError, match="escapes repo root"):
        resolve_inside_repo(root, "knowledge-base", {})


def test_feedback_preflight_prevents_starting_workflow(repo_root: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "run",
            "blog-article",
            "--client",
            "sample-client-a",
            "--topic",
            "safe",
            "--run-id",
            "rejected-feedback",
            "--repo",
            str(repo_root),
            "--feedback",
            "x" * 501,
        ],
    )
    assert isinstance(result.exception, WorkflowExecutionError)
    assert not (repo_root / "artifacts/rejected-feedback").exists()
