"""Owner-confirmed text edits; frozen facts, photos and approval snapshots remain authoritative."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from aicmo.errors import WorkflowExecutionError
from aicmo.local_pack import MAX_PACK_BYTES, WORKFLOW_ID, LocalPack, validate_pack
from aicmo.models import ApprovalDecision, StepStatus
from aicmo.paths import native_io_path, resolve_inside_repo
from aicmo.redaction import contains_raw_secret, minimize_customer_pii
from aicmo.source_input import prepare_workflow_inputs
from aicmo.spec import RUN_SPEC_REVISION, load_workflow_spec, run_spec_digest

if TYPE_CHECKING:
    from aicmo.models import WorkflowStep
    from aicmo.step_executor import WorkflowStepExecutor

_EDIT_STEP = "edit"

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class EditBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["aicmo.pack-edit-base.v1"] = "aicmo.pack-edit-base.v1"
    workflow_id: Literal["local-store-pack"] = "local-store-pack"
    spec_digest: Hash
    spec_revision: int
    draft_attempt: int = Field(ge=1)
    draft_sha: Hash
    snapshot_sha: Hash
    photo_sha: Hash
    dependencies_sha: Hash


class EditApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["aicmo.web-edit-approval.v1"]
    base: EditBase
    revision: int = Field(ge=0)
    edited_sha: Hash
    reviewer: Annotated[str, Field(pattern=r"^web-user:[1-9][0-9]*$")]
    requested_at: datetime


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack_text(pack: LocalPack) -> str:
    return pack.model_dump_json()


def editable_values(pack: LocalPack) -> dict[str, str]:
    values = {
        f"news_{index}_{name}": str(getattr(item, name))
        for index, item in enumerate(pack.news)
        for name in ("title", "body", "cta", "period")
    }
    return {**values, **{f"reply_{i}": item.body for i, item in enumerate(pack.replies)}}


def merge_edit(original: LocalPack, values: dict[str, str], inputs: dict[str, str]) -> LocalPack:
    if values.keys() != editable_values(original).keys():
        raise WorkflowExecutionError(_EDIT_STEP, "unexpected editable fields")
    for value in values.values():
        if (
            contains_raw_secret(value)
            or minimize_customer_pii(value) != value
            or any(
                (
                    unicodedata.category(char).startswith("C")
                    or unicodedata.category(char) in {"Zl", "Zp"}
                )
                and char not in "\n\t"
                for char in value
            )
        ):
            raise WorkflowExecutionError(
                _EDIT_STEP, "remove private or hidden content before saving"
            )
    changed = original.model_copy(deep=True)
    for index, item in enumerate(changed.news):
        for name in ("title", "body", "cta", "period"):
            setattr(item, name, values[f"news_{index}_{name}"])
    for index, item in enumerate(changed.replies):
        item.body = values[f"reply_{index}"]
    return validate_pack(pack_text(changed), inputs)


def _read(repo: Path, relative: str, maximum: int) -> bytes:
    path = resolve_inside_repo(repo, relative, {})
    if path != repo.resolve() / relative or not native_io_path(path).is_file():
        raise WorkflowExecutionError(_EDIT_STEP, "edit source must be a regular, unredirected file")
    with native_io_path(path).open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise WorkflowExecutionError(_EDIT_STEP, "edit source exceeds its byte limit")
    return raw


def inspect_base(  # noqa: C901, PLR0912 — sequential frozen-base verification
    runner: WorkflowStepExecutor, run_id: str, *, recovering: EditApproval | None = None
) -> tuple[EditBase, LocalPack]:
    if re.fullmatch(r"web-[0-9a-f]{32}", run_id) is None:
        raise WorkflowExecutionError(_EDIT_STEP, "a server-owned web run is required")
    run = runner.store.get_run(run_id)
    inputs = runner.store.get_inputs(run_id)
    spec = load_workflow_spec(runner.repo_root, WORKFLOW_ID)
    if (
        run["workflow_id"] != WORKFLOW_ID
        or run["spec_revision"] != RUN_SPEC_REVISION
        or run["spec_digest"] != run_spec_digest(spec, inputs)
        or prepare_workflow_inputs(spec.inputs, inputs).values != inputs
    ):
        raise WorkflowExecutionError(_EDIT_STEP, "edit specification or input facts changed")
    preceding: list[WorkflowStep] = []
    for step in spec.execution_order():
        if step.id == "owner_gate":
            break
        preceding.append(step)
    checked_steps = [step for step in preceding if recovering is None or step.id != "drafts"]
    runner.verified_export_outputs(
        spec.model_copy(update={"steps": tuple(checked_steps)}), run_id, inputs
    )
    relative = f"artifacts/{run_id}/local-pack.json"
    with runner.store.connect() as connection:
        snapshots = connection.execute(
            "select source_path,snapshot_path,sha256 from approval_snapshots "
            "where run_id=? and gate_id='owner_gate' order by source_path",
            (run_id,),
        ).fetchall()
    expected = {
        path for step in preceding for path in runner.store.get_step_outputs(run_id, step.id)
    }
    if {str(row["source_path"]) for row in snapshots} != expected or relative not in expected:
        raise WorkflowExecutionError(_EDIT_STEP, "approval snapshot inventory changed")
    original = b""
    for row in snapshots:
        sha = str(row["sha256"])
        if (
            re.fullmatch(r"[a-f0-9]{64}", sha) is None
            or row["snapshot_path"] != f".aicmo/snapshots/{sha}"
        ):
            raise WorkflowExecutionError(_EDIT_STEP, "invalid approval snapshot identity")
        raw = _read(runner.repo_root, str(row["snapshot_path"]), 2 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise WorkflowExecutionError(_EDIT_STEP, "approval snapshot bytes changed")
        allowed = {sha}
        if row["source_path"] == relative:
            original = raw
            if recovering is not None:
                allowed.add(recovering.edited_sha)
        current = _read(runner.repo_root, str(row["source_path"]), 2 * 1024 * 1024)
        if hashlib.sha256(current).hexdigest() not in allowed:
            raise WorkflowExecutionError(_EDIT_STEP, "artifact differs from confirmed edit base")
    original_sha = hashlib.sha256(original).hexdigest()
    draft_hashes = runner.store.get_output_hashes(run_id, "drafts")
    allowed_hashes = {original_sha}
    if recovering is not None:
        allowed_hashes.add(recovering.edited_sha)
    if (
        runner.store.get_step_outputs(run_id, "drafts") != [relative]
        or set(draft_hashes) != {relative}
        or draft_hashes[relative] not in allowed_hashes
        or runner.store.get_step_status(run_id, "drafts") != StepStatus.SUCCESS
    ):
        raise WorkflowExecutionError(_EDIT_STEP, "draft output version changed")
    versions = [
        [
            step.id,
            runner.store.get_step_attempt(run_id, step.id),
            runner.store.get_consumed_ref_digest(run_id, step.id),
        ]
        for step in preceding
    ]
    photo_sha, _ = runner.verified_photos(run_id)
    base = EditBase(
        spec_digest=str(run["spec_digest"]),
        spec_revision=int(run["spec_revision"]),
        draft_attempt=runner.store.get_step_attempt(run_id, "drafts"),
        draft_sha=original_sha,
        snapshot_sha=original_sha,
        photo_sha=photo_sha,
        dependencies_sha=digest(
            json.dumps([versions, [dict(row) for row in snapshots]], sort_keys=True)
        ),
    )
    if recovering is not None and base != recovering.base:
        raise WorkflowExecutionError(_EDIT_STEP, "confirmed edit base changed")
    return base, validate_pack(original.decode("utf-8"), inputs)


def prepare_edit_application(
    runner: WorkflowStepExecutor, run_id: str, receipt: EditApproval, body: str
) -> Path:
    """Persist intent before file replacement; only exact retries may resume it."""
    if len(body.encode("utf-8")) > MAX_PACK_BYTES or digest(body) != receipt.edited_sha:
        raise WorkflowExecutionError(_EDIT_STEP, "confirmed edit bytes changed")
    base, original = inspect_base(runner, run_id, recovering=receipt)
    inputs = runner.store.get_inputs(run_id)
    edited = validate_pack(body, inputs)
    if pack_text(merge_edit(original, editable_values(edited), inputs)) != body:
        raise WorkflowExecutionError(_EDIT_STEP, "protected pack fields changed")
    gate = runner.store.get_step_status(run_id, "owner_gate")
    approval = runner.store.approval_for(run_id, "owner_gate")
    payload = receipt.model_dump_json()
    with runner.store.connect() as connection:
        connection.execute("begin immediate")
        prior = connection.execute(
            "select * from pack_edit_receipts where run_id=?", (run_id,)
        ).fetchone()
        if prior is None:
            if gate != StepStatus.WAITING_APPROVAL or approval is not None:
                raise WorkflowExecutionError(_EDIT_STEP, "owner gate is no longer editable")
            # No unrecorded edited file is accepted as an initial apply.
            raw = _read(runner.repo_root, f"artifacts/{run_id}/local-pack.json", MAX_PACK_BYTES)
            if hashlib.sha256(raw).hexdigest() != base.draft_sha:
                raise WorkflowExecutionError(_EDIT_STEP, "unrecorded edit cannot be adopted")
            connection.execute(
                "insert into pack_edit_receipts values(?,?,?,'applying')", (run_id, payload, body)
            )
        elif prior["receipt_json"] != payload or prior["body"] != body:
            raise WorkflowExecutionError(_EDIT_STEP, "another edit receipt is already recorded")
    return resolve_inside_repo(runner.repo_root, f"artifacts/{run_id}/local-pack.json", {})


def verify_edit_approval(runner: WorkflowStepExecutor, run_id: str, receipt: EditApproval) -> None:
    with runner.store.connect() as connection:
        row = connection.execute(
            "select reviewer,photo_manifest_sha256 from approvals "
            "where run_id=? and step_id='owner_gate'",
            (run_id,),
        ).fetchone()
    if (
        runner.store.approval_for(run_id, "owner_gate") != ApprovalDecision.APPROVED
        or row is None
        or row["reviewer"] != receipt.reviewer
        or row["photo_manifest_sha256"] != receipt.base.photo_sha
        or runner.store.get_output_hashes(run_id, "drafts")
        != {f"artifacts/{run_id}/local-pack.json": receipt.edited_sha}
        or hashlib.sha256(
            _read(runner.repo_root, f"artifacts/{run_id}/local-pack.json", MAX_PACK_BYTES)
        ).hexdigest()
        != receipt.edited_sha
    ):
        raise WorkflowExecutionError(_EDIT_STEP, "applied edit approval differs from receipt")
