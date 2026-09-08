from __future__ import annotations

# Django owns isolation; these tests use the real verifier and synthetic engine adapters.
# ruff: noqa: PT009
# pyright: reportUninitializedInstanceVariable=false
import hashlib
import json
import re
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth.models import User
from django.test import TransactionTestCase, override_settings

from aicmo.photos import normalize_photo
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.store_app import delivery, photos, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, PublicationReport, Store
from tests.store_photo_cases import upload
from tests.test_delivery_manifest import PassReviewer
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _content,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


class DeliveryTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("delivery-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        configure_quota(self.runner.store, "shop", current_period(), 3, 6)

    def tick(self) -> None:
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            self.assertTrue(run_one())

    def complete(self, *, photo: bool = False) -> Job:
        manifest = (
            photos.store_photo(
                self.store, normalize_photo(upload().read()), "가게 사진", "own_photo"
            )
            if photo
            else None
        )
        job = services.submit(
            self.store, uuid.uuid4(), _brief()["brief_json"], manifest, actor=self.owner
        )
        self.tick()
        job.refresh_from_db()
        _, pack_sha, photo_sha = services.preview(job)
        self.assertEqual(
            self.client.post(
                f"/jobs/{job.id}/approve/",
                {"pack_sha": pack_sha, "photo_sha": photo_sha, "checked": "on"},
            ).status_code,
            302,
        )
        self.tick()
        job.refresh_from_db()
        return job

    def file_hashes(self) -> dict[str, str]:
        # WAL readers may create coordination sidecars; compare durable files and SQL below.
        sidecars = {
            self.runner.store.db_path.with_name(f"runs.sqlite3{suffix}")
            for suffix in ("-shm", "-wal")
        }
        return {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*")
            if path.is_file() and path not in sidecars
        }

    def engine_rows(self) -> tuple[str, ...]:
        with services.reader().store.connect() as connection:
            return tuple(connection.iterdump())

    def test_verified_cards_equal_zip_get_is_readonly_and_photo_stays_authorized(self) -> None:
        job = self.complete(photo=True)
        self.assertEqual(job.state, "success")
        usage = quota_status(self.runner.store, "shop", current_period())
        rows = self.engine_rows()
        before = self.file_hashes()
        for _ in range(2):
            response = self.client.get(f"/jobs/{job.id}/delivery/")
            self.assertContains(response, "승인 문안 복사")
            self.assertContains(response, f"/jobs/{job.id}/photo/")
            self.assertContains(response, 'rel="noopener noreferrer"')
            self.assertContains(response, 'href="https://smartplace.naver.com/"')
            self.assertIn("no-store", response["Cache-Control"])
        current = delivery.snapshot(job)
        self.assertEqual(self.file_hashes(), before)
        self.assertEqual(self.engine_rows(), rows)
        self.assertFalse((self.root / f"artifacts/{job.run_id}/exports").exists())
        self.assertEqual(PublicationReport.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), usage)
        path = services.download(job)
        self.assertEqual(services.download(job), path)
        with ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(current.bundle_sha, manifest["bundle_sha256"])
            self.assertEqual(manifest["external_publish_status"], "not_published")
            for card in current.cards:
                raw = archive.read(card.key + ".txt")
                self.assertEqual(card.text.encode("utf-8"), raw)
                self.assertEqual(card.file_sha, hashlib.sha256(raw).hexdigest())
            self.assertEqual(current.cards[0].photo_filename, "photos/news-1.png")
            self.assertEqual(
                self.client.get(f"/jobs/{job.id}/photo/").content, archive.read("photos/news-1.png")
            )
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), usage)
        self.assertEqual(PublicationReport.objects.count(), 0)
        other = User.objects.create_user("delivery-other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 404)
        self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 302)

    def test_unapproved_warn_and_forged_web_success_never_expose_cards(self) -> None:
        job = services.submit(self.store, uuid.uuid4(), _brief()["brief_json"], actor=self.owner)
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 409)
        self.tick()
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 409)
        Job.objects.filter(pk=job.pk).update(state="success")
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 409)
        # Finish this source with an actual terminal WARN, then forge only the web state.
        Job.objects.filter(pk=job.pk).update(state="waiting_approval")
        job.refresh_from_db()
        _, pack_sha, photo_sha = services.preview(job)
        self.client.post(
            f"/jobs/{job.id}/approve/",
            {"pack_sha": pack_sha, "photo_sha": photo_sha, "checked": "on"},
        )
        self.runner = replace(self.runner, review_adapter=PassReviewer("WARN"))
        self.tick()
        job.refresh_from_db()
        self.assertEqual(job.state, "needs_work")
        Job.objects.filter(pk=job.pk).update(state="success")
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 409)
        self.assertEqual(PublicationReport.objects.count(), 0)
        self.assertFalse((self.root / f"artifacts/{job.run_id}/exports").exists())

    def test_current_inputs_and_artifact_tampering_close_delivery(self) -> None:
        job = self.complete()
        original_inputs = job.inputs
        Job.objects.filter(pk=job.pk).update(
            inputs={**original_inputs, "brief_json": _brief(minutes=5)["brief_json"]}
        )
        self.assertEqual(self.client.get(f"/jobs/{job.id}/delivery/").status_code, 404)
        self.assertEqual(self.client.post(f"/jobs/{job.id}/download/").status_code, 404)
        Job.objects.filter(pk=job.pk).update(inputs=original_inputs)
        source = self.root / f"artifacts/{job.run_id}/local-pack.json"
        source.write_bytes(source.read_bytes() + b" ")
        response = self.client.get(f"/jobs/{job.id}/delivery/")
        self.assertContains(response, "승인된 결과를 확인할 수 없습니다", status_code=409)
        self.assertNotContains(response, "copy-data-", status_code=409)
        self.assertFalse((self.root / f"artifacts/{job.run_id}/exports").exists())

    def test_markup_is_plain_text_and_clipboard_json_preserves_crlf(self) -> None:
        pack = json.loads(_content(_brief()))
        raw = (
            "안내 첫 줄\r\n</textarea><script>window.syntheticMarker = true</script>"
            "& <b>둘째 줄</b>"
        )
        pack["news"][0]["body"] = raw
        self.runner = replace(
            self.runner, adapter=PackAdapter(override=json.dumps(pack, ensure_ascii=False))
        )
        job = self.complete()
        self.assertEqual(job.state, "success")
        response = self.client.get(f"/jobs/{job.id}/delivery/")
        html = response.content.decode()
        self.assertContains(response, "&lt;/textarea&gt;&lt;script&gt;")
        self.assertNotIn("<script>window.syntheticMarker", html)
        data = re.findall(
            r'<script id="copy-data-([^"]+)" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        cards = {card.key: card for card in delivery.snapshot(job).cards}
        self.assertEqual(len(data), len(cards))
        for key, serialized in data:
            copied = json.loads(serialized)
            self.assertEqual(copied, cards[key].text)
            self.assertEqual(hashlib.sha256(copied.encode()).hexdigest(), cards[key].file_sha)
        self.assertIn(raw, cards["news-1"].text)
        self.assertContains(response, "readonly")
        self.assertContains(response, ".copy-button[hidden]{display:none}")
        self.assertContains(response, "직접 복사하세요")
        self.assertEqual(self.client.post(f"/jobs/{job.id}/delivery/").status_code, 405)
