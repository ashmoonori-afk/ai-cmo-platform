"""Explicit development-only rehearsal; creates its own stopped synthetic source.

Run with ``uv run python -m scripts.rehearse_store_recovery --output NEW_DIRECTORY``.
Requires the repository's development dependencies and existing repository test helpers.
Never accepts a source database, starts a service, or restores over existing data.
The runtime digest covers core Python, Store model/migrations, selected synthetic
helpers and this script, not the whole app. This no-photo local-pack fixture has no
source_url/source-manifest. Operational H, full G26 and G02 remain OPEN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from aicmo.errors import AicmoError
from aicmo.export import verified_pack
from aicmo.local_pack import unique_json_pairs
from aicmo.paths import native_io_path
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore

REPO = Path(__file__).resolve().parents[1]
DB_PATHS = (".aicmo/web.sqlite3", ".aicmo/runs.sqlite3")
MANIFEST_NAME = "recovery-manifest.json"
MAX_FILES = 64
JOB_COUNT = 2
SYNTHETIC_SECRET = "synthetic-rehearsal-only-never-deploy"
REFERENCE_FILES = (
    "workflows/local-store-pack.workflow.yaml",
    "playbooks/09-local/local-store-pack.md",
    "agents/copywriter.md",
    "agents/reporter.md",
    "agents/reviewer.md",
    "prompts/shared/gate-check.md",
    "prompts/shared/deliverable-standard.md",
    *(
        f"clients/shop/{name}.md"
        for name in (
            "config",
            "brand-guidelines",
            "pricing-rules",
            "copy-patterns",
        )
    ),
)
OUTPUT_NAMES = (
    "context.md",
    "learning-context.json",
    "photos.json",
    "local-pack.json",
    "owner-approval.json",
    "delivery-review.json",
)


class RehearsalError(ValueError):
    """Only fixed diagnostic codes are emitted by the development entry point."""


class FileStamp(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    size: int = Field(ge=0, le=4 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal["aicmo.synthetic-recovery.v1"] = "aicmo.synthetic-recovery.v1"
    fixture_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    runtime_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete_run: str = Field(pattern=r"^web-[0-9a-f]{32}$")
    queued_run: str = Field(pattern=r"^web-[0-9a-f]{32}$")
    schema_sha256: dict[str, str]
    files: dict[str, FileStamp]


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RehearsalError(reason)


def runtime_digest() -> str:
    # Hash repository code only, never discover customer or existing fixture files.
    sources = [
        *sorted((REPO / "src/aicmo").glob("*.py")),
        REPO / "src/aicmo/store_app/models.py",
        *sorted((REPO / "src/aicmo/store_app/migrations").glob("*.py")),
        REPO / "tests/test_local_pack.py",
        REPO / "tests/test_delivery_manifest.py",
        REPO / "tests/conftest.py",
        Path(__file__),
    ]
    digest = hashlib.sha256()
    for source in sources:
        digest.update(source.relative_to(REPO).as_posix().encode())
        digest.update(b"\0")
        digest.update(source.read_bytes())
    return digest.hexdigest()


def plain_path(path: Path) -> Path:
    logical = path.absolute()
    for part in (logical, *logical.parents):
        io_part = native_io_path(part)
        require(not io_part.is_symlink() and not io_part.is_junction(), "redirect-path")
    require(logical.resolve() == logical, "redirect-path")
    return logical


def relative_file(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    require(
        bool(name)
        and not relative.is_absolute()
        and relative.as_posix() == name
        and ".." not in relative.parts
        and "\\" not in name
        and ":" not in name,
        "invalid-relative-path",
    )
    target = plain_path(root / name)
    require(target.is_relative_to(plain_path(root)), "outside-root")
    return native_io_path(target)


def separate(source: Path, destination: Path) -> tuple[Path, Path]:
    source, destination = plain_path(source), plain_path(destination)
    require(
        not source.is_relative_to(destination) and not destination.is_relative_to(source),
        "overlapping-roots",
    )
    require(not native_io_path(destination).exists(), "existing-destination")
    return source, destination


def stamp(path: Path) -> FileStamp:
    require(path.is_file(), "missing-file")
    raw = path.read_bytes()
    return FileStamp(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def file_stamps(root: Path, names: tuple[str, ...]) -> dict[str, FileStamp]:
    return {name: stamp(relative_file(root, name)) for name in names}


def sidecars(root: Path, run_id: str) -> dict[str, FileStamp]:
    names = [f"{name}{suffix}" for name in DB_PATHS for suffix in ("-wal", "-shm")]
    names.extend(
        (
            ".aicmo/web-worker.lock",
            f".aicmo/web-run-locks/{hashlib.sha256(run_id.encode()).hexdigest()}.lock",
        )
    )
    return {
        name: stamp(relative_file(root, name))
        for name in names
        if relative_file(root, name).is_file()
    }


def read_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(plain_path(path).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def database_state(path: Path) -> tuple[str, str]:
    with closing(read_database(path)) as connection:
        schema = [
            tuple(row)
            for row in connection.execute(
                "select type,name,tbl_name,sql from sqlite_master order by type,name"
            )
        ]
        schema_raw = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode()
        logical = "\n".join(connection.iterdump()).encode()
    return hashlib.sha256(schema_raw).hexdigest(), hashlib.sha256(logical).hexdigest()


def validate_manifest(manifest: Manifest) -> None:
    names = tuple(manifest.files)
    require(
        len(names) <= MAX_FILES and len({name.casefold() for name in names}) == len(names),
        "duplicate-or-large-file-set",
    )
    required = {
        *REFERENCE_FILES,
        *DB_PATHS,
        *(f"artifacts/{manifest.complete_run}/{name}" for name in OUTPUT_NAMES),
    }
    require(required <= set(names), "incomplete-file-set")
    for name in names:
        require(
            name in required
            or re.fullmatch(r"\.aicmo/snapshots/[0-9a-f]{64}", name) is not None
            or name
            in {
                f"artifacts/{manifest.complete_run}/_pre_edit/artifacts/"
                f"{manifest.complete_run}/{item}"
                for item in OUTPUT_NAMES[:4]
            },
            "unexpected-file-path",
        )
    require(set(manifest.schema_sha256) == set(DB_PATHS), "unsupported-schema-set")
    require(manifest.complete_run != manifest.queued_run, "duplicate-job")
    require(manifest.runtime_sha256 == runtime_digest(), "changed-runtime")


def backup_database(source: Path, destination: Path) -> None:
    with closing(read_database(source)) as reader, closing(sqlite3.connect(destination)) as writer:
        reader.backup(writer)


def manifest_bytes(manifest: Manifest) -> bytes:
    return (manifest.model_dump_json(indent=2) + "\n").encode()


def backup_fixture(source: Path, destination: Path, manifest_template: Manifest) -> Manifest:
    source, destination = separate(source, destination)
    validate_manifest(manifest_template)
    names = tuple(manifest_template.files)
    # Resolve every source before creating a destination or copying any bytes.
    before = file_stamps(source, names)
    logical_before = {name: database_state(source / name) for name in DB_PATHS}
    require(
        {name: value[0] for name, value in logical_before.items()}
        == manifest_template.schema_sha256,
        "changed-source-schema",
    )
    native_io_path(destination).mkdir(parents=True)
    for name in (*DB_PATHS, *(item for item in names if item not in DB_PATHS)):
        target = relative_file(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in DB_PATHS:
            backup_database(source / name, target)
        else:
            target.write_bytes(relative_file(source, name).read_bytes())
    require(file_stamps(source, names) == before, "source-file-changed")
    require(
        {name: database_state(source / name) for name in DB_PATHS} == logical_before,
        "source-database-changed",
    )
    require(
        {name: database_state(destination / name) for name in DB_PATHS} == logical_before,
        "backup-database-differs",
    )
    manifest = manifest_template.model_copy(update={"files": file_stamps(destination, names)})
    # Only this final write marks the newly created staging set complete.
    relative_file(destination, MANIFEST_NAME).write_bytes(manifest_bytes(manifest))
    return manifest


def read_manifest(root: Path) -> Manifest:
    raw = relative_file(root, MANIFEST_NAME).read_bytes()
    require(len(raw) <= 64 * 1024, "large-manifest")
    return Manifest.model_validate(json.loads(raw, object_pairs_hook=unique_json_pairs))


def verify_files(root: Path, trusted: Manifest, *, require_manifest: bool = True) -> None:
    validate_manifest(trusted)
    if require_manifest:
        require(
            relative_file(root, MANIFEST_NAME).read_bytes() == manifest_bytes(trusted),
            "untrusted-manifest",
        )
    # Backup captured committed WAL into the trusted database files. A later nonempty
    # WAL is outside that set; mode=ro would otherwise read its untrusted transactions.
    for name in DB_PATHS:
        wal = relative_file(root, f"{name}-wal")
        require(not wal.exists() or wal.stat().st_size == 0, "untrusted-wal")
    require(file_stamps(root, tuple(trusted.files)) == trusted.files, "file-mismatch")
    allowed = {
        *trusted.files,
        MANIFEST_NAME,
        *(f"{name}{suffix}" for name in DB_PATHS for suffix in ("-wal", "-shm")),
    }
    io_root = native_io_path(plain_path(root))
    for directory, folders, files in os.walk(io_root, followlinks=False):
        for name in (*folders, *files):
            relative = (Path(directory) / name).relative_to(io_root)
            path = plain_path(root / relative)
            if native_io_path(path).is_file():
                require(relative.as_posix() in allowed, "unexpected-file")


def verify_fixture(
    root: Path,
    trusted: Manifest,
    *,
    require_manifest: bool = True,
) -> dict[str, object]:
    root = plain_path(root)
    verify_files(root, trusted, require_manifest=require_manifest)
    before = file_stamps(root, tuple(trusted.files))
    for name in DB_PATHS:
        require(database_state(root / name)[0] == trusted.schema_sha256[name], "schema-mismatch")
        with closing(read_database(root / name)) as connection:
            require(
                connection.execute("pragma integrity_check").fetchone()[0] == "ok",
                "database-integrity",
            )
            require(not connection.execute("pragma foreign_key_check").fetchall(), "database-fk")
    with closing(read_database(root / DB_PATHS[0])) as connection:
        jobs = connection.execute(
            "select j.id,j.state,j.workflow_id,j.inputs,j.cancel_requested,s.client "
            "from store_app_job j join store_app_store s on s.id=j.store_id order by j.state"
        ).fetchall()
        require(len(jobs) == JOB_COUNT, "job-count")
    reader = WorkflowRunner(root, WorkflowStore(root / DB_PATHS[1], read_only=True))
    with reader.store.connect() as connection:
        require(connection.execute("select count(*) from runs").fetchone()[0] == 1, "run-count")
        require(
            connection.execute(
                "select count(*) from runs where run_id=?", (trusted.queued_run,)
            ).fetchone()[0]
            == 0,
            "queued-run-exists",
        )
        snapshots = connection.execute(
            "select source_path,snapshot_path,sha256 from approval_snapshots where run_id=?",
            (trusted.complete_run,),
        ).fetchall()
    for job in jobs:
        run_id = "web-" + str(job["id"])
        require(
            job["workflow_id"] == "local-store-pack"
            and job["client"] == "shop"
            and not job["cancel_requested"],
            "job-context",
        )
        inputs = json.loads(job["inputs"])
        require(inputs.get("client") == job["client"], "job-client")
        if run_id == trusted.complete_run:
            require(
                job["state"] == "success" and reader.store.get_inputs(run_id) == inputs,
                "completed-job-context",
            )
        else:
            require(run_id == trusted.queued_run and job["state"] == "queued", "queued-job-context")
    require(bool(snapshots), "missing-approval-snapshots")
    for row in snapshots:
        for name in (str(row["source_path"]), str(row["snapshot_path"])):
            require(
                name in trusted.files and stamp(relative_file(root, name)).sha256 == row["sha256"],
                "approval-snapshot-mismatch",
            )
    bundle, _files = verified_pack(reader, trusted.complete_run)
    require(file_stamps(root, tuple(trusted.files)) == before, "verification-mutated-files")
    return {"completed_jobs": 1, "queued_jobs": 1, "engine_runs": 1, "bundle_sha256": bundle}


def restore_fixture(backup: Path, destination: Path, trusted: Manifest) -> None:
    backup, destination = separate(backup, destination)
    verify_files(backup, trusted)
    native_io_path(destination).mkdir(parents=True)
    for name in trusted.files:
        target = relative_file(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative_file(backup, name).read_bytes())
    verify_fixture(destination, trusted, require_manifest=False)
    relative_file(destination, MANIFEST_NAME).write_bytes(manifest_bytes(trusted))


def create_fixture(root: Path) -> Manifest:
    # Configure Django only in this explicit, standalone development process.
    import django  # noqa: PLC0415
    from django.conf import settings  # noqa: PLC0415
    from django.core.management import call_command  # noqa: PLC0415
    from django.db import connections  # noqa: PLC0415
    from tests.test_local_pack import (  # noqa: PLC0415
        _brief,  # pyright: ignore[reportPrivateUsage]
        _runner,  # pyright: ignore[reportPrivateUsage]
    )

    require(not settings.configured and not native_io_path(root).exists(), "fixture-must-be-new")
    native_io_path(root).mkdir(parents=True)
    runner = _runner(root)
    native_io_path(root / ".aicmo").mkdir(exist_ok=True)
    settings.configure(
        SECRET_KEY=SYNTHETIC_SECRET,
        INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "aicmo.store_app"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": root / DB_PATHS[0]}},
        REPO_ROOT=root,
        USE_TZ=True,
    )
    django.setup()
    from django.contrib.auth.models import User  # noqa: PLC0415

    from aicmo.quota import configure_quota, current_period  # noqa: PLC0415
    from aicmo.reporter import exclusive_file_lock  # noqa: PLC0415
    from aicmo.store_app import services  # noqa: PLC0415
    from aicmo.store_app.models import Store  # noqa: PLC0415

    try:
        call_command("migrate", verbosity=0, interactive=False)
        owner = User.objects.create_user("synthetic-recovery-owner")
        store = Store.objects.create(owner=owner, name="Synthetic recovery store", client="shop")
        configure_quota(runner.store, "shop", current_period(), 2, 2)
        brief = _brief(photos=False, reviews=0)["brief_json"]
        done = services.submit(store, uuid4(), brief, actor=owner)
        with exclusive_file_lock(root / ".aicmo/web-worker.lock"):
            services.execute(done, runner)
            done.refresh_from_db()
            require(done.state == "waiting_approval", "fixture-awaiting-owner")
            _, pack_sha, photo_sha = services.preview(done)
            services.request_approval(done, pack_sha, photo_sha, owner)
            services.execute(done, runner)
        done.refresh_from_db()
        require(done.state == "success", "fixture-completion")
        queued = services.submit(store, uuid4(), brief, actor=owner)
        files = {
            *REFERENCE_FILES,
            *DB_PATHS,
            *(f"artifacts/{done.run_id}/{name}" for name in OUTPUT_NAMES),
        }
        with runner.store.connect() as connection:
            for row in connection.execute(
                "select source_path,snapshot_path from approval_snapshots where run_id=?",
                (done.run_id,),
            ):
                files.add(str(row["snapshot_path"]))
                files.add(f"artifacts/{done.run_id}/_pre_edit/{row['source_path']}")
        complete_run, queued_run = done.run_id, queued.run_id
    finally:
        connections.close_all()
    return Manifest(
        fixture_id=uuid4().hex,
        runtime_sha256=runtime_digest(),
        complete_run=complete_run,
        queued_run=queued_run,
        schema_sha256={name: database_state(root / name)[0] for name in DB_PATHS},
        files=file_stamps(root, tuple(sorted(files))),
    )


def rehearse(output: Path) -> dict[str, object]:
    output = plain_path(output)
    require(not native_io_path(output).exists(), "existing-output")
    native_io_path(output).mkdir(parents=True)
    source, backup, restored = (output / name for name in ("source", "backup", "restored"))
    template = create_fixture(source)
    before = file_stamps(source, tuple(template.files))
    auxiliary_before = sidecars(source, template.complete_run)
    manifest = backup_fixture(source, backup, template)
    restore_fixture(backup, restored, manifest)
    verification = verify_fixture(restored, manifest)
    after = file_stamps(source, tuple(template.files))
    require(before == after, "source-changed")
    evidence: dict[str, object] = {
        "status": "synthetic-pass",
        "provider": "synthetic-only",
        "operation_scope": "stopped-synthetic-only",
        "fixture_id": manifest.fixture_id,
        "source_before": {key: value.model_dump() for key, value in before.items()},
        "source_after": {key: value.model_dump() for key, value in after.items()},
        "source_sidecars_before": {
            key: value.model_dump() for key, value in auxiliary_before.items()
        },
        "source_sidecars_after": {
            key: value.model_dump()
            for key, value in sidecars(source, template.complete_run).items()
        },
        "verification": verification,
        "remaining": "operational-H, G26-full, G02 remain OPEN",
    }
    relative_file(output, "evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New synthetic rehearsal directory"
    )
    args = parser.parse_args()
    try:
        evidence = rehearse(args.output)
    except RehearsalError as exc:
        print(f"synthetic-rehearsal-failed: {exc}; incomplete directories preserved")
        return 1
    except (AicmoError, OSError, ValueError, sqlite3.Error):
        print("synthetic-rehearsal-failed; incomplete directories preserved")
        return 1
    print(json.dumps({key: evidence[key] for key in ("status", "operation_scope", "fixture_id")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
