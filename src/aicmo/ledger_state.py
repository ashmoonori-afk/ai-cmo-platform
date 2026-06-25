from __future__ import annotations

import json
import sqlite3
from typing import Self

from aicmo.errors import StepTransitionError
from aicmo.models import ApprovalDecision, StepStatus
from aicmo.step_state import WorkflowStepStore


class WorkflowLedgerStore(WorkflowStepStore):
    def approve(
        self: Self,
        run_id: str,
        step_id: str,
        decision: ApprovalDecision,
        reviewer: str,
        notes: str,
    ) -> None:
        with self.connect() as connection:
            self._require_waiting_gate(connection, run_id, step_id)
            self._require_no_existing_approval(connection, run_id, step_id)
            connection.execute(
                """
                insert into approvals (run_id, step_id, decision, reviewer, notes)
                values (?, ?, ?, ?, ?)
                """,
                (run_id, step_id, decision.value, reviewer, notes),
            )

    def approval_for(self: Self, run_id: str, step_id: str) -> ApprovalDecision | None:
        with self.connect() as connection:
            row = connection.execute(
                "select decision from approvals where run_id = ? and step_id = ?",
                (run_id, step_id),
            ).fetchone()
        if row is None:
            return None
        return ApprovalDecision(row["decision"])

    def record_event(
        self: Self,
        run_id: str,
        step_id: str | None,
        event_type: str,
        message: str,
        payload: dict[str, str] | None = None,
    ) -> None:
        event_payload = {} if payload is None else payload
        with self.connect() as connection:
            connection.execute(
                """
                insert into events (run_id, step_id, event_type, message, payload_json)
                values (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    step_id,
                    event_type,
                    message,
                    json.dumps(event_payload, ensure_ascii=False),
                ),
            )

    def record_kb_update(
        self: Self,
        run_id: str,
        step_id: str,
        client: str,
        path: str,
        content: str,
    ) -> None:
        with self.connect() as connection:
            # Idempotent: re-running a kb.update step (e.g. resume after a deleted artifact)
            # must not enqueue a duplicate. Content is regenerated deterministically per step,
            # so keeping the existing row (do nothing) loses nothing.
            connection.execute(
                """
                insert into kb_updates (run_id, step_id, client, path, status, content)
                values (?, ?, ?, ?, ?, ?)
                on conflict(run_id, step_id, path) do nothing
                """,
                (run_id, step_id, client, path, "queued", content),
            )

    def pending_kb_updates(self: Self, client: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as connection:
            if client is None:
                rows = connection.execute(
                    "select * from kb_updates where status = 'queued' order by kb_update_id",
                ).fetchall()
            else:
                rows = connection.execute(
                    "select * from kb_updates where status = 'queued' and client = ? "
                    "order by kb_update_id",
                    (client,),
                ).fetchall()
        return list(rows)

    def mark_kb_update_consumed(self: Self, kb_update_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "update kb_updates set status = 'consumed' where kb_update_id = ?",
                (kb_update_id,),
            )

    def _require_waiting_gate(
        self: Self,
        connection: sqlite3.Connection,
        run_id: str,
        step_id: str,
    ) -> None:
        row = connection.execute(
            "select step_type, status from steps where run_id = ? and step_id = ?",
            (run_id, step_id),
        ).fetchone()
        if row is None:
            raise StepTransitionError(run_id, step_id, "step does not exist")
        if row["step_type"] != "gate":
            raise StepTransitionError(run_id, step_id, "step is not an approval gate")
        if row["status"] != StepStatus.WAITING_APPROVAL.value:
            raise StepTransitionError(run_id, step_id, "gate is not waiting for approval")

    def _require_no_existing_approval(
        self: Self,
        connection: sqlite3.Connection,
        run_id: str,
        step_id: str,
    ) -> None:
        row = connection.execute(
            "select decision from approvals where run_id = ? and step_id = ?",
            (run_id, step_id),
        ).fetchone()
        if row is not None:
            raise StepTransitionError(run_id, step_id, "gate decision already recorded")
