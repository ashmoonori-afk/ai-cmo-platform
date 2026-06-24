from __future__ import annotations

import json
import sqlite3
from typing import Self

from aicmo.db import StoreDb
from aicmo.errors import RunConflictError, RunNotFoundError
from aicmo.models import RunStatus, StepStatus, WorkflowSpec


class WorkflowRunStore(StoreDb):
    def register_workflow(self: Self, spec: WorkflowSpec) -> None:
        spec_path = "" if spec.source_path is None else str(spec.source_path)
        with self.connect() as connection:
            connection.execute(
                """
                insert into workflows (workflow_id, name, spec_path)
                values (?, ?, ?)
                on conflict(workflow_id) do update set
                    name = excluded.name,
                    spec_path = excluded.spec_path,
                    updated_at = current_timestamp
                """,
                (spec.id, spec.name, spec_path),
            )

    def ensure_run(self: Self, spec: WorkflowSpec, run_id: str, inputs: dict[str, str]) -> None:
        self.register_workflow(spec)
        inputs_json = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
        with self.connect() as connection:
            connection.execute(
                """
                insert into runs (run_id, workflow_id, status, inputs_json)
                values (?, ?, ?, ?)
                on conflict(run_id) do nothing
                """,
                (run_id, spec.id, RunStatus.RUNNING.value, inputs_json),
            )
            row = connection.execute(
                "select workflow_id, inputs_json from runs where run_id = ?",
                (run_id,),
            ).fetchone()
            if row["workflow_id"] != spec.id:
                raise RunConflictError(run_id, "existing run uses a different workflow")
            if row["inputs_json"] != inputs_json:
                raise RunConflictError(run_id, "existing run uses different inputs")
            for order, step in enumerate(spec.steps):
                connection.execute(
                    """
                    insert into steps (run_id, step_id, step_order, step_type, status)
                    values (?, ?, ?, ?, ?)
                    on conflict(run_id, step_id) do nothing
                    """,
                    (run_id, step.id, order, step.type.value, StepStatus.PENDING.value),
                )

    def get_run(self: Self, run_id: str) -> sqlite3.Row:
        with self.connect() as connection:
            row = connection.execute("select * from runs where run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return row

    def list_runs(self: Self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from runs order by created_at desc, run_id desc",
            ).fetchall()
        return list(rows)

    def get_inputs(self: Self, run_id: str) -> dict[str, str]:
        row = self.get_run(run_id)
        loaded = json.loads(row["inputs_json"])
        return {str(key): str(value) for key, value in loaded.items()}

    def _mark_run(
        self: Self,
        connection: sqlite3.Connection,
        run_id: str,
        status: RunStatus,
        current_step_id: str | None,
        failed_step_id: str | None = None,
        completed: bool = False,
    ) -> None:
        if completed:
            connection.execute(
                """
                update runs set
                    status = ?,
                    current_step_id = ?,
                    failed_step_id = ?,
                    updated_at = current_timestamp,
                    completed_at = current_timestamp
                where run_id = ?
                """,
                (status.value, current_step_id, failed_step_id, run_id),
            )
            return
        connection.execute(
            """
            update runs set
                status = ?,
                current_step_id = ?,
                failed_step_id = ?,
                updated_at = current_timestamp
            where run_id = ?
            """,
            (status.value, current_step_id, failed_step_id, run_id),
        )
