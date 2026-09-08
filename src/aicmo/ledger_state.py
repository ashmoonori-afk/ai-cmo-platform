from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Self

from aicmo.errors import StepTransitionError
from aicmo.models import ApprovalDecision, StepStatus
from aicmo.redaction import redact, safe_kb_text
from aicmo.step_state import WorkflowStepStore


class WorkflowLedgerStore(WorkflowStepStore):
    def complete_step_success(
        self: Self,
        run_id: str,
        step_id: str,
        outputs: list[str],
        output_hashes: Mapping[str, str],
        consumed_ref_digest: str,
        owner: str | None = None,
    ) -> bool:
        """Commit the success ledger for artifacts already written to disk."""
        if set(outputs) != set(output_hashes):
            raise StepTransitionError(
                run_id,
                step_id,
                "successful outputs require exactly one hash each",
            )
        with self.connect() as connection:
            done = self._finalize_step(
                connection,
                run_id,
                step_id,
                owner,
                "status = ?, outputs_json = ?, completed_at = current_timestamp, error_json = null",
                (StepStatus.SUCCESS.value, json.dumps(outputs, ensure_ascii=False)),
            )
            if not done:
                return False
            self._record_artifacts(connection, run_id, step_id, outputs, "markdown")
            for path in outputs:
                connection.execute(
                    """
                    insert into step_output_hashes (run_id, step_id, path, sha256)
                    values (?, ?, ?, ?)
                    on conflict(run_id, step_id, path) do update set sha256 = excluded.sha256
                    """,
                    (run_id, step_id, path, output_hashes[path]),
                )
            connection.execute(
                """
                insert into step_consumed_ref_digests (run_id, step_id, sha256)
                values (?, ?, ?)
                on conflict(run_id, step_id) do update set sha256 = excluded.sha256
                """,
                (run_id, step_id, consumed_ref_digest),
            )
            connection.execute(
                """
                insert into events (run_id, step_id, event_type, message, payload_json)
                values (?, ?, 'step.success', ?, '{}')
                """,
                (run_id, step_id, f"Completed {step_id}"),
            )
        return True

    def approve(
        self: Self,
        run_id: str,
        step_id: str,
        decision: ApprovalDecision,
        reviewer: str,
        notes: str,
        photo_manifest_sha256: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute("begin immediate")
            self._require_waiting_gate(connection, run_id, step_id)
            self._require_no_existing_approval(connection, run_id, step_id)
            if photo_manifest_sha256 is not None:
                row = connection.execute(
                    "select sha256 from step_output_hashes where run_id=? and step_id='photos' "
                    "and path=?",
                    (run_id, f"artifacts/{run_id}/photos.json"),
                ).fetchone()
                if row is None or row["sha256"] != photo_manifest_sha256:
                    raise StepTransitionError(
                        run_id, step_id, "photo version changed during approval"
                    )
            connection.execute(
                """
                insert into approvals
                (run_id, step_id, decision, reviewer, notes, photo_manifest_sha256)
                values (?, ?, ?, ?, ?, ?)
                """,
                (run_id, step_id, decision.value, reviewer, notes, photo_manifest_sha256),
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
        payload: Mapping[str, str | list[str]] | None = None,
    ) -> None:
        message = redact(message)
        raw_payload: Mapping[str, str | list[str]] = {} if payload is None else payload
        event_payload: Mapping[str, str | list[str]] = {
            key: [redact(item) for item in value] if isinstance(value, list) else redact(value)
            for key, value in raw_payload.items()
        }
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

    def record_consumed_ref_digest(self: Self, run_id: str, step_id: str, digest: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                insert into step_consumed_ref_digests (run_id, step_id, sha256)
                values (?, ?, ?)
                on conflict(run_id, step_id) do update set sha256 = excluded.sha256
                """,
                (run_id, step_id, digest),
            )

    def get_consumed_ref_digest(self: Self, run_id: str, step_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "select sha256 from step_consumed_ref_digests where run_id = ? and step_id = ?",
                (run_id, step_id),
            ).fetchone()
        return None if row is None else str(row["sha256"])

    def record_kb_update(
        self: Self,
        run_id: str,
        step_id: str,
        client: str,
        path: str,
        content: str,
    ) -> None:
        content = safe_kb_text(content)
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
