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
        _append_insight(target, row)
        store.mark_kb_update_consumed(int(row["kb_update_id"]))
        flushed += 1
    return flushed


def _append_insight(target: Path, row: sqlite3.Row) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(_INSIGHTS_HEADER, encoding="utf-8")
    created = str(row["created_at"])[:10]
    run_id = str(row["run_id"])
    step_id = str(row["step_id"])
    content = str(row["content"])
    block = f"\n### [{created} / {run_id} / {step_id}]\n\n{content}\n\n---\n"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(block)
