from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path

import pytest
from scripts import rehearse_store_recovery as recovery

from aicmo.paths import native_io_path

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("store-recovery") / "fixture"
    completed = subprocess.run(  # noqa: S603 — fixed module and newly allocated synthetic path
        [sys.executable, "-m", "scripts.rehearse_store_recovery", "--output", str(root)],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
    return root


def _stamps(root: Path, paths: Iterable[str]) -> dict[str, dict[str, str | int]]:
    stamps: dict[str, dict[str, str | int]] = {}
    for relative in paths:
        raw = native_io_path(root / relative).read_bytes()
        stamps[relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
    return stamps


def _copy_files(source: Path, destination: Path, names: Iterable[str]) -> None:
    native_io_path(destination).mkdir()
    for relative in names:
        target = native_io_path(destination / relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(native_io_path(source / relative).read_bytes())


def _tamper(root: Path, mutation: str, manifest: recovery.Manifest) -> None:
    if mutation == "artifact":
        relative = f"artifacts/{manifest.complete_run}/local-pack.json"
        target = native_io_path(root / relative)
        target.write_bytes(target.read_bytes() + b"\n")
    else:
        native_io_path(root / recovery.DB_PATHS[0]).write_bytes(
            native_io_path(root / recovery.DB_PATHS[1]).read_bytes()
        )


def test_rehearsal_preserves_source_and_restores_both_databases(rehearsal: Path) -> None:
    source, restored = rehearsal / "source", rehearsal / "restored"
    manifest = recovery.read_manifest(rehearsal / "backup")
    evidence = json.loads((rehearsal / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "synthetic-pass"
    assert evidence["provider"] == "synthetic-only"
    assert evidence["operation_scope"] == "stopped-synthetic-only"
    assert evidence["source_before"] == evidence["source_after"]
    sidecars = {
        *(f"{name}{suffix}" for name in recovery.DB_PATHS for suffix in ("-wal", "-shm")),
        ".aicmo/web-worker.lock",
        f".aicmo/web-run-locks/{hashlib.sha256(manifest.complete_run.encode()).hexdigest()}.lock",
    }
    for observed in (evidence["source_sidecars_before"], evidence["source_sidecars_after"]):
        assert set(observed) <= sidecars
        for value in observed.values():
            recovery.FileStamp.model_validate(value)
    assert set(evidence["source_after"]) == set(manifest.files)
    assert set(recovery.DB_PATHS) <= manifest.files.keys()
    assert _stamps(source, manifest.files) == evidence["source_after"]
    assert _stamps(restored, manifest.files) == {
        relative: stamp.model_dump() for relative, stamp in manifest.files.items()
    }
    verification = recovery.verify_fixture(restored, manifest)
    assert verification == evidence["verification"]
    assert verification["completed_jobs"] == 1
    assert verification["queued_jobs"] == 1
    assert verification["engine_runs"] == 1
    assert len(str(verification["bundle_sha256"])) == 64
    with closing(
        sqlite3.connect((restored / recovery.DB_PATHS[0]).resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        states = dict(
            connection.execute("select state, count(*) from store_app_job group by state")
        )
    assert states == {"success": 1, "queued": 1}
    with closing(
        sqlite3.connect((restored / recovery.DB_PATHS[1]).resolve().as_uri() + "?mode=ro", uri=True)
    ) as connection:
        runs = connection.execute("select run_id, status from runs").fetchall()
    assert runs == [(manifest.complete_run, "success")]


@pytest.mark.parametrize("mutation", ["artifact", "database"])
def test_changed_payload_is_rejected_without_changing_trusted_manifest(
    rehearsal: Path, tmp_path: Path, mutation: str
) -> None:
    backup = rehearsal / "backup"
    trusted = recovery.read_manifest(backup)
    trusted_json = trusted.model_dump_json()
    manifest_bytes = (backup / recovery.MANIFEST_NAME).read_bytes()
    changed = tmp_path / "changed-backup"
    _copy_files(backup, changed, (*trusted.files, recovery.MANIFEST_NAME))
    _tamper(changed, mutation, trusted)
    with pytest.raises(recovery.RehearsalError):
        recovery.restore_fixture(changed, tmp_path / "rejected-restore", trusted)

    restored = tmp_path / "changed-restore"
    recovery.restore_fixture(backup, restored, trusted)
    _tamper(restored, mutation, trusted)
    with pytest.raises(recovery.RehearsalError):
        recovery.verify_fixture(restored, trusted)
    assert trusted.model_dump_json() == trusted_json
    assert (backup / recovery.MANIFEST_NAME).read_bytes() == manifest_bytes
    assert (changed / recovery.MANIFEST_NAME).read_bytes() == manifest_bytes


def test_second_database_failure_does_not_publish_manifest(
    rehearsal: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = rehearsal / "source"
    trusted = recovery.read_manifest(rehearsal / "backup")
    before = _stamps(source, trusted.files)
    destination = tmp_path / "incomplete-backup"
    backup_database = recovery.backup_database
    calls: list[Path] = []

    def fail_second_database(source_db: Path, destination_db: Path) -> None:
        calls.append(source_db)
        if len(calls) == 2:
            reason = "synthetic second database backup failure"
            raise OSError(reason)
        backup_database(source_db, destination_db)

    monkeypatch.setattr(recovery, "backup_database", fail_second_database)
    with pytest.raises(OSError, match="synthetic second"):
        recovery.backup_fixture(source, destination, trusted)
    assert len(calls) == 2
    assert not (destination / recovery.MANIFEST_NAME).exists()
    assert _stamps(source, trusted.files) == before


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_existing_destination_is_rejected_without_overwriting(
    rehearsal: Path, tmp_path: Path, operation: str
) -> None:
    trusted = recovery.read_manifest(rehearsal / "backup")
    destination = tmp_path / "existing"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_bytes(b"synthetic existing destination\n")
    before = sentinel.read_bytes()
    action = recovery.backup_fixture if operation == "backup" else recovery.restore_fixture
    source = rehearsal / ("source" if operation == "backup" else "backup")
    with pytest.raises(recovery.RehearsalError):
        action(source, destination, trusted)
    assert sentinel.read_bytes() == before
    assert not (destination / recovery.MANIFEST_NAME).exists()


@pytest.mark.parametrize(
    ("bad_key", "redirect_flag", "reason"),
    [
        ("../outside", None, "unexpected-file-path"),
        (".AICMO/WEB.SQLITE3", None, "duplicate-or-large-file-set"),
        (None, "is_symlink", "redirect-path"),
        (None, "is_junction", "redirect-path"),
    ],
)
def test_unsafe_manifest_or_redirect_is_rejected_before_copying(
    rehearsal: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_key: str | None,
    redirect_flag: str | None,
    reason: str,
) -> None:
    trusted = recovery.read_manifest(rehearsal / "backup")
    destination = tmp_path / "rejected-backup"
    if bad_key is not None:
        trusted = trusted.model_copy(
            update={"files": {**trusted.files, bad_key: trusted.files[recovery.DB_PATHS[0]]}}
        )
    else:
        assert redirect_flag is not None
        original = getattr(Path, redirect_flag)

        def redirected(path: Path) -> bool:
            return path == native_io_path(tmp_path) or bool(original(path))

        # Exercise both filesystem redirect indicators without Windows symlink privileges.
        monkeypatch.setattr(Path, redirect_flag, redirected)
    with pytest.raises(recovery.RehearsalError, match=reason):
        recovery.backup_fixture(rehearsal / "source", destination, trusted)
    assert not destination.exists()


def test_missing_reference_does_not_publish_manifest(rehearsal: Path, tmp_path: Path) -> None:
    trusted = recovery.read_manifest(rehearsal / "backup")
    source = tmp_path / "incomplete-source"
    _copy_files(
        rehearsal / "source",
        source,
        (relative for relative in trusted.files if relative != "agents/reviewer.md"),
    )
    destination = tmp_path / "rejected-backup"
    with pytest.raises(recovery.RehearsalError, match="missing-file"):
        recovery.backup_fixture(source, destination, trusted)
    assert not (destination / recovery.MANIFEST_NAME).exists()
    assert not destination.exists()


def test_failed_restore_verification_does_not_publish_manifest(
    rehearsal: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backup = rehearsal / "backup"
    trusted = recovery.read_manifest(backup)
    names = (*trusted.files, recovery.MANIFEST_NAME)
    before = _stamps(backup, names)
    destination = tmp_path / "unverified-restore"

    def fail_verification(*_args: object, **_kwargs: object) -> dict[str, object]:
        reason = "synthetic-reference-failure"
        raise recovery.RehearsalError(reason)

    monkeypatch.setattr(recovery, "verify_fixture", fail_verification)
    with pytest.raises(recovery.RehearsalError, match="synthetic-reference-failure"):
        recovery.restore_fixture(backup, destination, trusted)
    assert not (destination / recovery.MANIFEST_NAME).exists()
    assert _stamps(backup, names) == before


def test_post_backup_wal_is_rejected_with_unchanged_database_body(
    rehearsal: Path, tmp_path: Path
) -> None:
    backup = rehearsal / "backup"
    trusted = recovery.read_manifest(backup)
    names = (*trusted.files, recovery.MANIFEST_NAME)
    before = _stamps(backup, names)
    changed = tmp_path / "wal-backup"
    _copy_files(backup, changed, names)
    database = changed / recovery.DB_PATHS[1]
    destination = tmp_path / "rejected-restore"
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True)) as writer:
        assert writer.execute("pragma journal_mode=wal").fetchone() == ("wal",)
        writer.execute("pragma wal_autocheckpoint=0")
        updated = writer.execute(
            "update events set message=? where event_id=(select min(event_id) from events)",
            ("synthetic post-backup WAL change",),
        )
        assert updated.rowcount == 1
        writer.commit()
        assert (database.parent / f"{database.name}-wal").stat().st_size > 32
        assert _stamps(changed, names) == before
        with pytest.raises(recovery.RehearsalError, match=r"^untrusted-wal$"):
            recovery.verify_fixture(changed, trusted)
        with pytest.raises(recovery.RehearsalError, match=r"^untrusted-wal$"):
            recovery.restore_fixture(changed, destination, trusted)
        assert not destination.exists()
    assert _stamps(backup, names) == before
