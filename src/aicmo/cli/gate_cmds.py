from pathlib import Path
from typing import Annotated

import typer

from ._shared import console, make_runner


def approve_gate(
    run_id: Annotated[str, typer.Argument()],
    step_id: Annotated[str, typer.Argument()],
    reviewer: Annotated[str, typer.Option("--reviewer")] = "owner",
    notes: Annotated[str, typer.Option("--notes")] = "Approved",
    accept_edits: Annotated[
        bool,
        typer.Option(
            "--accept-edits",
            help="Keep human edits made to generated artifacts while the gate was "
            "waiting: re-hash them so resume does not regenerate over the edits. "
            "Originals stay under artifacts/<run_id>/_pre_edit/ for reflection diffs.",
        ),
    ] = False,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    changed = make_runner(repo, db).approve(
        run_id,
        step_id,
        reviewer,
        notes,
        accept_edits=accept_edits,
    )
    console.print(f"{run_id}/{step_id}: approved")
    if accept_edits:
        if changed:
            console.print(f"edits accepted ({len(changed)} file(s)):")
            for path in changed:
                console.print(f"  {path}")
        else:
            console.print("edits accepted: no artifact changes detected")

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


def register(app: typer.Typer) -> None:
    app.command("approve")(approve_gate)
    app.command("reject")(reject_gate)
