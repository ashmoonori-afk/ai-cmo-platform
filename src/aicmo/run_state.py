from __future__ import annotations

import json
import sqlite3
from typing import Self

from pydantic import TypeAdapter, ValidationError

from aicmo.db import StoreDb
from aicmo.errors import RunConflictError, RunNotFoundError
from aicmo.models import RunStatus, StepStatus, WorkflowSpec
from aicmo.spec import RUN_SPEC_REVISION, run_spec_digest

_RUN_INPUTS_ADAPTER = TypeAdapter(dict[str, str])


class WorkflowRunStore(StoreDb):
    def _register_workflow(
        self: Self,
        connection: sqlite3.Connection,
        spec: WorkflowSpec,
    ) -> None:
        spec_path = "" if spec.source_path is None else str(spec.source_path)
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

    def register_workflow(self: Self, spec: WorkflowSpec) -> None:
        with self.connect() as connection:
            self._register_workflow(connection, spec)

    def ensure_run(self: Self, spec: WorkflowSpec, run_id: str, inputs: dict[str, str]) -> None:
        spec_digest = run_spec_digest(spec, inputs)
        inputs_json = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
        with self.connect() as connection:
            connection.execute("begin immediate")
            row = connection.execute(
                "select workflow_id, spec_digest, spec_revision from runs where run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                self._register_workflow(connection, spec)
                connection.execute(
                    """
                    insert into runs (
                        run_id, workflow_id, status, inputs_json, spec_digest, spec_revision
                    )
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        spec.id,
                        RunStatus.RUNNING.value,
                        inputs_json,
                        spec_digest,
                        RUN_SPEC_REVISION,
                    ),
                )
            elif row["workflow_id"] != spec.id:
                raise RunConflictError(run_id, "workflow changed; start a new run")
            elif row["spec_digest"] is None or row["spec_revision"] is None:
                raise RunConflictError(
                    run_id,
                    "legacy run has no specification identity; start a new run",
                )
            elif row["spec_revision"] != RUN_SPEC_REVISION or row["spec_digest"] != spec_digest:
                raise RunConflictError(
                    run_id,
                    "workflow, role/prompt, or inputs changed; start a new run",
                )
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

    def ensure_phase_git_mode(self: Self, run_id: str, mode: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                insert into run_policies (run_id, phase_git_mode)
                values (?, ?)
                on conflict(run_id) do nothing
                """,
                (run_id, mode),
            )
            row = connection.execute(
                "select phase_git_mode from run_policies where run_id = ?",
                (run_id,),
            ).fetchone()
        if row["phase_git_mode"] != mode:
            raise RunConflictError(run_id, "existing run uses a different phase-git policy")

    def ensure_execution_policy(
        self: Self,
        run_id: str,
        policy_json: str,
        *,
        allow_change: bool = False,
    ) -> bool:
        """Persist the executor/reviewer/model policy. Returns whether it changed."""
        with self.connect() as connection:
            connection.execute("begin immediate")
            row = connection.execute(
                "select execution_policy_json from run_policies where run_id = ?",
                (run_id,),
            ).fetchone()
            execution_started = (
                connection.execute(
                    "select 1 from steps where run_id = ? and attempt > 0 limit 1",
                    (run_id,),
                ).fetchone()
                is not None
            )
            if row is None:
                connection.execute(
                    "insert into run_policies (run_id, phase_git_mode, execution_policy_json) "
                    "values (?, 'off', ?)",
                    (run_id, policy_json),
                )
                return False
            current = row["execution_policy_json"]
            if current == policy_json:
                return False
            if not allow_change and (current is not None or execution_started):
                raise RunConflictError(
                    run_id,
                    "executor, reviewer, or model policy changed; repeat the original settings "
                    "or explicitly allow a policy change",
                )
            connection.execute(
                "update run_policies set execution_policy_json = ? where run_id = ?",
                (policy_json, run_id),
            )
        return current is not None or execution_started

    def get_execution_policy(self: Self, run_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "select execution_policy_json from run_policies where run_id = ?",
                (run_id,),
            ).fetchone()
        return None if row is None or row["execution_policy_json"] is None else str(row[0])

    def is_run_cancelled(self: Self, run_id: str) -> bool:
        return str(self.get_run(run_id)["status"]) == RunStatus.CANCELLED.value

    def get_phase_git_mode(self: Self, run_id: str) -> str:
        with self.connect() as connection:
            row = connection.execute(
                "select phase_git_mode from run_policies where run_id = ?",
                (run_id,),
            ).fetchone()
        return "off" if row is None else str(row["phase_git_mode"])

    def list_runs(self: Self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from runs order by created_at desc, run_id desc",
            ).fetchall()
        return list(rows)

    def get_inputs(self: Self, run_id: str) -> dict[str, str]:
        row = self.get_run(run_id)
        try:
            return _RUN_INPUTS_ADAPTER.validate_json(row["inputs_json"], strict=True)
        except ValidationError:
            reason = "persisted inputs must be a JSON object with string values; start a new run"
            raise RunConflictError(run_id, reason) from None

    def _mark_run(
        self: Self,
        connection: sqlite3.Connection,
        run_id: str,
        status: RunStatus,
        current_step_id: str | None,
        failed_step_id: str | None = None,
        completed: bool = False,
    ) -> None:
        connection.execute(
            """
            update runs set
                status = ?,
                current_step_id = ?,
                failed_step_id = ?,
                updated_at = current_timestamp,
                completed_at = case when ? then current_timestamp else completed_at end
            where run_id = ?
            """,
            (status.value, current_step_id, failed_step_id, completed, run_id),
        )
