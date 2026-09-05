
from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import Console

from aicmo.adapters import CommandAdapter, LocalAdapter, StepAdapter
from aicmo.anthropic_adapter import AnthropicAdapter
from aicmo.errors import AicmoError
from aicmo.models import RunResult, RunStatus, WorkflowStep
from aicmo.phase_git import PhaseGitMode, PhaseGitResult, PhaseGitStatus, run_phase_git
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore

console = Console()
err_console = Console(stderr=True)

EXIT_FAILED = 1
EXIT_WAITING_APPROVAL = 75  # EX_TEMPFAIL: paused for approval; resume after the gate is approved
type PhaseAnnouncer = Callable[[WorkflowStep, tuple[str, ...]], None]


def exit_code_for(status: str) -> int:
    if status == RunStatus.FAILED.value:
        return EXIT_FAILED
    if status == RunStatus.WAITING_APPROVAL.value:
        return EXIT_WAITING_APPROVAL
    return 0

def emit_result(result: RunResult) -> None:
    console.print(f"{result.run_id}: {result.status}")
    if result.failed_step_id is not None:
        console.print(f"failed_step: {result.failed_step_id}")
    code = exit_code_for(result.status)
    if code != 0:
        raise typer.Exit(code)

def emit_phase_deliverables(step: WorkflowStep, deliverables: tuple[str, ...]) -> None:
    console.print(f"phase {step.id} deliverables:")
    for deliverable in deliverables:
        console.print(f"  {deliverable}")

def emit_phase_git_result(result: PhaseGitResult) -> None:
    if result.message:
        console.print(result.message)
    if result.status == PhaseGitStatus.FAILED:
        raise AicmoError(result.message)


def phase_git_callback(
    repo_root: Path,
    mode: PhaseGitMode,
    run_id: str,
) -> PhaseAnnouncer | None:
    if mode == PhaseGitMode.OFF:
        return None

    def completed(step: WorkflowStep, _deliverables: tuple[str, ...]) -> None:
        emit_phase_git_result(run_phase_git(repo_root, mode, run_id, step.id))

    return completed

def default_db(repo: Path) -> Path:
    return repo / ".aicmo" / "runs.sqlite3"

def parse_input_pairs(pairs: list[str]) -> dict[str, str]:
    """Parse repeated --input key=value options. The workflow spec still decides
    which keys are declared; malformed pairs fail fast here with a clear message."""
    parsed: dict[str, str] = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key.strip():
            message = f"expected key=value, got: {pair!r}"
            raise typer.BadParameter(message)
        parsed[key.strip()] = value
    return parsed

def make_runner(
    repo: Path,
    db: Path | None,
    adapter: StepAdapter | None = None,
    review_adapter: StepAdapter | None = None,
    phase_announcer: PhaseAnnouncer | None = None,
    phase_completed: PhaseAnnouncer | None = None,
) -> WorkflowRunner:
    repo_root = repo.resolve()
    store = WorkflowStore(db or default_db(repo_root))
    return WorkflowRunner(
        repo_root=repo_root,
        store=store,
        adapter=adapter or LocalAdapter(),
        review_adapter=review_adapter,
        phase_announcer=phase_announcer,
        phase_completed=phase_completed,
    )

def adapter_from_cmd(executor_cmd: str | None) -> StepAdapter | None:
    if not executor_cmd:
        return None
    return CommandAdapter(command=tuple(shlex.split(executor_cmd)))

_EXECUTOR_PRESETS = {
    "claude": ("claude", "-p"),
    "codex": ("codex", "exec"),
}


def adapter_for_executor(name: str | None) -> StepAdapter | None:
    if not name or name == "local":
        return None
    if name == "anthropic":
        return AnthropicAdapter()
    preset = _EXECUTOR_PRESETS.get(name)
    if preset is None:
        allowed = ", ".join(["local", "anthropic", *_EXECUTOR_PRESETS])
        msg = f"unknown executor '{name}' (use {allowed}, or --executor-cmd)"
        raise AicmoError(msg)
    return CommandAdapter(command=preset)

def select_adapter(
    executor: str | None,
    executor_cmd: str | None,
    use_anthropic: bool,
) -> StepAdapter | None:
    if executor_cmd:
        return adapter_from_cmd(executor_cmd)
    if executor:
        return adapter_for_executor(executor)
    if use_anthropic:
        return AnthropicAdapter()
    return None

def select_review_adapter(
    review: str | None,
    review_cmd: str | None,
    review_anthropic: bool,
) -> StepAdapter | None:
    if review_cmd:
        return adapter_from_cmd(review_cmd)
    if review:
        return adapter_for_executor(review)
    if review_anthropic:
        return AnthropicAdapter()
    return None

def compact_inputs(values: dict[str, str | None]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}
