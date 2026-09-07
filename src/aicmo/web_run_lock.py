"""Serialize server-owned web runs across web workers and operator CLI commands."""

from __future__ import annotations

import hashlib
import inspect
import os
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import cast

from aicmo.errors import RunConflictError, WorkflowExecutionError
from aicmo.pack_edits import EditApproval, verify_edit_approval
from aicmo.paths import native_io_path, parse_safe_id, resolve_inside_repo
from aicmo.reporter import exclusive_file_lock
from aicmo.step_executor import WorkflowStepExecutor
from aicmo.store import WorkflowStore

_EDIT_STEP = "edit"


class _ThreadLocks(threading.local):
    def __init__(self) -> None:
        self.paths: set[tuple[int, str]] = set()


_held = _ThreadLocks()


@contextmanager
def web_run_lock(repo: Path, run_id: str, *, blocking: bool = True) -> Iterator[None]:
    parse_safe_id("run_id", run_id)
    if re.fullmatch(r"web-[0-9a-f]{32}", run_id) is None:
        yield
        return
    relative = f".aicmo/web-run-locks/{hashlib.sha256(run_id.encode()).hexdigest()}.lock"
    path = resolve_inside_repo(repo, relative, {})
    if path != repo.resolve() / relative:
        raise WorkflowExecutionError(_EDIT_STEP, "web run lock must not redirect")
    key = (os.getpid(), str(path))
    if key in _held.paths:
        yield
        return
    native_io_path(path.parent).mkdir(parents=True, exist_ok=True)
    with exclusive_file_lock(native_io_path(path), blocking=blocking):
        _held.paths.add(key)
        try:
            yield
        finally:
            _held.paths.remove(key)


def serialized_web_run[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    signature = inspect.signature(method)

    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        bound = signature.bind(*args, **kwargs)
        owner = cast("WorkflowStepExecutor", bound.arguments["self"])
        run_id = cast("str", bound.arguments["run_id"])
        with web_run_lock(owner.repo_root, run_id):
            if (
                method.__name__ != "apply_pack_edit"
                and re.fullmatch(r"web-[0-9a-f]{32}", run_id)
                and owner.store.db_path.exists()
            ):
                with WorkflowStore(owner.store.db_path, read_only=True).connect() as connection:
                    exists = connection.execute(
                        "select 1 from sqlite_master where type='table' "
                        "and name='pack_edit_receipts'"
                    ).fetchone()
                    receipt = (
                        exists
                        and connection.execute(
                            "select state,receipt_json from pack_edit_receipts where run_id=?",
                            (run_id,),
                        ).fetchone()
                    )
                if receipt and receipt["state"] == "applying":
                    raise RunConflictError(run_id, "confirmed edit application must recover first")
                if receipt and method.__name__ != "cancel":
                    verify_edit_approval(
                        owner,
                        run_id,
                        EditApproval.model_validate_json(receipt["receipt_json"]),
                    )
            return method(*args, **kwargs)

    return wrapped
