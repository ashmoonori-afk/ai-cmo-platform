# pyright: reportImportCycles=false
# Executor annotations are TYPE_CHECKING-only; verification has no runtime import cycle.
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from aicmo.errors import WorkflowExecutionError
from aicmo.local_pack import WORKFLOW_ID, render_pack, validate_pack
from aicmo.models import ApprovalDecision
from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.source_input import JsonValue, prepare_workflow_inputs
from aicmo.spec import RUN_SPEC_REVISION, load_workflow_spec, run_spec_digest

if TYPE_CHECKING:
    from aicmo.step_executor import WorkflowStepExecutor

EXPORT_STEP = "export"


def verified_delivery(  # noqa: C901 — sequential fail-closed delivery checks
    runner: WorkflowStepExecutor, run_id: str, workflow_id: str
) -> tuple[dict[str, str], dict[str, bytes]]:
    parse_safe_id("run_id", run_id)
    run = runner.store.get_run(run_id)
    if run["workflow_id"] != workflow_id or run["status"] != "success":
        raise WorkflowExecutionError(EXPORT_STEP, f"a successful {workflow_id} run is required")
    inputs = runner.store.get_inputs(run_id)
    spec = load_workflow_spec(runner.repo_root, workflow_id)
    if (
        run["spec_revision"] != RUN_SPEC_REVISION
        or run["spec_digest"] != run_spec_digest(spec, inputs)
        or prepare_workflow_inputs(spec.inputs, inputs).values != inputs
    ):
        raise WorkflowExecutionError(EXPORT_STEP, "run specification or privacy rules changed")
    for step in spec.steps:
        if (
            step.requires_approval
            and runner.store.approval_for(run_id, step.id) != ApprovalDecision.APPROVED
        ):
            raise WorkflowExecutionError(EXPORT_STEP, "owner approval is required")
    contents = runner.verified_export_outputs(spec, run_id, inputs)
    try:
        manifest = cast(
            "JsonValue", json.loads(contents[f"artifacts/{run_id}/delivery-review.json"])
        )
    except (KeyError, ValueError):
        raise WorkflowExecutionError(EXPORT_STEP, "invalid delivery artifacts") from None
    if not isinstance(manifest, dict) or manifest.get("deliverable") is not True:
        raise WorkflowExecutionError(
            EXPORT_STEP, "delivery is blocked or demo; reviewer PASS required"
        )
    semantic = manifest.get("semantic_review")
    if (
        manifest.get("run_id") != run_id
        or manifest.get("workflow_id") != workflow_id
        or manifest.get("status") != "PASS"
        or not isinstance(semantic, dict)
        or semantic.get("status") != "PASS"
    ):
        raise WorkflowExecutionError(EXPORT_STEP, "terminal semantic PASS evidence is required")
    refs = manifest.get("artifacts")
    if not isinstance(refs, list) or not refs:
        raise WorkflowExecutionError(EXPORT_STEP, "reviewed artifact list is missing")
    for ref in refs:
        if not isinstance(ref, dict):
            raise WorkflowExecutionError(EXPORT_STEP, "invalid reviewed artifact reference")
        path = ref.get("path")
        if (
            not isinstance(path, str)
            or path not in contents
            or ref.get("sha256") != hashlib.sha256(contents[path]).hexdigest()
            or ref.get("truncated") is not False
        ):
            raise WorkflowExecutionError(EXPORT_STEP, "reviewed artifact version differs")
    return inputs, contents


def _verified_pack(runner: WorkflowStepExecutor, run_id: str) -> tuple[str, dict[str, str]]:
    inputs, contents = verified_delivery(runner, run_id, WORKFLOW_ID)
    raw_pack = contents[f"artifacts/{run_id}/local-pack.json"]
    pack_text = raw_pack.decode("utf-8")
    manifest = cast(
        "dict[str, JsonValue]", json.loads(contents[f"artifacts/{run_id}/delivery-review.json"])
    )
    digest = hashlib.sha256(raw_pack).hexdigest()
    refs = manifest.get("artifacts")
    if not isinstance(refs, list):
        raise WorkflowExecutionError(EXPORT_STEP, "invalid reviewed artifact list")
    if not any(
        isinstance(ref, dict)
        and ref.get("path") == f"artifacts/{run_id}/local-pack.json"
        and ref.get("sha256") == digest
        for ref in refs
    ):
        raise WorkflowExecutionError(EXPORT_STEP, "reviewed pack version does not match")
    pack = validate_pack(pack_text, inputs)
    files = render_pack(pack)
    files["manifest.json"] = (
        json.dumps(
            {
                "schema_version": "aicmo.local-export.v1",
                "run_id": run_id,
                "source_sha256": digest,
                "approval": "approved",
                "review": "PASS",
                "external_publish_status": "not_published",
                "visual_asset_status": "unavailable",
                "files": {
                    name: hashlib.sha256(text.encode("utf-8")).hexdigest()
                    for name, text in files.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    return digest, files


def export_local_pack(runner: WorkflowStepExecutor, run_id: str) -> Path:
    """Export captured, hash-verified approved bytes; never generate or publish content."""
    parse_safe_id("run_id", run_id)
    runner.store.initialize()
    # ponytail: SQLite write lock serializes export with cancellation/retry in this local CLI.
    # Move to per-store jobs if export throughput becomes a measured bottleneck.
    with runner.store.connect() as connection:
        connection.execute("begin immediate")
        digest, files = _verified_pack(runner, run_id)
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            for name, text in files.items():
                info = ZipInfo(name)
                info.compress_type = ZIP_DEFLATED
                archive.writestr(info, text.encode("utf-8"))
        payload = buffer.getvalue()
        target = resolve_inside_repo(
            runner.repo_root,
            f"artifacts/{run_id}/exports/local-pack-{digest[:16]}.zip",
            {},
        )
        if not target.is_relative_to(runner.repo_root.resolve() / "artifacts" / run_id):
            raise WorkflowExecutionError(
                EXPORT_STEP, "export path leaves this run's artifact folder"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != payload:
                raise WorkflowExecutionError(
                    EXPORT_STEP, "existing export differs; preserve and inspect it"
                )
            return target
        with TemporaryDirectory(prefix=".export-", dir=target.parent) as staging:
            temp = Path(staging) / "package.zip"
            temp.write_bytes(payload)
            temp.replace(target)
    return target
