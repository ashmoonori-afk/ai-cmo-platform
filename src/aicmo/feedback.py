from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.redaction import safe_kb_text
from aicmo.reporter import append_record

_FEEDBACK_HEADER = (
    "# Artifact Feedback\n\n"
    "Append-only feedback used to improve workflow prompts, gates, and engine defaults.\n"
)


def prepare_feedback(
    client: str,
    run_id: str,
    artifact_format: str,
    feedback: str,
) -> str:
    client_slug = parse_safe_id("client", client)
    safe_run_id = parse_safe_id("run_id", run_id)
    safe_feedback = safe_kb_text(feedback)
    safe_format = safe_kb_text(artifact_format.strip() or "unspecified")
    return safe_kb_text(
        "\n".join(
            [
                f"- client: {client_slug}",
                f"- run_id: {safe_run_id}",
                f"- artifact_format: {safe_format}",
                f"- feedback: {safe_feedback}",
            ],
        )
    )


def record_artifact_feedback(
    repo_root: Path,
    client: str,
    run_id: str,
    artifact_format: str,
    feedback: str,
) -> Path:
    body = prepare_feedback(client, run_id, artifact_format, feedback)
    parent = resolve_inside_repo(
        repo_root,
        "knowledge-base/_engine-improvements",
        {},
    )
    target = parent / "artifact-feedback.md"
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    append_record(
        target,
        f"<!-- feedback:v1:{digest} -->",
        f"[{created_at} / {run_id}]",
        body,
        _FEEDBACK_HEADER,
    )
    return target
