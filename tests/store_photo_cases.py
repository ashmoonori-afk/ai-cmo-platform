from __future__ import annotations

# Django owns database isolation; every photo and owner below is synthetic.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import io
import json
import subprocess
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import TransactionTestCase, override_settings
from django.utils.datastructures import MultiValueDict
from PIL import Image

from aicmo.errors import AicmoError
from aicmo.photos import MAX_PHOTO_BYTES, asset_path, normalize_photo, parse_photos
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.store import WorkflowStore
from aicmo.store_app import photos, services
from aicmo.store_app.forms import PackForm
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, Store
from tests.test_local_pack import (
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


def upload() -> SimpleUploadedFile:
    stream = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "PRIVATE_ORIGINAL_METADATA"
    Image.new("RGB", (12, 8), "red").save(stream, format="JPEG", exif=exif)
    return SimpleUploadedFile("private-owner-filename.jpg", stream.getvalue(), "image/jpeg")


class PhotoTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("photo-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        configure_quota(self.runner.store, "shop", current_period(), 2, 4)

    def data(self) -> dict[str, object]:
        return {
            "submission_key": str(uuid.uuid4()),
            "fact": "이번 주 평소대로 영업합니다.",
            "reviews": "",
            "owner_minutes": "20",
            "photo": upload(),
            "photo_caption": "가게 내부의 합성 사진",
            "photo_rights": "own_photo",
            "photo_privacy": "on",
        }

    def tick(self) -> bool:
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            return run_one()

    def test_photo_journey_preview_metadata_idempotency_and_exact_zip(self) -> None:
        data = self.data()
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            response = self.client.post(f"/stores/{self.store.pk}/new/", data)
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get()
        photo = parse_photos(job.inputs).photos[0]
        self.assertEqual((photo.width, photo.height), (8, 12))
        self.assertNotIn("private-owner-filename", json.dumps(job.inputs))
        self.assertEqual(
            services.submit(
                self.store,
                job.submission_key,
                job.inputs["brief_json"],
                job.inputs["photos_json"],
                actor=self.owner,
            ).pk,
            job.pk,
        )
        changed = json.loads(job.inputs["photos_json"])
        changed["photos"][0]["caption"] = "변경한 사진 설명"
        with self.assertRaises(services.StoreActionError):
            services.submit(
                self.store,
                job.submission_key,
                job.inputs["brief_json"],
                json.dumps(changed),
                actor=self.owner,
            )
        response = self.client.get(f"/jobs/{job.id}/photo/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("no-store", response["Cache-Control"])
        pixels = response.content
        self.assertNotIn(b"PRIVATE_ORIGINAL_METADATA", pixels)
        self.assertTrue(self.tick())
        job.refresh_from_db()
        self.assertEqual(job.state, "waiting_approval")
        _, pack_sha, photo_sha = services.preview(job)
        self.assertEqual(
            self.client.post(
                f"/jobs/{job.id}/approve/",
                {"pack_sha": pack_sha, "photo_sha": photo_sha, "checked": "on"},
            ).status_code,
            302,
        )
        self.assertTrue(self.tick())
        job.refresh_from_db()
        self.assertEqual(job.state, "success")
        with ZipFile(services.download(job)) as archive:
            self.assertEqual(archive.read("photos/news-1.png"), pixels)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period())["draft_used"], 1)

    def test_upload_errors_keep_text_and_require_rights_privacy_caption_and_one_file(self) -> None:
        for field in ("photo_caption", "photo_rights", "photo_privacy"):
            data = self.data()
            data[field] = ""
            response = self.client.post(f"/stores/{self.store.pk}/new/", data)
            self.assertContains(response, "이번 주 평소대로 영업합니다.", status_code=400)
            self.assertContains(response, "다시 선택", status_code=400)
        data = self.data()
        data["photo"] = [upload(), upload()]
        self.assertContains(
            self.client.post(f"/stores/{self.store.pk}/new/", data), "1장만", status_code=400
        )
        data = self.data()
        data["unexpected_file"] = upload()
        self.assertEqual(self.client.post(f"/stores/{self.store.pk}/new/", data).status_code, 400)
        animated = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(
            animated,
            format="PNG",
            save_all=True,
            append_images=[Image.new("RGB", (2, 2), "blue")],
        )
        for raw in (b"not-a-photo", b"x" * (MAX_PHOTO_BYTES + 1), animated.getvalue()):
            data = self.data()
            data.pop("photo")
            form = PackForm(data, MultiValueDict({"photo": [SimpleUploadedFile("bad.png", raw)]}))
            self.assertFalse(form.is_valid())
            self.assertIn("photo", form.errors)
        self.assertEqual(Job.objects.count(), 0)

    def test_preview_is_store_bound_and_tampering_fails_before_worker(self) -> None:
        manifest = photos.store_photo(
            self.store, normalize_photo(upload().read()), "가게 사진", "own_photo"
        )
        job = services.submit(
            self.store, uuid.uuid4(), _brief()["brief_json"], manifest, actor=self.owner
        )
        photo = parse_photos(job.inputs).photos[0]
        other = User.objects.create_user("photo-other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 302)
        self.client.force_login(self.owner)
        asset_path(self.root, "shop", photo.sha256).write_bytes(b"tampered")
        self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 404)
        self.assertTrue(self.tick())
        job.refresh_from_db()
        self.assertEqual(job.state, "failed")
        self.assertEqual(quota_status(self.runner.store, "shop", current_period())["draft_used"], 0)

    def test_photo_namespace_junction_never_writes_or_previews_redirected_asset(self) -> None:
        normalized = normalize_photo(upload().read())
        manifest = photos.store_photo(self.store, normalized, "사진", "own_photo")
        job = services.submit(
            self.store, uuid.uuid4(), _brief()["brief_json"], manifest, actor=self.owner
        )
        photo = parse_photos(job.inputs).photos[0]
        target = asset_path(self.root, "shop", photo.sha256).parent
        redirected = self.root / "redirected-photos"
        target.rename(redirected)
        if sys.platform == "win32":
            result = subprocess.run(  # noqa: S603 — fixed command and temporary test paths
                [
                    r"C:\Windows\System32\cmd.exe",
                    "/c",
                    "mklink",
                    "/J",
                    str(target),
                    str(redirected),
                ],
                capture_output=True,
                check=False,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            target.symlink_to(redirected, target_is_directory=True)
        self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 404)
        with self.assertRaises(AicmoError):
            photos.store_photo(self.store, normalized, "새 사진", "own_photo")
        self.assertEqual((redirected / f"{photo.sha256}.png").read_bytes(), normalized[0])

    def test_valid_photo_swap_cannot_change_the_approval_preview(self) -> None:
        manifest = photos.store_photo(
            self.store, normalize_photo(upload().read()), "원래 사진", "own_photo"
        )
        job = services.submit(
            self.store, uuid.uuid4(), _brief()["brief_json"], manifest, actor=self.owner
        )
        self.assertTrue(self.tick())
        job.refresh_from_db()
        _, pack_sha, photo_sha = services.preview(job)
        alternate = io.BytesIO()
        Image.new("RGB", (12, 8), "blue").save(alternate, format="PNG")
        replacement = photos.store_photo(
            self.store, normalize_photo(alternate.getvalue()), "다른 사진", "own_photo"
        )
        Job.objects.filter(pk=job.pk).update(inputs={**job.inputs, "photos_json": replacement})
        self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 404)
        detail = self.client.get(f"/jobs/{job.id}/")
        self.assertContains(detail, "내용을 확인할 수 없습니다.")
        self.assertNotContains(detail, "확인하고 최종 검토 요청")
        self.assertEqual(
            self.client.post(
                f"/jobs/{job.id}/approve/",
                {"pack_sha": pack_sha, "photo_sha": photo_sha, "checked": "on"},
            ).status_code,
            409,
        )
        job.refresh_from_db()
        self.assertEqual(job.state, "waiting_approval")
        self.assertEqual(job.approval, {})
        self.assertFalse(self.tick())

    def test_pre_run_preview_does_not_create_missing_engine_database(self) -> None:
        manifest = photos.store_photo(
            self.store, normalize_photo(upload().read()), "사진", "own_photo"
        )
        job = services.submit(
            self.store, uuid.uuid4(), _brief()["brief_json"], manifest, actor=self.owner
        )
        missing = self.root / "missing-runs.sqlite3"
        reader = replace(self.runner, store=WorkflowStore(missing, read_only=True))
        with patch("aicmo.store_app.photos.services.reader", return_value=reader):
            self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 200)
            self.assertFalse(missing.exists())
            Job.objects.filter(pk=job.pk).update(state="waiting_approval")
            self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 404)
            Job.objects.filter(pk=job.pk).update(state="queued")
            missing.write_bytes(b"invalid-database")
            self.assertEqual(self.client.get(f"/jobs/{job.id}/photo/").status_code, 404)

    def test_bound_inputs_never_reflect_secrets_controls_or_oversized_prose(self) -> None:
        secret = "sk-syntheticPrivateCredential123456789"
        for field in ("fact", "reviews", "photo_caption"):
            for value in (secret, "bad\u202econtrol", "x" * 6001):
                data = self.data()
                data[field] = value
                data["photo"] = SimpleUploadedFile("broken.png", b"not-an-image")
                response = self.client.post(f"/stores/{self.store.pk}/new/", data)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(value, response.content.decode())
                self.assertContains(response, "입력 길이·형식·개인정보", status_code=400)
                if field != "fact":
                    self.assertContains(response, "이번 주 평소대로 영업합니다.", status_code=400)
        data = self.data()
        data["fact"] = secret
        with patch("aicmo.store_app.services.engine") as engine:
            response = self.client.post(f"/stores/{self.store.pk}/new/", data)
        self.assertEqual(response.status_code, 400)
        engine.assert_not_called()
        self.assertEqual(Job.objects.count(), 0)

    def test_bound_pii_is_minimized_on_service_failure_and_metadata_stays_exact(self) -> None:
        data = self.data()
        data["submission_key"] = "aaaaaaaa-aaaa-aaaa-aaaa-a01012345678"
        for field in ("fact", "reviews", "photo_caption"):
            data[field] = "안내 고객 연락 01012345678 synthetic@example.com"
        with patch("aicmo.store_app.services.engine", side_effect=services.StoreActionError):
            response = self.client.post(f"/stores/{self.store.pk}/new/", data)
        self.assertContains(response, str(data["submission_key"]), status_code=400)
        self.assertNotContains(response, "synthetic@example.com", status_code=400)
        self.assertContains(response, "[customer-phone]", status_code=400)
        self.assertContains(response, "[customer-email]", status_code=400)
        self.assertEqual(response.content.decode().count("01012345678"), 1)

    def test_unknown_and_duplicate_text_rejected_without_losing_safe_fields(self) -> None:
        data = self.data()
        data.pop("photo")
        for invalid in ("unknown", "duplicate"):
            post = QueryDict(mutable=True)
            post.update({name: str(value) for name, value in data.items()})
            if invalid == "unknown":
                post["client"] = "sk-secretSyntheticUnknown"
            else:
                post.appendlist("fact", "sk-secretSyntheticDuplicate")
            form = PackForm(post)
            self.assertFalse(form.is_valid())
            self.assertNotIn("sk-secret", form.as_p())
            self.assertIn("가게 내부의 합성 사진", form.as_p())
