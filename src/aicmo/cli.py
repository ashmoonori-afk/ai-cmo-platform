from __future__ import annotations

import shlex
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

from aicmo.adapters import CommandAdapter, StepAdapter
from aicmo.errors import AicmoError
from aicmo.evaluate import evaluate_asset, render_report
from aicmo.mockup import brief_from_answers, render_landing_mockup, render_png
from aicmo.models import RunResult, RunStatus
from aicmo.onboarding import OnboardingResult, load_answers, scaffold_client
from aicmo.reporter import flush_kb_updates
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from aicmo.web import run_server

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
console = Console()

EXIT_FAILED = 1
EXIT_WAITING_APPROVAL = 75  # EX_TEMPFAIL: paused for approval; resume after the gate is approved


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


def default_db(repo: Path) -> Path:
    return repo / ".aicmo" / "runs.sqlite3"


def make_runner(repo: Path, db: Path | None, adapter: StepAdapter | None = None) -> WorkflowRunner:
    repo_root = repo.resolve()
    store = WorkflowStore(db or default_db(repo_root))
    if adapter is None:
        return WorkflowRunner(repo_root=repo_root, store=store)
    return WorkflowRunner(repo_root=repo_root, store=store, adapter=adapter)


def adapter_from_cmd(executor_cmd: str | None) -> StepAdapter | None:
    if not executor_cmd:
        return None
    return CommandAdapter(command=tuple(shlex.split(executor_cmd)))


def generated_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    return f"run_{timestamp}_{uuid4().hex}"


@app.command("run")
def run_workflow(
    workflow_id: Annotated[str, typer.Argument(help="Workflow id under workflows/*.workflow.yaml")],
    client: Annotated[str | None, typer.Option("--client")] = None,
    topic: Annotated[str | None, typer.Option("--topic")] = None,
    target_keyword: Annotated[str | None, typer.Option("--target-keyword")] = None,
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
    executor_cmd: Annotated[
        str | None,
        typer.Option(
            "--executor-cmd",
            help="Live executor; the prompt is piped on stdin (e.g. 'claude -p'). "
            "Omit to use the deterministic local adapter.",
        ),
    ] = None,
) -> None:
    inputs = compact_inputs(
        {
            "client": client,
            "topic": topic,
            "target_keyword": target_keyword,
        },
    )
    runner = make_runner(repo, db, adapter_from_cmd(executor_cmd))
    result = runner.run(workflow_id=workflow_id, run_id=run_id or generated_run_id(), inputs=inputs)
    emit_result(result)


@app.command("resume")
def resume_run(
    run_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
    executor_cmd: Annotated[
        str | None,
        typer.Option("--executor-cmd", help="Live executor command (prompt piped on stdin)."),
    ] = None,
) -> None:
    result = make_runner(repo, db, adapter_from_cmd(executor_cmd)).resume(run_id)
    emit_result(result)


@app.command("status")
def status_run(
    run_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    runner = make_runner(repo, db)
    runner.store.initialize()
    run = runner.store.get_run(run_id)
    console.print(f"{run['run_id']}: {run['status']} ({run['workflow_id']})")
    table = Table("order", "step", "type", "status", "attempt")
    for step in runner.store.list_steps(run_id):
        table.add_row(
            str(step["step_order"]),
            str(step["step_id"]),
            str(step["step_type"]),
            str(step["status"]),
            str(step["attempt"]),
        )
    console.print(table)


@app.command("list-runs")
def list_runs(
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    runner = make_runner(repo, db)
    runner.store.initialize()
    table = Table("run_id", "workflow", "status", "updated")
    for run in runner.store.list_runs():
        table.add_row(
            str(run["run_id"]),
            str(run["workflow_id"]),
            str(run["status"]),
            str(run["updated_at"]),
        )
    console.print(table)


@app.command("approve")
def approve_gate(
    run_id: Annotated[str, typer.Argument()],
    step_id: Annotated[str, typer.Argument()],
    reviewer: Annotated[str, typer.Option("--reviewer")] = "owner",
    notes: Annotated[str, typer.Option("--notes")] = "Approved",
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    make_runner(repo, db).approve(run_id, step_id, reviewer, notes)
    console.print(f"{run_id}/{step_id}: approved")


@app.command("reject")
def reject_gate(
    run_id: Annotated[str, typer.Argument()],
    step_id: Annotated[str, typer.Argument()],
    reviewer: Annotated[str, typer.Option("--reviewer")] = "owner",
    notes: Annotated[str, typer.Option("--notes")] = "Rejected",
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    make_runner(repo, db).reject(run_id, step_id, reviewer, notes)
    console.print(f"{run_id}/{step_id}: rejected")


@app.command("retry")
def retry_step(
    run_id: Annotated[str, typer.Argument()],
    step_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    make_runner(repo, db).retry(run_id, step_id)
    console.print(f"{run_id}/{step_id}: retry queued")


def emit_onboarding(result: OnboardingResult) -> None:
    console.print(f"onboarded {result.client}: {len(result.created)} files created")
    for path in result.created:
        console.print(f"  {path}")


@app.command("onboard")
def onboard_client(
    client: Annotated[str, typer.Option("--client", help="Client slug (folder under clients/)")],
    answers: Annotated[Path, typer.Option("--from", help="Path to the 7-answer JSON file")],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    force: Annotated[bool, typer.Option("--force")] = False,
    date: Annotated[str | None, typer.Option("--date")] = None,
) -> None:
    loaded = load_answers(answers)
    loaded = replace(loaded, client=client, onboarding_date=date or loaded.onboarding_date)
    result = scaffold_client(repo.resolve(), loaded, force=force)
    emit_onboarding(result)


@app.command("serve")
def serve_cmd(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
) -> None:
    console.print(f"AI CMO web: http://{host}:{port}  (Ctrl-C to stop)")
    run_server(host, port)


@app.command("mockup")
def mockup_cmd(
    source: Annotated[Path, typer.Option("--from", help="Onboarding answers JSON")],
    out: Annotated[Path, typer.Option("--out", help="HTML mockup output path")],
    png: Annotated[Path | None, typer.Option("--png", help="PNG via Playwright")] = None,
) -> None:
    brief = brief_from_answers(load_answers(source))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_landing_mockup(brief), encoding="utf-8")
    console.print(f"mockup: {out}")
    if png is not None:
        console.print(f"png: {render_png(out, png)}")


@app.command("evaluate")
def evaluate_cmd(
    source: Annotated[Path, typer.Option("--from", help="Asset markdown to score")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    out: Annotated[Path | None, typer.Option("--out", help="Write scorecard markdown")] = None,
) -> None:
    result = evaluate_asset(source.read_text(encoding="utf-8"))
    console.print(f"score: {result.total}/100 — {result.band}")
    for dim in result.dimensions:
        console.print(f"  {dim.name}: {dim.score}/{dim.max}")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_report(result, title or source.stem), encoding="utf-8")
        console.print(f"scorecard: {out}")


@app.command("kb-flush")
def kb_flush(
    client: Annotated[str | None, typer.Option("--client")] = None,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    repo_root = repo.resolve()
    store = WorkflowStore(db or default_db(repo_root))
    count = flush_kb_updates(repo_root, store, client)
    console.print(f"kb-flush: {count} queued update(s) appended to knowledge-base")


def compact_inputs(values: dict[str, str | None]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def main() -> None:
    try:
        app()
    except AicmoError as exc:
        console.print(f"error: {exc}")
        raise SystemExit(1) from None
    except Exception as exc:  # noqa: BLE001 — top-level CLI guard: surface a clean message
        console.print(f"unexpected error: {exc}")
        raise SystemExit(1) from None
