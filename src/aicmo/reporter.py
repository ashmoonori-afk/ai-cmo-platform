from __future__ import annotations

import sqlite3
from pathlib import Path

from aicmo.paths import parse_safe_id
from aicmo.store import WorkflowStore

_INSIGHTS_HEADER = (
    "# 리서치 인사이트\n\n(Reporter가 근거 있는 인사이트를 누적합니다. append-only.)\n"
)


def flush_kb_updates(repo_root: Path, store: WorkflowStore, client: str | None = None) -> int:
    """Append queued kb_updates to knowledge-base/<client>/insights.md, then mark consumed.

    Append-only and idempotent: a row is consumed exactly once, so re-flushing is a no-op.
    Reporter remains the only writer of durable KB, per prompts/shared/knowledge-update.md.
    """
    store.initialize()
    root = repo_root.resolve()
    flushed = 0
    for row in store.pending_kb_updates(client):
        row_client = str(row["client"]).strip()
        if not row_client:
            continue
        slug = parse_safe_id("client", row_client).value
        target = (root / "knowledge-base" / slug / "insights.md").resolve()
        if not target.is_relative_to(root):
            continue
        appended = _append_insight(target, row)
        store.mark_kb_update_consumed(int(row["kb_update_id"]))
        if appended:
            flushed += 1
    return flushed


def _append_insight(target: Path, row: sqlite3.Row) -> bool:
    """Append the row's KB block; return True if written, False if already present."""
    run_id = str(row["run_id"])
    step_id = str(row["step_id"])
    path = str(row["path"])
    # Content-addressed marker: if a crash replays a row whose block was already
    # appended (but not yet consumed), the marker is present and we skip — no duplicate.
    marker = f"<!-- kb:{run_id}:{step_id}:{path} -->"
    existing = target.read_text(encoding="utf-8") if target.exists() else _INSIGHTS_HEADER
    if marker in existing:
        return False
    created = str(row["created_at"])[:10]
    content = str(row["content"])
    block = f"\n{marker}\n### [{created} / {run_id} / {step_id}]\n\n{content}\n\n---\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic read-modify-write so a crash mid-append cannot leave a torn marker line.
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(existing + block, encoding="utf-8")
    tmp.replace(target)
    return True
