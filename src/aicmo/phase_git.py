from __future__ import annotations

import os
import signal
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, assert_never

from aicmo.errors import AicmoError
from aicmo.paths import parse_safe_id, resolve_inside_repo

_GIT_TIMEOUT_SECONDS: Final = 30.0
_TREE_KILL_TIMEOUT_SECONDS: Final = 5.0
_DETAIL_LIMIT: Final = 500


class PhaseGitMode(StrEnum):
    OFF = "off"
    DRY_RUN = "dry-run"
    COMMIT = "commit"
    PUSH = "push"
    MERGE = "merge"


type ActivePhaseGitMode = Literal[
    PhaseGitMode.DRY_RUN,
    PhaseGitMode.COMMIT,
    PhaseGitMode.PUSH,
    PhaseGitMode.MERGE,
]


class PhaseGitStatus(StrEnum):
    DISABLED = "disabled"
    DRY_RUN = "dry-run"
    UNAVAILABLE = "unavailable"
    NO_CHANGE = "no-change"
    COMMITTED = "committed"
    PUSHED = "pushed"
    MERGED = "merged"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PhaseGitResult:
    status: PhaseGitStatus
    message: str
    paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _PhaseGitContext:
    run_id: str
    phase_id: str
    paths: tuple[str, ...]


def run_phase_git(
    repo_root: Path,
    mode: PhaseGitMode,
    run_id: str,
    phase_id: str,
    reviewed_paths: tuple[str, ...] | None = None,
) -> PhaseGitResult:
    try:
        safe_run_id = parse_safe_id("run_id", run_id)
        safe_phase_id = parse_safe_id("phase_id", phase_id)
        match mode:
            case PhaseGitMode.OFF:
                result = PhaseGitResult(PhaseGitStatus.DISABLED, "")
            case (
                PhaseGitMode.DRY_RUN | PhaseGitMode.COMMIT | PhaseGitMode.PUSH | PhaseGitMode.MERGE
            ):
                if not reviewed_paths:
                    result = PhaseGitResult(
                        PhaseGitStatus.UNAVAILABLE,
                        f"phase-git {mode.value}: unavailable (no reviewed export paths)",
                    )
                else:
                    context = _PhaseGitContext(
                        run_id=safe_run_id,
                        phase_id=safe_phase_id,
                        paths=_reviewed_paths(repo_root, reviewed_paths),
                    )
                    result = _run_with_paths(repo_root, mode, context)
            case _ as unreachable:
                assert_never(unreachable)
    except AicmoError as exc:
        result = PhaseGitResult(
            PhaseGitStatus.FAILED,
            f"phase-git {mode.value}: {exc}",
        )
    return result


def _run_with_paths(
    repo_root: Path,
    mode: ActivePhaseGitMode,
    context: _PhaseGitContext,
) -> PhaseGitResult:
    match mode:
        case PhaseGitMode.DRY_RUN:
            return _dry_run(repo_root, context)
        case PhaseGitMode.COMMIT | PhaseGitMode.PUSH | PhaseGitMode.MERGE:
            if not _commit_phase(repo_root, context):
                return PhaseGitResult(
                    PhaseGitStatus.NO_CHANGE,
                    f"phase-git {mode.value}: no changes for {context.phase_id}",
                    context.paths,
                )
            match mode:
                case PhaseGitMode.COMMIT:
                    status = PhaseGitStatus.COMMITTED
                case PhaseGitMode.PUSH:
                    _git(repo_root, "push")
                    status = PhaseGitStatus.PUSHED
                case PhaseGitMode.MERGE:
                    _git(repo_root, "push")
                    _merge_current_branch(repo_root, context.run_id, context.phase_id)
                    status = PhaseGitStatus.MERGED
                case _ as unreachable:
                    assert_never(unreachable)
            return PhaseGitResult(
                status,
                f"phase-git {mode.value}: {status.value} {context.phase_id} for {context.run_id}",
                context.paths,
            )
        case _ as unreachable:
            assert_never(unreachable)


def _reviewed_paths(repo_root: Path, reviewed_paths: tuple[str, ...]) -> tuple[str, ...]:
    paths: list[str] = []
    for raw_path in reviewed_paths:
        resolved = resolve_inside_repo(repo_root, raw_path, {})
        if not resolved.is_file():
            msg = "reviewed export path is not a file"
            raise AicmoError(msg)
        relative = resolved.relative_to(repo_root.resolve()).as_posix()
        if relative not in paths:
            paths.append(relative)
    ignored = _git(repo_root, "check-ignore", "--quiet", "--", *paths, check=False)
    if ignored.returncode == 0:
        msg = "reviewed export path is ignored"
        raise AicmoError(msg)
    if ignored.returncode != 1:
        detail = ignored.stderr.strip() or ignored.stdout.strip()
        msg = f"git check-ignore failed: {detail[:_DETAIL_LIMIT]}"
        raise AicmoError(msg)
    return tuple(paths)


def _dry_run(repo_root: Path, context: _PhaseGitContext) -> PhaseGitResult:
    _git(repo_root, "rev-parse", "--is-inside-work-tree")
    branch = _git_text(repo_root, "branch", "--show-current") or "detached"
    return PhaseGitResult(
        PhaseGitStatus.DRY_RUN,
        f"phase-git dry-run: phase={context.phase_id} branch={branch} run_id={context.run_id} "
        f"reviewed_paths={len(context.paths)}",
        context.paths,
    )


def _commit_phase(repo_root: Path, context: _PhaseGitContext) -> bool:
    literal_paths = tuple(f":(literal){path}" for path in context.paths)
    _git(repo_root, "add", "--", *literal_paths)
    diff = _git(repo_root, "diff", "--cached", "--quiet", "--", *literal_paths, check=False)
    if diff.returncode == 0:
        return False
    if diff.returncode != 1:
        detail = diff.stderr.strip() or diff.stdout.strip()
        msg = f"git diff failed: {detail[:_DETAIL_LIMIT]}"
        raise AicmoError(msg)
    _git(
        repo_root,
        "commit",
        "--only",
        "-m",
        f"chore(phase): {context.phase_id} for {context.run_id}",
        "--",
        *literal_paths,
    )
    return True


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
    command = ["git", *args]
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=environment,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        msg = f"git {args[0]} could not start: {exc}"
        raise AicmoError(msg) from exc
    try:
        stdout, stderr = process.communicate(timeout=_GIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        with suppress(OSError, subprocess.TimeoutExpired):
            process.communicate(timeout=_TREE_KILL_TIMEOUT_SECONDS)
        msg = f"git {args[0]} timed out after {_GIT_TIMEOUT_SECONDS:g}s"
        raise AicmoError(msg) from exc
    if process.returncode is None:
        msg = f"git {args[0]} ended without a return code"
        raise AicmoError(msg)
    completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        msg = f"git {args[0]} failed: {detail[:_DETAIL_LIMIT]}"
        raise AicmoError(msg)
    return completed


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        with suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(  # noqa: S603
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],  # noqa: S607
                check=False,
                capture_output=True,
                timeout=_TREE_KILL_TIMEOUT_SECONDS,
            )
    else:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        with suppress(OSError):
            process.kill()
    with suppress(OSError, subprocess.TimeoutExpired):
        process.wait(timeout=_TREE_KILL_TIMEOUT_SECONDS)
