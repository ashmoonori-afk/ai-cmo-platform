from __future__ import annotations

import subprocess
from enum import StrEnum
from pathlib import Path

from aicmo.errors import AicmoError
from aicmo.paths import parse_safe_id


class PhaseGitMode(StrEnum):
    OFF = "off"
    DRY_RUN = "dry-run"
    COMMIT = "commit"
    PUSH = "push"
    MERGE = "merge"


def run_phase_git(
    repo_root: Path,
    mode: PhaseGitMode,
    run_id: str,
    phase_id: str,
) -> list[str]:
    safe_run_id = parse_safe_id("run_id", run_id).value
    safe_phase_id = parse_safe_id("phase_id", phase_id).value
    if mode == PhaseGitMode.OFF:
        return []
    if mode == PhaseGitMode.DRY_RUN:
        return _dry_run(repo_root, safe_run_id, safe_phase_id)
    _commit_phase(repo_root, safe_run_id, safe_phase_id)
    if mode == PhaseGitMode.COMMIT:
        return [
            f"phase-git commit: staged and committed {safe_phase_id} artifacts for {safe_run_id}",
        ]
    _git(repo_root, "push")
    if mode == PhaseGitMode.PUSH:
        return [f"phase-git push: pushed {safe_phase_id} phase commit for {safe_run_id}"]
    _merge_current_branch(repo_root, safe_run_id, safe_phase_id)
    return [f"phase-git merge: merged pushed {safe_phase_id} phase branch for {safe_run_id}"]


def _dry_run(repo_root: Path, run_id: str, phase_id: str) -> list[str]:
    if _git(repo_root, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        return [
            f"phase-git dry-run: phase={phase_id} not a git repository run_id={run_id}",
            "phase-git dry-run: would run git add -A",
            f"phase-git dry-run: would commit 'chore(phase): {phase_id} for {run_id}'",
            "phase-git dry-run: push/merge require explicit --phase-git push|merge",
        ]
    branch = _git_text(repo_root, "branch", "--show-current") or "detached"
    status = _git_text(repo_root, "status", "--short")
    dirty = "yes" if status else "no"
    return [
        f"phase-git dry-run: phase={phase_id} branch={branch} run_id={run_id} dirty={dirty}",
        "phase-git dry-run: would run git add -A",
        f"phase-git dry-run: would commit 'chore(phase): {phase_id} for {run_id}'",
        "phase-git dry-run: push/merge require explicit --phase-git push|merge",
    ]


def _commit_phase(repo_root: Path, run_id: str, phase_id: str) -> None:
    _git(repo_root, "add", "-A")
    if _git(repo_root, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    _git(repo_root, "commit", "-m", f"chore(phase): {phase_id} for {run_id}")


def _merge_current_branch(repo_root: Path, run_id: str, phase_id: str) -> None:
    branch = _git_text(repo_root, "branch", "--show-current")
    if branch in ("", "main", "master"):
        msg = "phase-git merge requires a non-default branch"
        raise AicmoError(msg)
    default_ref = _git_text(repo_root, "symbolic-ref", "refs/remotes/origin/HEAD", "--short")
    default_branch = default_ref.removeprefix("origin/") or "main"
    _git(repo_root, "fetch", "origin", default_branch)
    _git(repo_root, "checkout", default_branch)
    try:
        _git(repo_root, "pull", "--ff-only", "origin", default_branch)
        _git(
            repo_root,
            "merge",
            "--no-ff",
            branch,
            "-m",
            f"chore(phase): merge {phase_id} for {run_id}",
        )
        _git(repo_root, "push", "origin", default_branch)
    finally:
        _git(repo_root, "checkout", branch)


def _git_text(repo_root: Path, *args: str) -> str:
    return _git(repo_root, *args).stdout.strip()


def _git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        msg = f"git {' '.join(args)} failed: {detail}"
        raise AicmoError(msg)
    return completed
