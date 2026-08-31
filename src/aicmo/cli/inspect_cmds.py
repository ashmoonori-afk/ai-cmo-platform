from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from ._shared import console, make_runner


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


def register(app: typer.Typer) -> None:
    app.command("status")(status_run)
    app.command("list-runs")(list_runs)
