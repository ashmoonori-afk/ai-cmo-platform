from __future__ import annotations

import json
import sqlite3
from typing import Self

from aicmo.errors import StepTransitionError
from aicmo.models import ApprovalDecision, RunStatus, StepStatus, WorkflowStep
from aicmo.run_state import WorkflowRunStore


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

    def mark_step_running(self: Self, run_id: str, step: WorkflowStep) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "select attempt from steps where run_id = ? and step_id = ?",
                (run_id, step.id),
            ).fetchone()
            attempt = 1 if row is None else int(row["attempt"]) + 1
            connection.execute(
                """
                update steps set
                    status = ?,
                    attempt = ?,
                    started_at = current_timestamp,
                    completed_at = null,
                    error_json = null
                where run_id = ? and step_id = ?
                """,
                (StepStatus.RUNNING.value, attempt, run_id, step.id),
            )
            self._mark_run(connection, run_id, RunStatus.RUNNING, step.id)
        return attempt

    def mark_step_success(self: Self, run_id: str, step_id: str, outputs: list[str]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                update steps set
                    status = ?,
                    outputs_json = ?,
                    completed_at = current_timestamp,
                    error_json = null
                where run_id = ? and step_id = ?
                """,
                (
                    StepStatus.SUCCESS.value,
                    json.dumps(outputs, ensure_ascii=False),
                    run_id,
                    step_id,
                ),
            )
            self._record_artifacts(connection, run_id, step_id, outputs, "markdown")

    def mark_step_waiting(self: Self, run_id: str, step_id: str, outputs: list[str]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                update steps set
                    status = ?,
                    outputs_json = ?,
                    completed_at = current_timestamp
                where run_id = ? and step_id = ?
                """,
                (
                    StepStatus.WAITING_APPROVAL.value,
                    json.dumps(outputs, ensure_ascii=False),
                    run_id,
                    step_id,
                ),
            )
            self._record_artifacts(connection, run_id, step_id, outputs, "gate")
            self._mark_run(connection, run_id, RunStatus.WAITING_APPROVAL, step_id)

    def mark_step_failed(self: Self, run_id: str, step_id: str, message: str) -> None:
        payload = json.dumps({"message": message}, ensure_ascii=False)
        with self.connect() as connection:
            connection.execute(
                """
                update steps set
                    status = ?,
                    error_json = ?,
                    completed_at = current_timestamp
                where run_id = ? and step_id = ?
                """,
                (StepStatus.FAILED.value, payload, run_id, step_id),
            )
            self._mark_run(connection, run_id, RunStatus.FAILED, step_id, step_id)

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
                    completed_at = null
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
