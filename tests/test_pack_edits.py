from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZipFile

import pytest

from aicmo.errors import RunConflictError, StepTransitionError, WorkflowExecutionError
from aicmo.export import export_local_pack
from aicmo.pack_edits import (
    EditApproval,
    digest,
    editable_values,
    inspect_base,
    merge_edit,
    pack_text,
)
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.test_delivery_manifest import PassReviewer
from tests.test_local_pack import (
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from collections.abc import Callable

RUN = "web-" + "1" * 32


@pytest.mark.parametrize("identifier", ["run", "client"])
def test_internal_identity_survives_phone_shaped_digits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, identifier: str
) -> None:
    client = "shop"
    suffix = "a" * 21 + "01012345678"
    if identifier == "run":
        monkeypatch.setattr(sys.modules[__name__], "RUN", "web-" + suffix)
    else:
        client = "web-client-" + suffix
    runner, receipt, body = _prepared(tmp_path, client=client)
    runner.apply_pack_edit(RUN, receipt, body)
    assert runner.resume(RUN).status == "success"
    assert export_local_pack(runner, RUN).is_file()


def _prepared(root: Path, *, client: str = "shop") -> tuple[WorkflowRunner, EditApproval, str]:
    runner = _runner(root)
    if client != "shop":
        shutil.copytree(root / "clients/shop", root / "clients" / client)
    configure_quota(runner.store, client, current_period(), 2, 3)
    assert (
        runner.run("local-store-pack", RUN, {**_brief(), "client": client}).status
        == "waiting_approval"
    )
    base, pack = inspect_base(runner, RUN)
    values = {**editable_values(pack), "news_0_title": "사장님이 고친 이번 주 안내"}
    body = pack_text(merge_edit(pack, values, runner.store.get_inputs(RUN)))
    receipt = EditApproval(
        schema_version="aicmo.web-edit-approval.v1",
        base=base,
        revision=1,
        edited_sha=digest(body),
        reviewer="web-user:1",
        requested_at=datetime.now(UTC),
    )
    return runner, receipt, body


def _receipt_state(runner: WorkflowRunner) -> str:
    with runner.store.connect() as connection:
        return str(
            connection.execute(
                "select state from pack_edit_receipts where run_id=?", (RUN,)
            ).fetchone()[0]
        )


def test_edit_apply_replay_delivery_and_original_preservation(tmp_path: Path) -> None:
    runner, receipt, body = _prepared(tmp_path)
    snapshot = tmp_path / ".aicmo/snapshots" / receipt.base.snapshot_sha
    before = snapshot.read_bytes()
    runner.apply_pack_edit(RUN, receipt, body)
    runner.apply_pack_edit(RUN, receipt, body)
    assert _receipt_state(runner) == "applied"
    assert runner.resume(RUN).status == "success"
    runner.apply_pack_edit(RUN, receipt, body)
    assert runner.store.get_step_attempt(RUN, "drafts") == 1
    assert snapshot.read_bytes() == before
    status = quota_status(runner.store, "shop", current_period())
    assert status["draft_used"] == 1
    assert status["packs"] == {
        "reserved": 0,
        "consumed": 1,
        "released": 0,
        "credited": 0,
        "unmetered": 0,
    }
    with ZipFile(export_local_pack(runner, RUN)) as archive:
        assert any(
            "사장님이 고친 이번 주 안내".encode() in archive.read(name)
            for name in archive.namelist()
        )
    artifact = tmp_path / f"artifacts/{RUN}/local-pack.json"
    artifact.write_bytes(before)
    with pytest.raises(WorkflowExecutionError, match="approval differs"):
        runner.apply_pack_edit(RUN, receipt, body)
    assert artifact.read_bytes() == before  # Never silently repair post-approval tampering.


class _Crash(BaseException):
    pass


@pytest.mark.parametrize("point", ["replace", "hash", "approval"])
def test_edit_crash_blocks_other_mutations_and_recovers_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    runner, receipt, body = _prepared(tmp_path)
    with monkeypatch.context() as patcher:
        if point == "replace":
            write = WorkflowRunner._write_pack_edit  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

            def crash_write(path: Path, value: str) -> None:
                write(path, value)
                raise _Crash

            patcher.setattr(WorkflowRunner, "_write_pack_edit", staticmethod(crash_write))
        elif point == "hash":
            record = WorkflowStore.record_output_hashes

            def crash_hash(
                self: WorkflowStore, run_id: str, step: str, hashes: dict[str, str]
            ) -> None:
                record(self, run_id, step, hashes)
                if step == "drafts":
                    raise _Crash

            patcher.setattr(WorkflowStore, "record_output_hashes", crash_hash)
        else:
            approve = WorkflowRunner._approve  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

            def crash_approval(
                self: WorkflowRunner,
                run_id: str,
                step_id: str,
                reviewer: str,
                notes: str,
                accept_edits: bool = False,
                photos_reviewed: bool = False,
            ) -> list[str]:
                approve(self, run_id, step_id, reviewer, notes, accept_edits, photos_reviewed)
                raise _Crash

            patcher.setattr(WorkflowRunner, "_approve", crash_approval)
        with pytest.raises(_Crash):
            runner.apply_pack_edit(RUN, receipt, body)
    assert _receipt_state(runner) == "applying"
    attempts = runner.store.get_step_attempt(RUN, "drafts")
    calls: list[Callable[[], object]] = [
        lambda: runner.resume(RUN),
        lambda: runner.approve(RUN, "owner_gate", "another-owner", "test"),
        lambda: runner.cancel(RUN),
        lambda: runner.retry(RUN, "drafts"),
        lambda: runner.reject(RUN, "owner_gate", "operator", "test"),
        lambda: runner.complete_verified_local_pack(RUN),
        lambda: runner.run("local-store-pack", RUN, _brief()),
    ]
    for call in calls:
        with pytest.raises(RunConflictError, match="recover first"):
            call()
    assert runner.store.get_step_attempt(RUN, "drafts") == attempts == 1
    runner.apply_pack_edit(RUN, receipt, body)
    assert runner.resume(RUN).status == "success"
    assert runner.store.get_step_attempt(RUN, "drafts") == 1
    assert quota_status(runner.store, "shop", current_period())["draft_used"] == 1


@pytest.mark.parametrize("mutation", ["snapshot", "attempt", "context", "photos", "spec"])
def test_edit_rejects_changed_base(tmp_path: Path, mutation: str) -> None:
    runner, receipt, body = _prepared(tmp_path)
    source = tmp_path / f"artifacts/{RUN}/local-pack.json"
    original = source.read_bytes()
    if mutation == "snapshot":
        (tmp_path / ".aicmo/snapshots" / receipt.base.snapshot_sha).write_text("changed")
    elif mutation == "attempt":
        with runner.store.connect() as connection:
            connection.execute(
                "update steps set attempt=attempt+1 where run_id=? and step_id='drafts'", (RUN,)
            )
    elif mutation == "spec":
        path = tmp_path / "agents/copywriter.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
    else:
        name = "context.md" if mutation == "context" else "photos.json"
        (tmp_path / f"artifacts/{RUN}" / name).write_text("changed")
    with pytest.raises((WorkflowExecutionError, RunConflictError)):
        runner.apply_pack_edit(RUN, receipt, body)
    assert source.read_bytes() == original
    assert runner.store.approval_for(RUN, "owner_gate") is None


@pytest.mark.parametrize("mutation", ["summary", "sources", "private"])
def test_edit_rejects_protected_or_private_content(tmp_path: Path, mutation: str) -> None:
    runner, receipt, body = _prepared(tmp_path)
    value = json.loads(body)
    if mutation == "private":
        value["news"][0]["body"] = "비밀번호: example-credential-do-not-store"
    elif mutation == "sources":
        value["sources"][0] = "제공하지 않은 새로운 사실"
    else:
        value["summary"] = "보호된 요약을 덮어쓰기"
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    receipt = receipt.model_copy(update={"edited_sha": digest(body)})
    with pytest.raises(WorkflowExecutionError):
        runner.apply_pack_edit(RUN, receipt, body)
    with runner.store.connect() as connection:
        assert connection.execute("select count(*) from pack_edit_receipts").fetchone()[0] == 0


def test_confirmed_edit_cannot_bless_another_edit_or_regenerate_it(tmp_path: Path) -> None:
    runner, receipt, body = _prepared(tmp_path)
    runner.apply_pack_edit(RUN, receipt, body)
    with pytest.raises(StepTransitionError, match="already recorded"):
        runner.approve(RUN, "owner_gate", "another-owner", "test", accept_edits=True)
    changed = json.loads(body)
    changed["news"][0]["title"] = "추가로 승인하지 않은 문안"
    path = tmp_path / f"artifacts/{RUN}/local-pack.json"
    path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    calls: list[Callable[[], object]] = [
        lambda: runner.approve(RUN, "owner_gate", "another-owner", "test", accept_edits=True),
        lambda: runner.resume(RUN),
        lambda: runner.run("local-store-pack", RUN, _brief()),
        lambda: runner.retry(RUN, "drafts"),
        lambda: runner.reject(RUN, "owner_gate", "operator", "test"),
        lambda: runner.complete_verified_local_pack(RUN),
    ]
    for call in calls:
        with pytest.raises(WorkflowExecutionError, match="approval differs"):
            call()
    assert runner.store.get_output_hashes(RUN, "drafts") == {
        f"artifacts/{RUN}/local-pack.json": receipt.edited_sha
    }
    assert runner.store.get_step_attempt(RUN, "drafts") == 1
    runner.cancel(RUN)
    assert runner.store.get_run(RUN)["status"] == "cancelled"


@pytest.mark.parametrize("verdict", ["WARN", "FAIL"])
def test_edited_pack_requires_semantic_pass(tmp_path: Path, verdict: str) -> None:
    runner, receipt, body = _prepared(tmp_path)
    runner = replace(runner, review_adapter=PassReviewer(verdict))
    runner.apply_pack_edit(RUN, receipt, body)
    runner.resume(RUN)
    with pytest.raises(WorkflowExecutionError):
        export_local_pack(runner, RUN)
    assert runner.store.get_step_attempt(RUN, "drafts") == 1


_PROCESS_STARTUP_SECONDS = 60 if sys.platform == "win32" else 10
_LOCK_ATTEMPT_SECONDS = 10
_PROCESS_RELEASE_SECONDS = _PROCESS_STARTUP_SECONDS + _LOCK_ATTEMPT_SECONDS + 30

_PROCESS_SCRIPT = r"""
import json, sys, time
from contextlib import contextmanager
from pathlib import Path
import aicmo.web_run_lock as locks
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from aicmo.pack_edits import EditApproval
from tests.test_local_pack import PackAdapter
from tests.test_delivery_manifest import PassReviewer
root, action = Path(sys.argv[1]), sys.argv[2]
receipt = EditApproval.model_validate_json((root/'edit-receipt.json').read_text())
body = (root/'edit-body.json').read_text(encoding='utf-8')
run_id = 'web-' + '1'*32
runner = WorkflowRunner(root, WorkflowStore(root/'.aicmo/runs.sqlite3'),
                        adapter=PackAdapter(), review_adapter=PassReviewer())
if action == 'paused':
    original = WorkflowRunner._write_pack_edit
    def pause(path, body):
        original(path, body)
        (root/'paused-ready').touch()
        deadline = time.monotonic() + float(sys.argv[3])
        while not (root/'release').exists():
            if time.monotonic() > deadline: raise TimeoutError('test release missing')
            time.sleep(.02)
    WorkflowRunner._write_pack_edit = staticmethod(pause)
else:
    original_lock = locks.exclusive_file_lock
    @contextmanager
    def announce_lock(path, **kwargs):
        (root/'competitor-lock').touch()
        with original_lock(path, **kwargs):
            (root/'competitor-acquired').touch()
            yield
    locks.exclusive_file_lock = announce_lock
    (root/'competitor-ready').touch()
try:
    if action in ('paused', 'apply'): runner.apply_pack_edit(run_id, receipt, body)
    elif action == 'resume': runner.resume(run_id)
    else: runner.approve(run_id, 'owner_gate', 'another-owner', 'synthetic', accept_edits=True)
except Exception as exc:
    print(type(exc).__name__)
else:
    print('ok')
"""


def _wait_marker(
    path: Path, process: subprocess.Popen[str], *, timeout: float = _PROCESS_STARTUP_SECONDS
) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        assert process.poll() is None, process.communicate(timeout=5)
        assert time.monotonic() < deadline, "test process did not reach lock boundary"
        time.sleep(0.02)


def _stop_process(process: subprocess.Popen[str]) -> None:
    try:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=10)
    finally:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def test_competing_process_timeout_closes_pipes(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        with pytest.raises(AssertionError, match="did not reach lock boundary"):
            _wait_marker(tmp_path / "missing-ready", process, timeout=0)
    finally:
        _stop_process(process)
    assert process.poll() is not None
    assert process.stdout is not None
    assert process.stdout.closed
    assert process.stderr is not None
    assert process.stderr.closed


@pytest.mark.parametrize("action", ["apply", "resume", "approve"])
def test_edit_serializes_competing_processes(tmp_path: Path, action: str) -> None:
    runner, receipt, body = _prepared(tmp_path)
    (tmp_path / "edit-receipt.json").write_text(receipt.model_dump_json(), encoding="utf-8")
    (tmp_path / "edit-body.json").write_text(body, encoding="utf-8")
    script = tmp_path / "compete.py"
    script.write_text(_PROCESS_SCRIPT, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    processes: list[subprocess.Popen[str]] = []
    try:
        for name in ("paused", action):
            process = subprocess.Popen(  # noqa: S603 — fixed synthetic process script
                [sys.executable, str(script), str(tmp_path), name, str(_PROCESS_RELEASE_SECONDS)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            processes.append(process)
            _wait_marker(
                tmp_path / ("paused-ready" if name == "paused" else "competitor-ready"), process
            )
        _wait_marker(tmp_path / "competitor-lock", processes[1], timeout=_LOCK_ATTEMPT_SECONDS)
        time.sleep(0.15)
        assert processes[1].poll() is None  # Competing mutation must wait for the edit lock.
        assert not (tmp_path / "competitor-acquired").exists()
        (tmp_path / "release").touch()
        for index, process in enumerate(processes):
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr
            assert stdout.strip() == (
                "StepTransitionError" if index == 1 and action == "approve" else "ok"
            ), stdout + stderr
    finally:
        with ExitStack() as cleanup:
            for process in processes:
                cleanup.callback(_stop_process, process)
            (tmp_path / "release").touch()
    assert (tmp_path / "competitor-acquired").exists()
    assert _receipt_state(runner) == "applied"
    assert runner.store.get_step_attempt(RUN, "drafts") == 1
    assert runner.store.get_output_hashes(RUN, "drafts") == {
        f"artifacts/{RUN}/local-pack.json": receipt.edited_sha
    }
    assert runner.resume(RUN).status == "success"
