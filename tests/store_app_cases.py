from __future__ import annotations

# Django's runner owns setUp and unittest assertions; passwords below are synthetic fixtures.
# ruff: noqa: PT009, PT027, S106
# pyright: reportUninitializedInstanceVariable=false
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth.models import Permission, User
from django.db import close_old_connections, connection
from django.http import FileResponse  # noqa: TC002 — runtime response assertion
from django.test import Client, TransactionTestCase, override_settings

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.quota import configure_quota, current_period, run_quota_status
from aicmo.store import WorkflowStore
from aicmo.store_app import services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, LoginWindow, Store
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _content,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


class StoreAppTests(TransactionTestCase):
    def setUp(self) -> None:
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.runner = _runner(self.root)
        self.setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        self.setting.enable()
        self.addCleanup(self.setting.disable)
        self.owner = User.objects.create_user("owner", password="synthetic-long-password")
        self.other = User.objects.create_user("other", password="synthetic-other-password")
        self.store = Store.objects.create(owner=self.owner, name="동네 가게", client="shop")
        self.client.force_login(self.owner)

    def submit(self) -> Job:
        return services.submit(self.store, uuid.uuid4(), _brief()["brief_json"])

    def tick(self) -> bool:
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            return run_one()

    def approve(self, job: Job) -> None:
        _, pack_sha, photo_sha = services.preview(job)
        result = self.client.post(
            f"/jobs/{job.id}/approve/",
            {
                "pack_sha": pack_sha,
                "photo_sha": photo_sha,
                "checked": "on",
            },
        )
        self.assertEqual(result.status_code, 302)

    def test_journey_and_verified_download(self) -> None:
        fields = {
            "submission_key": str(uuid.uuid4()),
            "fact": "이번 주 평소대로 영업합니다.",
            "reviews": "친절한 안내가 좋았습니다.",
            "owner_minutes": "20",
        }
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            rejected = self.client.post(
                f"/stores/{self.store.pk}/new/",
                {**fields, "client": "another-store", "executor": "not-trusted"},
            )
            self.assertEqual(rejected.status_code, 400)
            self.assertFalse(Job.objects.exists())
            result = self.client.post(
                f"/stores/{self.store.pk}/new/",
                fields,
            )
        self.assertEqual(result.status_code, 302)
        job = Job.objects.get()
        self.assertEqual(job.inputs["client"], "shop")
        self.assertNotIn("executor", job.inputs)
        self.assertEqual(job.state, "queued")
        self.assertTrue(self.tick())
        job.refresh_from_db()
        self.assertEqual(job.state, "waiting_approval")
        self.assertContains(self.client.get(f"/jobs/{job.id}/"), "평소대로")
        self.approve(job)
        self.assertTrue(self.tick())
        job.refresh_from_db()
        self.assertEqual(job.state, "success")
        response = self.client.post(f"/jobs/{job.id}/download/")
        self.assertEqual(response.status_code, 200)
        payload = b"".join(
            cast(
                "Iterable[bytes]", cast("FileResponse", cast("object", response)).streaming_content
            )
        )
        response.close()
        with ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
        # A same-store Job with different facts must not expose the old approved files.
        original_inputs = job.inputs
        job.inputs = {**job.inputs, "brief_json": _brief(minutes=5)["brief_json"]}
        job.save(update_fields=["inputs"])
        self.assertEqual(self.client.post(f"/jobs/{job.id}/download/").status_code, 404)
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 404)
        job.inputs = original_inputs
        job.save(update_fields=["inputs"])

    def test_other_store_and_unauthenticated_access(self) -> None:
        job = self.submit()
        self.client.force_login(self.other)
        for suffix in ("", "approve/", "cancel/", "download/"):
            response = (
                self.client.get(f"/jobs/{job.id}/")
                if not suffix
                else self.client.post(f"/jobs/{job.id}/{suffix}")
            )
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(f"/stores/{self.store.pk}/new/").status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(f"/jobs/{job.id}/").status_code, 302)

    def test_csrf_and_post_only_actions(self) -> None:
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        job = self.submit()
        for suffix in ("approve", "cancel", "download"):
            self.assertEqual(client.post(f"/jobs/{job.id}/{suffix}/").status_code, 403)
            self.assertEqual(client.get(f"/jobs/{job.id}/{suffix}/").status_code, 405)

    def test_operator_permission_is_explicit(self) -> None:
        self.other.is_staff = True
        self.other.save()
        self.assertFalse(services.allowed_stores(self.other).exists())
        self.other.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(codename="operate_stores")
        )
        self.assertTrue(services.allowed_stores(User.objects.get(pk=self.other.pk)).exists())

    def test_same_submission_is_idempotent_and_conflicts_rejected(self) -> None:
        key = uuid.uuid4()
        first = services.submit(self.store, key, _brief()["brief_json"])
        self.assertEqual(first.pk, services.submit(self.store, key, _brief()["brief_json"]).pk)
        with self.assertRaises(services.StoreActionError):
            services.submit(self.store, key, _brief(minutes=5)["brief_json"])
        with self.assertRaises(services.StoreActionError):
            self.submit()

    def test_concurrent_submit(self) -> None:
        key = uuid.uuid4()

        def send(_index: int) -> uuid.UUID:
            close_old_connections()
            try:
                return services.submit(self.store, key, _brief()["brief_json"]).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(send, range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Job.objects.count(), 1)

    def test_cancel_before_start_and_during_generation(self) -> None:
        job = self.submit()
        services.request_cancel(job)
        self.tick()
        job.refresh_from_db()
        self.assertEqual(job.state, "cancelled")
        self.assertFalse(job.cancel_requested)
        second = self.submit()
        original = PackAdapter.generate

        def generate(adapter: PackAdapter, request: AgentRequest) -> AgentResult:
            services.request_cancel(second)
            return original(adapter, request)

        with patch.object(PackAdapter, "generate", generate):
            self.tick()
        second.refresh_from_db()
        self.assertEqual(second.state, "cancelled")

    def test_recovery_after_engine_approval_and_success_wins_cancel(self) -> None:
        job = self.submit()
        self.tick()
        job.refresh_from_db()
        self.approve(job)
        job.refresh_from_db()
        self.runner.approve(job.run_id, "owner_gate", job.approval["reviewer"], "synthetic crash")
        Job.objects.filter(pk=job.pk).update(state="running")
        self.assertTrue(self.tick())
        Job.objects.filter(pk=job.pk).update(state="running", cancel_requested=True)
        self.assertTrue(self.tick())
        job.refresh_from_db()
        self.assertEqual(job.state, "success")
        self.assertFalse(job.cancel_requested)

    def test_stale_approval_and_corrupt_job_are_closed(self) -> None:
        job = self.submit()
        self.tick()
        job.refresh_from_db()
        _, _, photo_sha = services.preview(job)
        result = self.client.post(
            f"/jobs/{job.id}/approve/",
            {
                "pack_sha": "a" * 64,
                "photo_sha": photo_sha,
                "checked": "on",
            },
        )
        self.assertEqual(result.status_code, 409)
        Job.objects.filter(pk=job.pk).update(state="queued", approval=["broken"])
        self.tick()
        job.refresh_from_db()
        self.assertEqual(job.state, "failed")
        self.assertNotIn("broken", job.notice)

    def test_login_throttle_and_session_revocation(self) -> None:
        client = Client()
        for _ in range(7):
            self.assertTrue(client.login(username="owner", password="synthetic-long-password"))
            client.logout()
        for _ in range(5):
            self.assertFalse(client.login(username="owner", password="wrong"))
        self.assertFalse(client.login(username="owner", password="synthetic-long-password"))
        self.assertTrue(
            all(len(key) == 64 for key in LoginWindow.objects.values_list("key", flat=True))
        )
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_cancel_and_empty_worker_without_provider_configuration(self) -> None:
        with patch("aicmo.store_app.management.commands.work.engine", side_effect=AssertionError):
            self.assertFalse(run_one())
            job = self.submit()
            services.request_cancel(job)
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertEqual(job.state, "cancelled")

    def test_cancel_recovers_crash_before_completion_without_provider(self) -> None:
        configure_quota(self.runner.store, "shop", current_period(), 1, 1)
        job = self.submit()
        self.tick()
        self.approve(job)
        with (
            patch.object(
                WorkflowStore, "mark_run_success", side_effect=RuntimeError("synthetic crash")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.tick()
        self.assertEqual(self.runner.store.get_run(job.run_id)["status"], "running")
        self.assertEqual(
            (run_quota_status(self.runner.store, job.run_id) or {})["state"], "reserved"
        )
        self.assertTrue(
            all(row["status"] == "success" for row in self.runner.store.list_steps(job.run_id))
        )
        services.request_cancel(job)
        with patch("aicmo.store_app.management.commands.work.engine", side_effect=AssertionError):
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertEqual(job.state, "success")
        self.assertFalse(job.cancel_requested)
        self.assertEqual(self.runner.store.get_run(job.run_id)["status"], "success")
        self.assertEqual(
            (run_quota_status(self.runner.store, job.run_id) or {})["state"], "consumed"
        )
        self.assertFalse(run_one())

    def test_preview_uses_read_only_engine_connection(self) -> None:
        job = self.submit()
        self.tick()
        with (
            services.reader().store.connect() as connection,
            self.assertRaises(sqlite3.OperationalError),
        ):
            connection.execute("delete from runs")
        with patch("aicmo.store_app.services.WorkflowStore.initialize", side_effect=AssertionError):
            self.assertContains(self.client.get(f"/jobs/{job.id}/"), "사장님 확인")

    def test_fresh_lease_is_not_reclaimed(self) -> None:
        job = self.submit()
        self.tick()
        with self.runner.store.connect() as connection:
            connection.execute(
                "update steps set status='running', locked_by='synthetic-foreign-worker', "
                "locked_at=current_timestamp where run_id=? and step_id='drafts'",
                (job.run_id,),
            )
        Job.objects.filter(pk=job.pk).update(state="running")
        self.assertFalse(self.tick())
        with self.runner.store.connect() as connection:
            connection.execute(
                "update steps set locked_at='2000-01-01 00:00:00' where run_id=?", (job.run_id,)
            )
        self.assertTrue(self.tick())
        job.refresh_from_db()
        self.assertEqual(job.state, "waiting_approval")

    def test_two_worker_processes_generate_once(self) -> None:
        job = self.submit()
        (self.root / "registry").mkdir()
        shutil.copyfile(
            Path(__file__).resolve().parents[1] / "registry/capabilities.yaml",
            self.root / "registry/capabilities.yaml",
        )
        (self.root / "pack.json").write_text(_content(job.inputs), encoding="utf-8")
        script = self.root / "synthetic_generator.py"
        script.write_text(
            "import sys\nfrom pathlib import Path\nsys.stdin.read()\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "root=Path(__file__).parent\n"
            "with (root/'calls.txt').open('a') as f: f.write('called\\n')\n"
            "print((root/'pack.json').read_text(encoding='utf-8'))\n",
            encoding="utf-8",
        )
        command = json.dumps([sys.executable, str(script)])
        env = {
            **os.environ,
            "AICMO_REPO": str(self.root),
            "AICMO_TEST_DB": str(connection.settings_dict["NAME"]),
            "AICMO_WEB_EXECUTOR_CMD": command,
            "AICMO_WEB_REVIEW_CMD": command,
        }
        children: list[subprocess.Popen[bytes]] = []
        try:
            for _ in range(2):
                children.append(  # noqa: PERF401 — retain each child for cleanup if spawning fails
                    subprocess.Popen(
                        [sys.executable, "-m", "tests.run_store_app_tests", "--worker"],
                        env=env,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                )
            for child in children:
                self.assertEqual(child.wait(timeout=45), 0)
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)
        self.assertEqual((self.root / "calls.txt").read_text().splitlines(), ["called"])
        job.refresh_from_db()
        self.assertEqual(job.state, "waiting_approval")
