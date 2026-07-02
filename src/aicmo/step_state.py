from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Self

from aicmo.errors import StepTransitionError
from aicmo.models import ApprovalDecision, RunStatus, StepStatus, WorkflowStep
from aicmo.run_state import WorkflowRunStore

_DEFAULT_LEASE_TTL = 300.0


def _stale_threshold(lease_ttl_seconds: float) -> str:
    moment = datetime.now(UTC) - timedelta(seconds=lease_ttl_seconds)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


class WorkflowStepStore(WorkflowRunStore):
    def list_steps(self: Self, run_id: str) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from steps where run_id = ? order by step_order",
                (run_id,),
            ).fetchall()
        return list(rows)

    def get_step_status(self: Self, run_id: str, step_id: str) -> StepStatus:
        with self.connect() as connection:
            row = connection.execute(
                "select status from steps where run_id = ? and step_id = ?",
                (run_id, step_id),
            ).fetchone()
        if row is None:
            return StepStatus.PENDING
        return StepStatus(row["status"])

    def get_step_outputs(self: Self, run_id: str, step_id: str) -> list[str]:
        with self.connect() as connection:
            row = connection.execute(
                "select outputs_json from steps where run_id = ? and step_id = ?",
                (run_id, step_id),
            ).fetchone()
        if row is None:
            return []
        loaded = json.loads(row["outputs_json"])
        return [str(value) for value in loaded]

    def record_output_hashes(self: Self, run_id: str, step_id: str, hashes: dict[str, str]) -> None:
        with self.connect() as connection:
            for path, digest in hashes.items():
                connection.execute(
                    """
                    insert into step_output_hashes (run_id, step_id, path, sha256)
                    values (?, ?, ?, ?)
                    on conflict(run_id, step_id, path) do update set sha256 = excluded.sha256
                    """,
                    (run_id, step_id, path, digest),
                )

    def get_output_hashes(self: Self, run_id: str, step_id: str) -> dict[str, str]:
        with self.connect() as connection:
            rows = connection.execute(
                "select path, sha256 from step_output_hashes where run_id = ? and step_id = ?",
                (run_id, step_id),
            ).fetchall()
        return {str(row["path"]): str(row["sha256"]) for row in rows}

    def mark_step_running(
        self: Self,
        run_id: str,
        step: WorkflowStep,
        owner: str = "runner",
        lease_ttl_seconds: float = _DEFAULT_LEASE_TTL,
    ) -> bool:
        """Compare-and-swap claim. Returns True if this owner won the step.

        Claimable when the step is not RUNNING, OR its lease owner is NULL (a crash
        cleared it), OR its lease is older than the TTL (a crashed runner stopped
        renewing). A RUNNING step with a fresh foreign lease is NOT claimable, so a
        concurrent runner fails predictably instead of double-executing.
        """
        threshold = _stale_threshold(lease_ttl_seconds)
        with self.connect() as connection:
            cursor = connection.execute(
                """
                update steps set
                    status = ?,
                    attempt = attempt + 1,
                    started_at = current_timestamp,
                    completed_at = null,
                    error_json = null,
                    locked_by = ?,
                    locked_at = current_timestamp
                where run_id = ? and step_id = ?
                  and (status != 'running' or locked_by is null or locked_at <= ?)
                """,
                (StepStatus.RUNNING.value, owner, run_id, step.id, threshold),
            )
            claimed = cursor.rowcount == 1
            if claimed:
                self._mark_run(connection, run_id, RunStatus.RUNNING, step.id)
        return claimed

    def renew_lease(self: Self, run_id: str, step_id: str, owner: str) -> None:
        """Heartbeat: refresh a live lease so a long step is not falsely reclaimed."""
        with self.connect() as connection:
            connection.execute(
                """
                update steps set locked_at = current_timestamp
                where run_id = ? and step_id = ? and locked_by = ? and status = 'running'
                """,
                (run_id, step_id, owner),
            )

    def _finalize_step(
        self: Self,
        connection: sqlite3.Connection,
        run_id: str,
        step_id: str,
        owner: str | None,
        set_clause: str,
        params: tuple[object, ...],
    ) -> bool:
        """Apply a terminal-state update and release the lease.

        With an owner, the update only lands while that owner still holds a live
        RUNNING lease — a runner that lost its lease cannot overwrite another
        runner's result. `set_clause` is an internal constant; values stay bound.
        """
        guard = "where run_id = ? and step_id = ?"
        guard_params: tuple[object, ...] = (run_id, step_id)
        if owner is not None:
            guard += " and locked_by = ? and status = 'running'"
            guard_params = (*guard_params, owner)
        cursor = connection.execute(
            f"update steps set {set_clause}, locked_by = null, locked_at = null {guard}",
            (*params, *guard_params),
        )
        return cursor.rowcount == 1

    def mark_step_success(
        self: Self,
        run_id: str,
        step_id: str,
        outputs: list[str],
        owner: str | None = None,
    ) -> bool:
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
        return True

    def mark_step_waiting(
        self: Self,
        run_id: str,
        step_id: str,
        outputs: list[str],
        owner: str | None = None,
    ) -> bool:
        with self.connect() as connection:
            done = self._finalize_step(
                connection,
                run_id,
                step_id,
                owner,
                "status = ?, outputs_json = ?, completed_at = current_timestamp",
                (StepStatus.WAITING_APPROVAL.value, json.dumps(outputs, ensure_ascii=False)),
            )
            if not done:
                return False
            self._record_artifacts(connection, run_id, step_id, outputs, "gate")
            self._mark_run(connection, run_id, RunStatus.WAITING_APPROVAL, step_id)
        return True

    def mark_step_failed(
        self: Self,
        run_id: str,
        step_id: str,
        message: str,
        owner: str | None = None,
    ) -> bool:
        payload = json.dumps({"message": message}, ensure_ascii=False)
        with self.connect() as connection:
            done = self._finalize_step(
                connection,
                run_id,
                step_id,
                owner,
                "status = ?, error_json = ?, completed_at = current_timestamp",
                (StepStatus.FAILED.value, payload),
            )
            if not done:
                return False
            self._mark_run(connection, run_id, RunStatus.FAILED, step_id, step_id)
        return True

    def mark_run_success(self: Self, run_id: str) -> None:
        with self.connect() as connection:
            self._mark_run(connection, run_id, RunStatus.SUCCESS, None, None, completed=True)

    def retry_step(self: Self, run_id: str, step_id: str) -> None:
        with self.connect() as connection:
            self._require_retryable_step(connection, run_id, step_id)
            connection.execute(
                """
                update steps set
                    status = ?,
                    error_json = null,
                    completed_at = null,
                    locked_by = null,
                    locked_at = null
                where run_id = ? and step_id = ?
                """,
                (StepStatus.PENDING.value, run_id, step_id),
            )
            self._mark_run(connection, run_id, RunStatus.RUNNING, step_id)

    def reopen_step(self: Self, run_id: str, step_id: str) -> None:
        """Reset a previously SUCCESS step to PENDING so resume can regenerate lost outputs."""
        with self.connect() as connection:
            row = connection.execute(
                "select status from steps where run_id = ? and step_id = ?",
                (run_id, step_id),
            ).fetchone()
            if row is None:
                raise StepTransitionError(run_id, step_id, "step does not exist")
            if row["status"] != StepStatus.SUCCESS.value:
                raise StepTransitionError(run_id, step_id, "only successful steps can be reopened")
            connection.execute(
                """
                update steps set
                    status = ?,
                    error_json = null,
                    completed_at = null,
                    locked_by = null,
                    locked_at = null
                where run_id = ? and step_id = ?
                """,
                (StepStatus.PENDING.value, run_id, step_id),
            )
            self._mark_run(connection, run_id, RunStatus.RUNNING, step_id)

    def _record_artifacts(
        self: Self,
        connection: sqlite3.Connection,
        run_id: str,
        step_id: str,
        outputs: list[str],
        kind: str,
    ) -> None:
        for output in outputs:
            connection.execute(
                """
                insert into artifacts (run_id, step_id, path, kind)
                values (?, ?, ?, ?)
                on conflict(run_id, step_id, path) do nothing
                """,
                (run_id, step_id, output, kind),
            )

    def _require_retryable_step(
        self: Self,
        connection: sqlite3.Connection,
        run_id: str,
        step_id: str,
    ) -> None:
        row = connection.execute(
            "select status, step_type from steps where run_id = ? and step_id = ?",
            (run_id, step_id),
        ).fetchone()
        if row is None:
            raise StepTransitionError(run_id, step_id, "step does not exist")
        if row["status"] != StepStatus.FAILED.value:
            raise StepTransitionError(run_id, step_id, "step is not failed")
        if row["step_type"] != "gate":
            return
        approval = connection.execute(
            "select decision from approvals where run_id = ? and step_id = ?",
            (run_id, step_id),
        ).fetchone()
        if approval is not None and approval["decision"] == ApprovalDecision.REJECTED.value:
            raise StepTransitionError(
                run_id,
                step_id,
                "rejected gate decision is terminal; start a new run",
            )
