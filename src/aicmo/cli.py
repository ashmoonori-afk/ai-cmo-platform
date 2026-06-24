from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

from aicmo.errors import AicmoError
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore

app = typer.Typer(no_args_is_help=True)
console = Console()


def default_db(repo: Path) -> Path:
    return repo / ".aicmo" / "runs.sqlite3"


def make_runner(repo: Path, db: Path | None) -> WorkflowRunner:
    repo_root = repo.resolve()
    return WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db or default_db(repo_root)))


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
) -> None:
    inputs = compact_inputs(
        {
            "client": client,
            "topic": topic,
            "target_keyword": target_keyword,
        },
    )
    runner = make_runner(repo, db)
    result = runner.run(workflow_id=workflow_id, run_id=run_id or generated_run_id(), inputs=inputs)
    console.print(f"{result.run_id}: {result.status}")
    if result.failed_step_id is not None:
        console.print(f"failed_step: {result.failed_step_id}")


@app.command("resume")
def resume_run(
    run_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    result = make_runner(repo, db).resume(run_id)
    console.print(f"{result.run_id}: {result.status}")
    if result.failed_step_id is not None:
        console.print(f"failed_step: {result.failed_step_id}")


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


def compact_inputs(values: dict[str, str | None]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value is not None}


def main() -> None:
    try:
        app()
    except AicmoError as exc:
        console.print(f"error: {exc}")
        raise SystemExit(1) from None
