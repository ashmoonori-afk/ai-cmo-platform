
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from aicmo.feedback import record_artifact_feedback
from aicmo.ingest import InboxItem, archive_item, retain_failed_urls, scan_inbox
from aicmo.phase_git import PhaseGitMode, run_phase_git
from aicmo.redaction import redact
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore

from ._options import (
    AnthropicOpt,
    ExecutorCmdOpt,
    ExecutorCmdRunOpt,
    ExecutorOpt,
    ReviewAnthropicOpt,
    ReviewCmdOpt,
    ReviewOpt,
)
from ._shared import (
    EXIT_FAILED,
    compact_inputs,
    console,
    default_db,
    emit_phase_deliverables,
    emit_phase_git_result,
    emit_result,
    make_runner,
    parse_input_pairs,
    phase_git_callback,
    select_adapter,
    select_review_adapter,
)


class _RunIdFactory:
    callback: Callable[[], str] | None = None

    def __call__(self) -> str:
        if self.callback is None:
            msg = "run id factory is not registered"
            raise RuntimeError(msg)
        return self.callback()


generated_run_id = _RunIdFactory()


def run_workflow(
    workflow_id: Annotated[str, typer.Argument(help="Workflow id under workflows/*.workflow.yaml")],
    client: Annotated[str | None, typer.Option("--client")] = None,
    topic: Annotated[str | None, typer.Option("--topic")] = None,
    target_keyword: Annotated[str | None, typer.Option("--target-keyword")] = None,
    artifact_format: Annotated[
        str | None,
        typer.Option("--artifact-format", help="Requested artifact format, e.g. markdown, json."),
    ] = None,
    extra_inputs: Annotated[
        list[str] | None,
        typer.Option(
            "--input",
            help="Extra workflow input as key=value (repeatable), e.g. "
            "--input source_url=https://example.com/article",
        ),
    ] = None,
    feedback: Annotated[
        str | None,
        typer.Option("--feedback", help="Artifact feedback to persist for engine improvement."),
    ] = None,
    phase_git: Annotated[
        PhaseGitMode,
        typer.Option("--phase-git", help="Phase git automation: off|dry-run|commit|push|merge."),
    ] = PhaseGitMode.OFF,
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
    executor_cmd: ExecutorCmdRunOpt = None,
    executor: ExecutorOpt = None,
    anthropic: AnthropicOpt = False,
    review: ReviewOpt = None,
    review_cmd: ReviewCmdOpt = None,
    review_anthropic: ReviewAnthropicOpt = False,
) -> None:
    inputs = {
        **parse_input_pairs(extra_inputs or []),
        **compact_inputs(
            {
                "client": client,
                "topic": topic,
                "target_keyword": target_keyword,
                "artifact_format": artifact_format,
            },
        ),
    }
    run_id_value = run_id or generated_run_id()
    repo_root = repo.resolve()
    runner = make_runner(
        repo_root,
        db,
        select_adapter(executor, executor_cmd, anthropic),
        select_review_adapter(review, review_cmd, review_anthropic),
        emit_phase_deliverables,
        phase_git_callback(repo_root, phase_git, run_id_value),
    )
    runner.store.initialize()
    runner.store.ensure_phase_git_mode(run_id_value, phase_git.value)
    result = runner.run(workflow_id=workflow_id, run_id=run_id_value, inputs=inputs)
    if feedback and client:
        path = record_artifact_feedback(
            repo_root,
            client,
            run_id_value,
            artifact_format or "unspecified",
            feedback,
        )
        console.print(f"feedback: {path.relative_to(repo_root)}")
        emit_phase_git_result(run_phase_git(repo_root, phase_git, run_id_value, "feedback"))
    elif phase_git != PhaseGitMode.OFF:
        emit_phase_git_result(run_phase_git(repo_root, phase_git, run_id_value, "workflow"))
    emit_result(result)

def _ingest_item(runner: WorkflowRunner, item: InboxItem, client: str, repo_root: Path) -> bool:
    failed_urls: list[str] = []
    for url in item.urls:
        run_id = generated_run_id()
        console.print(f"{item.source_file.name} -> {run_id}: {redact(url)}", markup=False)
        try:
            result = runner.run(
                workflow_id="content-engine",
                run_id=run_id,
                inputs={"client": client, "source_url": url},
            )
        except Exception as exc:  # noqa: BLE001 — keep ingesting the remaining URLs
            console.print(redact(f"  failed: {type(exc).__name__}: {exc}"), markup=False)
            failed_urls.append(url)
            continue
        console.print(f"  {result.status}", markup=False)
        if result.status not in ("success", "waiting_approval"):
            failed_urls.append(url)

    if not item.urls:
        console.print(f"skipped (no urls): {item.source_file.name}", markup=False)
    elif not failed_urls:
        archived = archive_item(item)
        console.print(f"archived: {archived.relative_to(repo_root)}", markup=False)
    elif len(failed_urls) < len(item.urls):
        retain_failed_urls(item, failed_urls)
        console.print(
            f"retained {len(failed_urls)} failed url(s) in {item.source_file.name} for retry",
            markup=False,
        )
    else:
        console.print(f"kept for retry: {item.source_file.name}", markup=False)
    return bool(failed_urls)


def ingest_inbox(
    client: Annotated[str, typer.Option("--client", help="Client slug (inbox/<client>/)")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List inbox URLs and planned runs without executing."),
    ] = False,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
    executor_cmd: ExecutorCmdOpt = None,
    executor: ExecutorOpt = None,
    anthropic: AnthropicOpt = False,
    review: ReviewOpt = None,
    review_cmd: ReviewCmdOpt = None,
) -> None:
    """Turn URL files under inbox/<client>/ into content-engine runs.

    One .txt/.md file per source, one URL per line (# comments allowed). Each URL
    starts a content-engine run that stops at owner_gate for approval. Files whose
    URLs all reached waiting/success are archived to inbox/<client>/processed/;
    files with any failed run stay in the inbox for the next pass.
    """
    repo_root = repo.resolve()
    items = scan_inbox(repo_root, client)
    if not items:
        console.print(f"inbox empty: inbox/{client}/ (drop .txt/.md files with one URL per line)")
        return
    if dry_run:
        for item in items:
            console.print(f"{item.source_file.name}: {len(item.urls)} url(s)", markup=False)
            for url in item.urls:
                console.print(
                    f"  would run content-engine --input source_url={redact(url)}",
                    markup=False,
                )
        return
    runner = make_runner(
        repo_root,
        db,
        select_adapter(executor, executor_cmd, anthropic),
        select_review_adapter(review, review_cmd, review_anthropic=False),
        emit_phase_deliverables,
    )
    any_failed = False
    for item in items:
        any_failed |= _ingest_item(runner, item, client, repo_root)
    if any_failed:
        raise typer.Exit(EXIT_FAILED)

def resume_run(
    run_id: Annotated[str, typer.Argument()],
    phase_git: Annotated[
        PhaseGitMode | None,
        typer.Option(
            "--phase-git",
            help="Persisted phase-Git policy; omit to reuse the mode selected by run.",
        ),
    ] = None,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
    executor_cmd: ExecutorCmdOpt = None,
    executor: ExecutorOpt = None,
    anthropic: AnthropicOpt = False,
    review: ReviewOpt = None,
    review_cmd: ReviewCmdOpt = None,
    review_anthropic: ReviewAnthropicOpt = False,
    allow_policy_change: Annotated[
        bool,
        typer.Option(
            "--allow-policy-change",
            help="Explicitly resume with different executor, reviewer, or model settings.",
        ),
    ] = False,
) -> None:
    repo_root = repo.resolve()
    policy_store = WorkflowStore(db or default_db(repo_root))
    policy_store.initialize()
    policy_store.get_run(run_id)
    stored_mode = PhaseGitMode(policy_store.get_phase_git_mode(run_id))
    selected_mode = stored_mode if phase_git is None else phase_git
    policy_store.ensure_phase_git_mode(run_id, selected_mode.value)
    runner = make_runner(
        repo_root,
        db,
        select_adapter(executor, executor_cmd, anthropic),
        select_review_adapter(review, review_cmd, review_anthropic),
        emit_phase_deliverables,
        phase_git_callback(repo_root, selected_mode, run_id),
    )
    result = runner.resume(run_id, allow_policy_change=allow_policy_change)
    emit_result(result)


def cancel_run(
    run_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    make_runner(repo, db).cancel(run_id)
    console.print(f"{run_id}: cancelled")

def retry_step(
    run_id: Annotated[str, typer.Argument()],
    step_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    make_runner(repo, db).retry(run_id, step_id)
    console.print(f"{run_id}/{step_id}: retry queued")


def register(app: typer.Typer, run_id_factory: Callable[[], str]) -> None:
    generated_run_id.callback = run_id_factory
    app.command("run")(run_workflow)
    app.command("ingest")(ingest_inbox)
    app.command("resume")(resume_run)


def register_retry(app: typer.Typer) -> None:
    app.command("retry")(retry_step)
    app.command("cancel")(cancel_run)
