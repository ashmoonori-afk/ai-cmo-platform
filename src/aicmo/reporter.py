from __future__ import annotations

import importlib
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast

from aicmo.paths import parse_safe_id
from aicmo.store import WorkflowStore

_INSIGHTS_HEADER = (
    "# 리서치 인사이트\n\n(Reporter가 근거 있는 인사이트를 누적합니다. append-only.)\n"
)

class _MsvcrtModule(Protocol):
    LK_LOCK: int
    LK_UNLCK: int

    def locking(self, fd: int, mode: int, nbytes: int) -> None: ...


class _FcntlModule(Protocol):
    LOCK_EX: int
    LOCK_UN: int

    def flock(self, fd: int, operation: int) -> None: ...


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
        appended = append_insight(target, row)
        store.mark_kb_update_consumed(int(row["kb_update_id"]))
        if appended:
            flushed += 1
    return flushed


def append_insight(target: Path, row: sqlite3.Row) -> bool:
    """Append the row's KB block; return True if written, False if already present."""
    run_id = str(row["run_id"])
    step_id = str(row["step_id"])
    path = str(row["path"])
    # Content-addressed marker: if a crash replays a row whose block was already
    # appended (but not yet consumed), the marker is present and we skip — no duplicate.
    target.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_file_lock(target.with_name(target.name + ".lock")):
        marker = f"<!-- kb:{run_id}:{step_id}:{path} -->"
        existing = target.read_text(encoding="utf-8") if target.exists() else _INSIGHTS_HEADER
        if marker in existing:
            return False
        created = str(row["created_at"])[:10]
        content = str(row["content"])
        block = f"\n{marker}\n### [{created} / {run_id} / {step_id}]\n\n{content}\n\n---\n"
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(existing + block, encoding="utf-8")
        tmp.replace(target)
    return True


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    with lock_path.open("a+b") as handle:
        if sys.platform == "win32":
            locker = cast(
                "_MsvcrtModule",
                cast("object", importlib.import_module("msvcrt")),
            )
            locker.locking(handle.fileno(), locker.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                locker.locking(handle.fileno(), locker.LK_UNLCK, 1)
        else:
            locker = cast(
                "_FcntlModule",
                cast("object", importlib.import_module("fcntl")),
            )
            locker.flock(handle.fileno(), locker.LOCK_EX)
            try:
                yield
            finally:
                locker.flock(handle.fileno(), locker.LOCK_UN)
