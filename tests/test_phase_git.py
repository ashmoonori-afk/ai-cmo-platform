from __future__ import annotations

import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from aicmo import phase_git as phase_git_module
from aicmo.cli import app
from aicmo.phase_git import PhaseGitMode, run_phase_git
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_text(repo: Path, *args: str) -> str:
    return _git(repo, *args).stdout.strip()


def _initialized_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "Phase Git Test")
    _git(repo, "config", "user.email", "phase-git@example.invalid")
    write_text(repo / ".gitignore", "ignored/\n")
    write_text(repo / "exports" / "reviewed.md", "reviewed v1\n")
    write_text(repo / "unrelated.txt", "unrelated v1\n")
    _git(repo, "add", "--", ".gitignore", "exports/reviewed.md", "unrelated.txt")
    _git(repo, "commit", "-m", "initial")
    return repo


def test_phase_git_commits_only_reviewed_export_path_when_worktree_dirty(
    tmp_path: Path,
) -> None:
    # Given: one reviewed export, one unrelated tracked edit, and one ignored artifact.
    repo = _initialized_repo(tmp_path)
    write_text(repo / "exports" / "reviewed.md", "reviewed v2\n")
    write_text(repo / "unrelated.txt", "unrelated v2\n")
    write_text(repo / "ignored" / "trace.log", "not a delivery\n")

    # When: phase-Git is given the exact reviewed export path.
    result = run_phase_git(
        repo,
        PhaseGitMode.COMMIT,
        "run_1",
        "reviewed_export",
        reviewed_paths=("exports/reviewed.md",),
    )

    # Then: only that path is committed; unrelated and ignored work remains outside delivery.
    assert result.status == "committed", result.message
    assert result.paths == ("exports/reviewed.md",)
    assert _git_text(repo, "show", "--pretty=", "--name-only", "HEAD") == ("exports/reviewed.md")
    assert _git_text(repo, "diff", "--cached", "--name-only") == ""
    assert _git(repo, "status", "--short").stdout == " M unrelated.txt\n"


def test_phase_git_reports_no_change_without_claiming_a_commit(tmp_path: Path) -> None:
    # Given: the reviewed export already matches HEAD.
    repo = _initialized_repo(tmp_path)
    initial_head = _git_text(repo, "rev-parse", "HEAD")

    # When: commit mode runs for that exact unchanged export.
    result = run_phase_git(
        repo,
        PhaseGitMode.COMMIT,
        "run_2",
        "reviewed_export",
        reviewed_paths=("exports/reviewed.md",),
    )

    # Then: the typed outcome and repository both say no commit happened.
    assert result.status == "no-change", result.message
    assert "no changes" in result.message
    assert _git_text(repo, "rev-parse", "HEAD") == initial_head


def test_phase_git_mutation_is_unavailable_without_reviewed_export_paths(
    tmp_path: Path,
) -> None:
    # Given: a dirty repository but no reviewed export manifest.
    repo = _initialized_repo(tmp_path)
    write_text(repo / "unrelated.txt", "unrelated v2\n")
    initial_head = _git_text(repo, "rev-parse", "HEAD")

    # When: commit mode is requested without an explicit reviewed path set.
    result = run_phase_git(repo, PhaseGitMode.COMMIT, "run_3", "reviewed_export")

    # Then: phase-Git does not stage or commit anything.
    assert result.status == "unavailable"
    assert _git_text(repo, "rev-parse", "HEAD") == initial_head
    assert _git_text(repo, "diff", "--cached", "--name-only") == ""


@pytest.mark.parametrize("reviewed_path", ["../outside.md", "ignored/trace.log"])
def test_phase_git_rejects_untrusted_or_ignored_reviewed_paths(
    tmp_path: Path,
    reviewed_path: str,
) -> None:
    # Given: a path that is outside the repository or intentionally ignored.
    repo = _initialized_repo(tmp_path)
    write_text(tmp_path / "outside.md", "outside\n")
    write_text(repo / "ignored" / "trace.log", "ignored\n")
    initial_head = _git_text(repo, "rev-parse", "HEAD")

    # When: the malformed manifest path is submitted to phase-Git.
    result = run_phase_git(
        repo,
        PhaseGitMode.COMMIT,
        "run_4",
        "reviewed_export",
        reviewed_paths=(reviewed_path,),
    )

    # Then: it returns a typed failure without touching the index or history.
    assert result.status == "failed"
    assert result.paths == ()
    assert _git_text(repo, "rev-parse", "HEAD") == initial_head
    assert _git_text(repo, "diff", "--cached", "--name-only") == ""


def test_phase_git_timeout_cleanup_is_bounded_typed_noninteractive_and_tree_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a Git child that never returns before the configured deadline.
    repo = _initialized_repo(tmp_path)
    write_text(repo / "exports" / "reviewed.md", "reviewed v2\n")

    class HangingGit:
        pid = 424_242
        returncode: int | None = None
        observed_env: ClassVar[dict[str, str]] = {}
        observed_timeouts: ClassVar[list[float | None]] = []
        tree_terminated: ClassVar[bool] = False

        def __init__(
            self,
            command: list[str],
            *,
            cwd: Path,
            stdout: int,
            stderr: int,
            text: bool,
            encoding: str,
            env: dict[str, str],
            creationflags: int = 0,
            start_new_session: bool = False,
        ) -> None:
            del command, cwd, stdout, stderr, text, encoding, creationflags, start_new_session
            type(self).observed_env = env

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            type(self).observed_timeouts.append(timeout)
            raise subprocess.TimeoutExpired(cmd="git", timeout=timeout or -1)

        def poll(self) -> int | None:
            return self.returncode

    def terminate_tree(process: HangingGit) -> None:
        process.returncode = -9
        HangingGit.tree_terminated = True

    monkeypatch.setattr(subprocess, "Popen", HangingGit)
    monkeypatch.setattr(phase_git_module, "_terminate_process_tree", terminate_tree)

    # When: the public phase hook reaches the hung Git command.
    result = run_phase_git(
        repo,
        PhaseGitMode.COMMIT,
        "run_5",
        "reviewed_export",
        reviewed_paths=("exports/reviewed.md",),
    )

    # Then: it fails truthfully and both communicate calls stay bounded after tree cleanup.
    assert result.status == "failed"
    assert "timed out" in result.message
    assert HangingGit.observed_env["GIT_TERMINAL_PROMPT"] == "0"
    assert HangingGit.observed_timeouts == [30.0, 5.0]
    assert HangingGit.tree_terminated


def test_cli_resume_reuses_persisted_phase_git_policy(repo_root: Path) -> None:
    # Given: a run paused at an owner gate with dry-run phase-Git selected.
    write_text(
        repo_root / "workflows" / "phase-policy.workflow.yaml",
        lines(
            "id: phase-policy",
            "name: Phase Policy",
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
            "      - artifacts/${run_id}/report.md",
        ),
    )
    cli = CliRunner()
    started = cli.invoke(
        app,
        [
            "run",
            "phase-policy",
            "--client",
            "sample-client-a",
            "--phase-git",
            "dry-run",
            "--run-id",
            "run_policy",
            "--repo",
            str(repo_root),
        ],
    )
    approved = cli.invoke(
        app,
        ["approve", "run_policy", "owner_gate", "--repo", str(repo_root)],
    )

    # When: resume is invoked twice without repeating the phase-Git option.
    resumed = cli.invoke(app, ["resume", "run_policy", "--repo", str(repo_root)])
    repeated = cli.invoke(app, ["resume", "run_policy", "--repo", str(repo_root)])

    # Then: both resumes succeed and the original opt-in policy remains observable and stored.
    assert started.exit_code == 75, started.output
    assert approved.exit_code == 0, approved.output
    assert resumed.exit_code == 0, resumed.output
    assert "phase-git dry-run: unavailable" in resumed.output
    assert repeated.exit_code == 0, repeated.output
    store = WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3")
    assert store.get_phase_git_mode("run_policy") == "dry-run"


def test_resume_help_exposes_persisted_phase_git_policy_option() -> None:
    # Given: the public CLI.
    cli = CliRunner()

    # When: an operator asks for resume help.
    result = cli.invoke(app, ["resume", "--help"])

    # Then: the policy option and persistence behavior are discoverable.
    assert result.exit_code == 0, result.output
    assert "--phase-git" in result.output
    assert "persisted" in result.output.lower()
