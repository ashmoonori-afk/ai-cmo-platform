from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from aicmo.paths import parse_safe_id

_FEEDBACK_HEADER = (
    "# Artifact Feedback\n\n"
    "Append-only feedback used to improve workflow prompts, gates, and engine defaults.\n"
)


def record_artifact_feedback(
    repo_root: Path,
    client: str,
    run_id: str,
    artifact_format: str,
    feedback: str,
) -> Path:
    client_slug = parse_safe_id("client", client).value
    safe_run_id = parse_safe_id("run_id", run_id).value
    target = repo_root / "knowledge-base" / "_engine-improvements" / "artifact-feedback.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = target.read_text(encoding="utf-8") if target.exists() else _FEEDBACK_HEADER
    created_at = datetime.now(UTC).isoformat(timespec="seconds")
    block = "\n".join(
        [
            "",
            f"## {created_at} / {safe_run_id}",
            "",
            f"- client: {client_slug}",
            f"- artifact_format: {artifact_format.strip() or 'unspecified'}",
            f"- feedback: {feedback.strip()}",
            "",
        ],
    )
    target.write_text(existing.rstrip() + "\n" + block, encoding="utf-8")
    return target
