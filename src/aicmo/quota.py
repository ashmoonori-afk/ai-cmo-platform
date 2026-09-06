from __future__ import annotations

import json
import sqlite3
from datetime import date

from aicmo.db import StoreDb
from aicmo.errors import WorkflowExecutionError
from aicmo.paths import parse_safe_id
from aicmo.redaction import safe_kb_text
from aicmo.source_input import source_checked_date

_MAX_ALLOWANCE = 1_000_000


class QuotaError(WorkflowExecutionError):
    def __init__(self, reason: str) -> None:
        super().__init__("quota", reason)


def current_period() -> str:
    return source_checked_date().strftime("%Y-%m")


def parse_period(value: str) -> str:
    try:
        parsed = date.fromisoformat(f"{value}-01")
        if parsed.strftime("%Y-%m") != value:
            raise ValueError  # noqa: TRY301 — fixed safe error below
    except ValueError:
        reason = "period must be YYYY-MM"
        raise QuotaError(reason) from None
    return value


def _used(connection: sqlite3.Connection, client: str, period: str) -> int:
    return int(
        connection.execute(
            "select count(*) from product_usage where client=? and period=? "
            "and state in ('reserved','consumed')",
            (client, period),
        ).fetchone()[0]
    )


def configure_quota(store: StoreDb, client: str, period: str, packs: int, drafts: int) -> None:
    client, period = parse_safe_id("client", client), parse_period(period)
    if any(type(value) is not int or not 0 <= value <= _MAX_ALLOWANCE for value in (packs, drafts)):
        reason = "limits must be integers from 0 to 1000000"
        raise QuotaError(reason)
    store.initialize()
    with store.connect() as connection:
        connection.execute("begin immediate")
        row = connection.execute(
            "select draft_used from product_quotas where client=? and period=?", (client, period)
        ).fetchone()
        if packs < _used(connection, client, period) or (row and drafts < row[0]):
            reason = "limits cannot be below reserved/consumed packs or used attempts"
            raise QuotaError(reason)
        connection.execute(
            "insert into product_quotas(client,period,pack_limit,draft_limit) values(?,?,?,?) "
            "on conflict(client,period) do update set "
            "pack_limit=excluded.pack_limit,draft_limit=excluded.draft_limit",
            (client, period, packs, drafts),
        )


def claim_quota(  # noqa: C901 — ordered checks before any reservation mutation
    connection: sqlite3.Connection, run_id: str, step_id: str
) -> None:
    """Called only inside the transaction of a winning step claim, before dispatch."""
    run = connection.execute("select * from runs where run_id=?", (run_id,)).fetchone()
    if run["workflow_id"] != "local-store-pack":
        return
    client = str(json.loads(run["inputs_json"])["client"])
    receipt = connection.execute("select * from product_usage where run_id=?", (run_id,)).fetchone()
    if receipt is not None and receipt["state"] == "unmetered":
        return
    legacy_attempts = connection.execute(
        "select coalesce(sum(attempt),0) from steps where run_id=?", (run_id,)
    ).fetchone()[0]
    if receipt is None and (
        legacy_attempts > 1
        or (
            connection.execute(
                "select 1 from product_quotas where client=? limit 1", (client,)
            ).fetchone()
            is None
        )
    ):
        connection.execute(
            "insert into product_usage(run_id,client,period,state) values(?,?,?,'unmetered')",
            (run_id, client, current_period()),
        )
        _event(connection, run_id, "unmetered", {})
        return
    period = current_period() if receipt is None else str(receipt["period"])
    state = None if receipt is None else str(receipt["state"])
    if state == "credited":
        reason = "credited run cannot regenerate; create a new run"
        raise QuotaError(reason)
    if state == "released" and period != current_period():
        reason = "released reservation expired; create a new run in the current period"
        raise QuotaError(reason)
    quota = connection.execute(
        "select * from product_quotas where client=? and period=?", (client, period)
    ).fetchone()
    if quota is None:
        reason = "no allowance for this period; operator must configure it first"
        raise QuotaError(reason)
    if step_id == "drafts" and quota["draft_used"] >= quota["draft_limit"]:
        reason = "draft attempt limit reached; no generation was dispatched"
        raise QuotaError(reason)
    if state in (None, "released") and _used(connection, client, period) >= quota["pack_limit"]:
        reason = "pack limit reached; cancel unused reservations or adjust allowance"
        raise QuotaError(reason)
    if state in (None, "released"):
        connection.execute(
            "insert into product_usage(run_id,client,period,state) values(?,?,?,'reserved') "
            "on conflict(run_id) do update set state='reserved'",
            (run_id, client, period),
        )
        _event(connection, run_id, "reserved", {"period": period})
    if step_id == "drafts":
        connection.execute(
            "update product_quotas set draft_used=draft_used+1 where client=? and period=?",
            (client, period),
        )
        _event(connection, run_id, "draft_attempt", {"period": period})


def _event(connection: sqlite3.Connection, run_id: str, action: str, data: dict[str, str]) -> None:
    connection.execute(
        "insert into events(run_id,event_type,message,payload_json) values(?,?,?,?)",
        (run_id, f"quota.{action}", f"Product quota {action}", json.dumps(data)),
    )


def settle_quota(connection: sqlite3.Connection, run_id: str, digest: str | None = None) -> None:
    state = "consumed" if digest else "released"
    changed = connection.execute(
        "update product_usage set state=?,delivery_sha256=? where run_id=? and state='reserved'",
        (state, digest, run_id),
    ).rowcount
    if changed:
        _event(connection, run_id, state, {} if digest is None else {"delivery_sha256": digest})


def credit_quota(store: StoreDb, run_id: str, reason: str) -> bool:
    run_id, reason = parse_safe_id("run_id", run_id), safe_kb_text(reason)
    store.initialize()
    with store.connect() as connection:
        connection.execute("begin immediate")
        row = connection.execute(
            "select product_usage.state,runs.status from product_usage join runs using(run_id) "
            "where run_id=?",
            (run_id,),
        ).fetchone()
        if row is not None and row["state"] == "credited":
            return False
        if row is None or row["state"] != "consumed" or row["status"] != "success":
            reason = "only a consumed, successful run can receive product credit"
            raise QuotaError(reason)
        connection.execute("update product_usage set state='credited' where run_id=?", (run_id,))
        _event(connection, run_id, "credited", {"reason": reason})
    return True


def quota_status(store: StoreDb, client: str, period: str) -> dict[str, object]:
    client, period = parse_safe_id("client", client), parse_period(period)
    store.initialize()
    with store.connect() as connection:
        connection.execute("begin")
        row = connection.execute(
            "select * from product_quotas where client=? and period=?", (client, period)
        ).fetchone()
        managed = (
            connection.execute(
                "select 1 from product_quotas where client=? limit 1", (client,)
            ).fetchone()
            is not None
        )
        counts = dict(
            connection.execute(
                "select state,count(*) from product_usage where client=? and period=? "
                "group by state",
                (client, period),
            ).fetchall()
        )
    return {
        "client": client,
        "period": period,
        "mode": "managed" if managed else "unmetered_local",
        "pack_limit": None if row is None else row["pack_limit"],
        "draft_limit": None if row is None else row["draft_limit"],
        "draft_used": None if row is None else row["draft_used"],
        "packs": {
            state: counts.get(state, 0)
            for state in ("reserved", "consumed", "released", "credited", "unmetered")
        },
        "provider_cost": "unavailable; product units are not money or a provider invoice",
    }


def run_quota_status(store: StoreDb, run_id: str) -> dict[str, str] | None:
    with store.connect() as connection:
        row = connection.execute("select * from product_usage where run_id=?", (run_id,)).fetchone()
    return None if row is None else dict(row)
