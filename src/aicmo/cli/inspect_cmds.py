import json
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.table import Table

from aicmo.quota import run_quota_status
from aicmo.store_inspection import inspect_store

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
    product = run_quota_status(runner.store, run_id)
    if product is not None:
        console.print(
            f"Product: {product['state']} / {product['period']}; "
            "provider cost unavailable; product credit is not a cash refund.",
            markup=False,
        )


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


def usage_run(
    run_id: Annotated[str, typer.Argument()],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    """Show observed logical adapter calls; unavailable is not zero or a billing total."""
    store = make_runner(repo, db).store
    store.initialize()
    store.get_run(run_id)
    with store.connect() as connection:
        rows = connection.execute(
            "select step_id, payload_json from events where run_id = ? "
            "and event_type in ('agent.call_started', 'agent.call_finished') order by event_id",
            (run_id,),
        ).fetchall()
    calls: dict[str, dict[str, str]] = {}
    for row in rows:
        payload = cast("dict[str, str]", json.loads(row["payload_json"]))
        call_id = payload.get("call_id", "")
        calls[call_id] = {**calls.get(call_id, {}), **payload, "step": str(row["step_id"])}
    if not calls:
        console.print("usage unavailable: no call observations recorded for this run")
        return
    table = Table(
        "step / attempt",
        "role",
        "provider / model",
        "in / out",
        "cache write / read",
        "stop / result",
        "cost",
    )
    for data in calls.values():
        model = data.get("response_model", "unavailable")
        if model == "unavailable":
            model = data.get("requested_model", "unavailable")
        table.add_row(
            f"{data['step']} / {data.get('attempt', 'unavailable')}",
            data.get("role", ""),
            f"{data.get('provider', 'unavailable')} / {model}",
            f"{data.get('input_tokens', 'unavailable')} / "
            f"{data.get('output_tokens', 'unavailable')}",
            f"{data.get('cache_creation_input_tokens', 'unavailable')} / "
            f"{data.get('cache_read_input_tokens', 'unavailable')}",
            f"{data.get('stop_reason', 'unavailable')} / {data.get('result', 'unfinished')}",
            data.get("cost_status", "unavailable"),
        )
    console.print(table)
    console.print(
        "Logical calls only; provider-internal retries and invoice totals are unavailable."
    )


def inspect_store_command(
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
) -> None:
    """Read aggregate DB state as JSON; exit 0 means readable, not a live worker."""
    result = inspect_store(repo)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if result["inspection_status"] != "available":
        raise typer.Exit(1)


def register(app: typer.Typer) -> None:
    app.command("status")(status_run)
    app.command("list-runs")(list_runs)
    app.command("usage")(usage_run)
    app.command("inspect-store")(inspect_store_command)
