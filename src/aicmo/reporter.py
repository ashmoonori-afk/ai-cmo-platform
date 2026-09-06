from __future__ import annotations

import hashlib
import importlib
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol, cast

from aicmo.errors import WorkflowExecutionError
from aicmo.paths import parse_safe_id, resolve_inside_repo
from aicmo.redaction import safe_kb_text
from aicmo.store import WorkflowStore

_INSIGHTS_HEADER = (
    "# 리서치 인사이트\n\n(Reporter가 근거 있는 인사이트를 누적합니다. append-only.)\n"
)
_STORAGE_STEP = "knowledge-storage"


def append_record(
    target: Path,
    marker: str,
    heading: str,
    content: str,
    header: str,
    *,
    legacy_marker: str | None = None,
) -> bool:
    """Append one literal, minimized record, preserving every existing byte."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_file_lock(target.with_name(target.name + ".lock")):
        if target.is_symlink():
            reason = "knowledge file must not be a symbolic link"
            raise WorkflowExecutionError(_STORAGE_STEP, reason)
        # ponytail: whole-file rewrite; segment storage if measured KB size makes this slow.
        existing = target.read_bytes() if target.exists() else header.encode("utf-8")
        try:
            existing.decode("utf-8-sig")
        except UnicodeError:
            reason = "existing knowledge file is not UTF-8; preserve and repair it before appending"
            raise WorkflowExecutionError(_STORAGE_STEP, reason) from None
        candidates = [marker] + ([legacy_marker] if legacy_marker is not None else [])
        normalized = b"\n" + existing.replace(b"\r\n", b"\n") + b"\n"
        if any(f"\n{item}\n".encode() in normalized for item in candidates):
            return False
        safe = safe_kb_text(content)
        # Indentation keeps untrusted text literal and prevents top-level marker spoofing.
        literal = "\n".join("    " + line for line in safe.split("\n"))
        block = f"\n{marker}\n### {heading}\n\n{literal}\n\n---\n".encode()
        with NamedTemporaryFile(
            dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
        try:
            temporary.write_bytes(existing + block)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return True


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
        slug = parse_safe_id("client", row_client)
        parent = resolve_inside_repo(root, f"knowledge-base/{slug}", {})
        target = parent / "insights.md"
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
    parse_safe_id("run_id", run_id)
    parse_safe_id("step_id", step_id)
    identity = json.dumps([run_id, step_id, path], ensure_ascii=False).encode("utf-8")
    marker = f"<!-- kb:v2:{hashlib.sha256(identity).hexdigest()} -->"
    legacy = (
        f"<!-- kb:{run_id}:{step_id}:{path} -->" if "\n" not in path and "\r" not in path else None
    )
    created = str(row["created_at"])[:10]
    try:
        date.fromisoformat(created)
    except ValueError:
        reason = "queued knowledge has an invalid creation date"
        raise WorkflowExecutionError(_STORAGE_STEP, reason) from None
    return append_record(
        target,
        marker,
        f"[{created} / {run_id} / {step_id}]",
        str(row["content"]),
        _INSIGHTS_HEADER,
        legacy_marker=legacy,
    )


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    with lock_path.open("a+b") as handle:
        if sys.platform == "win32":
            locker = cast(
                "_MsvcrtModule",
                cast("object", importlib.import_module("msvcrt")),
            )
            handle.seek(0)
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
