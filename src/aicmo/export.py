from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from aicmo.errors import WorkflowExecutionError
from aicmo.local_pack import WORKFLOW_ID, render_pack, validate_pack
from aicmo.models import ApprovalDecision
from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.runner import WorkflowRunner
from aicmo.source_input import JsonValue, prepare_workflow_inputs
from aicmo.spec import RUN_SPEC_REVISION, load_workflow_spec, run_spec_digest

EXPORT_STEP = "export"


def _verified_pack(runner: WorkflowRunner, run_id: str) -> tuple[str, dict[str, str]]:
    run = runner.store.get_run(run_id)
    if run["workflow_id"] != WORKFLOW_ID or run["status"] != "success":
        raise WorkflowExecutionError(EXPORT_STEP, "a successful local-store-pack run is required")
    inputs = runner.store.get_inputs(run_id)
    spec = load_workflow_spec(runner.repo_root, WORKFLOW_ID)
    if (
        run["spec_revision"] != RUN_SPEC_REVISION
        or run["spec_digest"] != run_spec_digest(spec, inputs)
        or prepare_workflow_inputs(spec.inputs, inputs).values != inputs
    ):
        raise WorkflowExecutionError(EXPORT_STEP, "run specification or privacy rules changed")
    if runner.store.approval_for(run_id, "owner_gate") != ApprovalDecision.APPROVED:
        raise WorkflowExecutionError(EXPORT_STEP, "owner approval is required")
    contents = runner.verified_export_outputs(spec, run_id, inputs)
    try:
        manifest = cast(
            "JsonValue", json.loads(contents[f"artifacts/{run_id}/delivery-review.json"])
        )
        raw_pack = contents[f"artifacts/{run_id}/local-pack.json"]
        pack_text = raw_pack.decode("utf-8")
    except (KeyError, ValueError):
        raise WorkflowExecutionError(EXPORT_STEP, "invalid delivery artifacts") from None
    if not isinstance(manifest, dict) or manifest.get("deliverable") is not True:
        raise WorkflowExecutionError(
            EXPORT_STEP, "delivery is blocked or demo; reviewer PASS required"
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


def export_local_pack(runner: WorkflowRunner, run_id: str) -> Path:
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
