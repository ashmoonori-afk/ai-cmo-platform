from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from aicmo.db import StoreDb
from aicmo.quota import configure_quota, credit_quota, current_period, quota_status

from ._shared import console, make_runner


def show_quota(
    client: Annotated[str, typer.Argument()],
    period: Annotated[str | None, typer.Option("--period", help="KST YYYY-MM")] = None,
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    """Show local product units, separately from provider usage and money."""
    data = quota_status(make_runner(repo, db).store, client, period or current_period())
    console.print(json.dumps(data, ensure_ascii=False, indent=2), markup=False, soft_wrap=True)


def quota_notice(store: StoreDb, client: str) -> None:
    data = quota_status(store, client, current_period())
    console.print(
        f"Product allowance ({data['period']}): {data['mode']}; "
        f"packs={data['pack_limit']}, draft attempts={data['draft_used']}/{data['draft_limit']}. "
        "Expected provider cost: unavailable. Use 'aicmo quota' for reservations/consumption.",
        markup=False,
    )


def set_quota(
    client: Annotated[str, typer.Argument()],
    period: Annotated[str, typer.Option("--period", help="KST YYYY-MM")],
    packs: Annotated[int, typer.Option("--packs")],
    drafts: Annotated[int, typer.Option("--draft-attempts")],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    """Operator: set allowance; an existing client's missing months block new work."""
    configure_quota(make_runner(repo, db).store, client, period, packs, drafts)
    show_quota(client, period, repo, db)


def credit_run(
    run_id: Annotated[str, typer.Argument()],
    reason: Annotated[str, typer.Option("--reason")],
    repo: Annotated[Path, typer.Option("--repo")] = Path(),
    db: Annotated[Path | None, typer.Option("--db")] = None,
) -> None:
    """Operator: return one product unit once; this does not refund money."""
    changed = credit_quota(make_runner(repo, db).store, run_id, reason)
    console.print("Product unit credited; no money refunded." if changed else "Already credited.")


def register(app: typer.Typer) -> None:
    app.command("quota")(show_quota)
    app.command("quota-set")(set_quota)
    app.command("quota-credit")(credit_run)
