"""Privacy boundary: secrets never persist to SQLite diagnostics or CLI output."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from aicmo.adapters import CommandAdapter
from aicmo.cli import app, ingest_inbox
from aicmo.errors import WorkflowExecutionError
from aicmo.redaction import contains_raw_secret, redact
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore

_BEARER_SECRET = "sk-live-LEAKME123456"
_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
_STDERR_SCRIPT = (
    "import sys\n"
    f'sys.stderr.write("Authorization: Bearer {_BEARER_SECRET}\\n")\n'
    f'sys.stderr.write("api_key={_AWS_KEY}\\n")\n'
    "sys.exit(3)\n"
)

_INPUTS = {"client": "sample-client-a", "topic": "보안 점검"}


def _persisted_diagnostics(db: Path) -> str:
    with closing(sqlite3.connect(db)) as connection:
        connection.row_factory = sqlite3.Row
        events = [
            f"{row['message']} {row['payload_json']}"
            for row in connection.execute("select message, payload_json from events")
        ]
        errors = [
            row["error_json"] or "" for row in connection.execute("select error_json from steps")
        ]
    return "\n".join(events + errors)


def test_failed_executor_stderr_secrets_absent_from_events(repo_root: Path) -> None:
    db = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db),
        adapter=CommandAdapter(command=(sys.executable, "-c", _STDERR_SCRIPT)),
    )

    result = runner.run("blog-article", "r_privacy", _INPUTS)

    blob = _persisted_diagnostics(db)
    assert result.status == "failed"
    assert _BEARER_SECRET not in blob
    assert _AWS_KEY not in blob
    # Diagnostics stay useful and legitimate client context stays intact.
    assert "executor exited 3" in blob
    assert "보안 점검" in blob


def test_ingest_dry_run_masks_signed_url_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inbox = tmp_path / "inbox" / "sample-client-a"
    inbox.mkdir(parents=True)
    (inbox / "sources.txt").write_text(
        "https://cdn.example.com/report.pdf?X-Amz-Signature=SECSIG99&X-Amz-Credential=AKIACRED7\n",
        encoding="utf-8",
    )

    ingest_inbox(client="sample-client-a", dry_run=True, repo=tmp_path)

    flat = capsys.readouterr().out.replace("\n", "")
    assert "cdn.example.com" in flat
    assert "SECSIG99" not in flat
    assert "AKIACRED7" not in flat


def test_ingest_cli_masks_customer_pii_in_url_and_filename(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inbox = repo_root / "inbox" / "sample-client-a"
    inbox.mkdir(parents=True)
    source = inbox / "고객명=김민수_010-9876-5432.txt"
    source.write_text(
        "https://example.test/010-9876-5432?email=minsu.kim@example.test\n제공 원문\n",
        encoding="utf-8",
    )
    fake_runner = Mock()
    fake_runner.run.return_value = SimpleNamespace(status="waiting_approval")
    monkeypatch.setattr("aicmo.cli.run_cmds.make_runner", Mock(return_value=fake_runner))
    cli = CliRunner()

    dry_run = cli.invoke(
        app,
        ["ingest", "--client", "sample-client-a", "--dry-run", "--repo", str(repo_root)],
    )
    live_run = cli.invoke(
        app,
        ["ingest", "--client", "sample-client-a", "--repo", str(repo_root)],
    )

    output = dry_run.output + live_run.output
    assert dry_run.exit_code == 0
    assert live_run.exit_code == 0, live_run.output
    assert "김민수" not in output
    assert "010-9876-5432" not in output
    assert "minsu.kim@example.test" not in output
    assert "[customer-name]" in output
    assert "[customer-phone]" in output
    assert "[customer-email]" in output


def test_raw_credential_inputs_rejected(repo_root: Path) -> None:
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
    )

    with pytest.raises(WorkflowExecutionError, match="credential"):
        runner.run(
            "blog-article",
            "r_rawsecret",
            {"client": "sample-client-a", "topic": f"use Bearer {_BEARER_SECRET}"},
        )


def test_env_reference_inputs_accepted(repo_root: Path) -> None:
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
    )

    result = runner.run(
        "blog-article",
        "r_envref",
        {"client": "sample-client-a", "topic": "env:BLOG_TOPIC_TOKEN"},
    )

    assert result.status == "success"


def test_redaction_preserves_legitimate_content() -> None:
    korean = "문의: hong@example.com / 010-1234-5678 김대리, 서울 강남구"
    assert redact(korean) == korean

    masked = redact(f"Authorization: Bearer {_BEARER_SECRET}")
    assert _BEARER_SECRET not in masked
    assert "Bearer" in masked

    signed = redact("https://x.example/a.pdf?X-Amz-Signature=abc123&page=2")
    assert "abc123" not in signed
    assert "page=2" in signed


@pytest.mark.parametrize(
    "value",
    [
        "https://alice:supersecret@example.com/path",
        "env:KEY sk-test-credential-1234567890",
        "https://alice@example.com/path",
        "비밀번호=supersecret",
        "암호: supersecret",
        "인증키=abcdefgh12345678",
        "토큰=abcdefgh12345678",
        "비밀번호\uff1dsupersecret",
        "\uff50\uff41\uff53\uff53\uff57\uff4f\uff52\uff44\uff1dsupersecret",
    ],
)
def test_secret_references_cannot_hide_literals(value: str) -> None:
    assert contains_raw_secret(value)
    assert redact(value) != value
    assert contains_raw_secret("env:SAFE_KEY") is False
    assert contains_raw_secret("https://example.com/@public-name") is False


def test_secret_redaction_does_not_activate_fullwidth_markup_or_rewrite_prose() -> None:
    original = "\uff1cscript\uff1ealert(1)\uff1c/script\uff1e \uff21\uff22\uff23 ① ㎏"
    assert redact(original) == original
    assert redact(original + " 비밀번호=supersecret") == original + " 비밀번호=[redacted]"
    assert redact(original + " 비밀번호\uff1dsupersecret") == "[redacted]"
