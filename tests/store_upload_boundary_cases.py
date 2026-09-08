from __future__ import annotations

# Django owns database isolation; all owners and files below are synthetic.
# ruff: noqa: PT009
# pyright: reportUninitializedInstanceVariable=false
import io
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import BadRequest
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.test import Client, RequestFactory, TransactionTestCase, override_settings
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from PIL import Image

from aicmo.outcomes import MAX_CSV_BYTES
from aicmo.photos import MAX_PHOTO_BYTES, parse_photos
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.store_app import uploads
from aicmo.store_app.models import Job, Store
from tests.test_local_pack import _runner  # pyright: ignore[reportPrivateUsage]


def photo() -> SimpleUploadedFile:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(output, format="JPEG")
    return SimpleUploadedFile("synthetic-photo.jpg", output.getvalue(), "image/jpeg")


class UploadBoundaryTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.uploads = self.root / "uploads"
        self.uploads.mkdir()
        self.runner = _runner(self.root)
        setting = override_settings(
            REPO_ROOT=self.root,
            ALLOWED_HOSTS=["testserver"],
            FILE_UPLOAD_TEMP_DIR=str(self.uploads),
            FILE_UPLOAD_MAX_MEMORY_SIZE=0,
        )
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("upload-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        configure_quota(self.runner.store, "shop", current_period(), 2, 4)

    def data(self) -> dict[str, object]:
        return {
            "submission_key": str(uuid.uuid4()),
            "fact": "이번 주 평소대로 영업합니다.",
            "reviews": "",
            "owner_minutes": "20",
        }

    def assert_no_work(self) -> None:
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period())["draft_used"], 0)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(list((self.root / ".aicmo/photos").rglob("*.png")), [])

    def test_interrupted_multipart_never_becomes_a_photo_less_job(self) -> None:
        data = self.data()
        data["photo"] = photo()
        body = encode_multipart(BOUNDARY, data)
        body = body.rsplit(b"\r\n--" + BOUNDARY.encode() + b"--", 1)[0][:-128]
        with patch("aicmo.store_app.services.engine", return_value=self.runner) as engine:
            response = self.client.generic(
                "POST", f"/stores/{self.store.pk}/new/", body, content_type=MULTIPART_CONTENT
            )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "1장만", status_code=400)
        engine.assert_not_called()
        self.assert_no_work()

    def test_file_limit_stops_before_excess_bytes_reach_temporary_storage(self) -> None:
        self.assertEqual(MAX_PHOTO_BYTES, 20 * 1024 * 1024)
        self.assertEqual(
            uploads.MAX_PHOTO_BYTES,  # pyright: ignore[reportPrivateLocalImportUsage]
            MAX_PHOTO_BYTES,
        )
        self.assertEqual(settings.DATA_UPLOAD_MAX_NUMBER_FILES, 1)
        self.assertEqual(
            settings.FILE_UPLOAD_HANDLERS, ["aicmo.store_app.uploads.PhotoUploadHandler"]
        )
        limit = 2 * TemporaryFileUploadHandler.chunk_size
        data = self.data()
        data.update(
            photo_caption="합성 가게 사진",
            photo_rights="own_photo",
            photo_privacy="on",
            photo=SimpleUploadedFile(
                "sk-syntheticUploadSecret123456789.jpg",
                photo().read() + b"x" * (limit * 2),
                "image/jpeg",
            ),
        )
        persisted: list[int] = []
        handlers: list[TemporaryFileUploadHandler] = []
        receive = TemporaryFileUploadHandler.receive_data_chunk

        def track_write(handler: TemporaryFileUploadHandler, raw_data: bytes, start: int) -> None:
            receive(handler, raw_data, start)
            persisted.append(handler.file.tell())
            handlers.append(handler)

        with (
            patch.object(uploads, "MAX_PHOTO_BYTES", limit),
            patch.object(TemporaryFileUploadHandler, "receive_data_chunk", track_write),
            patch("aicmo.store_app.services.engine", return_value=self.runner) as engine,
        ):
            response = self.client.post(f"/stores/{self.store.pk}/new/", data)
        self.assertContains(response, "20 MiB", status_code=400)
        self.assertNotContains(response, "sk-syntheticUploadSecret123456789", status_code=400)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(persisted)
        self.assertGreater(max(persisted), 0)
        self.assertLessEqual(max(persisted), limit)
        self.assertTrue(all(handler.file.closed for handler in handlers))
        engine.assert_not_called()
        self.assert_no_work()

    def test_multiple_files_are_rejected_and_completed_file_is_removed(self) -> None:
        data = self.data()
        data["photo"] = [photo(), photo()]
        with patch("aicmo.store_app.services.engine", return_value=self.runner) as engine:
            response = self.client.post(f"/stores/{self.store.pk}/new/", data)
        self.assertContains(response, "1장만", status_code=400)
        engine.assert_not_called()
        self.assert_no_work()

    def test_normal_photo_is_accepted_and_other_bad_requests_stay_generic(self) -> None:
        data = self.data()
        data.update(
            photo=photo(),
            photo_caption="합성 가게 사진",
            photo_rights="own_photo",
            photo_privacy="on",
        )
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            response = self.client.post(f"/stores/{self.store.pk}/new/", data)
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get()
        self.assertEqual(len(parse_photos(job.inputs).photos), 1)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(quota_status(self.runner.store, "shop", current_period())["draft_used"], 0)
        rejected = uploads.upload_bad_request(
            RequestFactory().get("/"), BadRequest("sk-syntheticErrorSecret123456789")
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertNotContains(rejected, "sk-syntheticErrorSecret123456789", status_code=400)
        self.assertNotContains(rejected, "20 MiB", status_code=400)

    def test_invalid_base64_closes_the_active_temporary_file(self) -> None:
        data = self.data()
        data["photo"] = SimpleUploadedFile("synthetic.png", b"a", "image/png")
        body = encode_multipart(BOUNDARY, data).replace(
            b"Content-Type: image/png\r\n",
            b"Content-Type: image/png\r\nContent-Transfer-Encoding: base64\r\n",
        )
        created: list[TemporaryUploadedFile] = []

        def track_file(
            name: str,
            content_type: str,
            size: int,
            charset: str | None,
            content_type_extra: dict[str, bytes] | None = None,
        ) -> TemporaryUploadedFile:
            result = TemporaryUploadedFile(name, content_type, size, charset, content_type_extra)
            created.append(result)
            return result

        with (
            patch("django.core.files.uploadhandler.TemporaryUploadedFile", track_file),
            patch("aicmo.store_app.services.engine", return_value=self.runner) as engine,
        ):
            response = self.client.generic(
                "POST", f"/stores/{self.store.pk}/new/", body, content_type=MULTIPART_CONTENT
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].closed)
        engine.assert_not_called()
        self.assert_no_work()

    def test_stream_read_error_closes_the_active_temporary_file(self) -> None:
        class BrokenStream(io.BytesIO):
            def read(self, size: int | None = -1) -> bytes:
                if self.tell() >= 2 * TemporaryFileUploadHandler.chunk_size:
                    reason = "synthetic upload read interruption"
                    raise OSError(reason)
                return super().read(size)

        data = self.data()
        data["photo"] = SimpleUploadedFile("synthetic.png", b"x" * (256 * 1024), "image/png")
        body = encode_multipart(BOUNDARY, data)
        client = Client(raise_request_exception=False)
        client.force_login(self.owner)
        written: list[TemporaryFileUploadHandler] = []
        receive = TemporaryFileUploadHandler.receive_data_chunk

        def track_write(handler: TemporaryFileUploadHandler, raw_data: bytes, start: int) -> None:
            receive(handler, raw_data, start)
            written.append(handler)

        with (
            patch.object(TemporaryFileUploadHandler, "receive_data_chunk", track_write),
            patch("aicmo.store_app.services.engine", return_value=self.runner) as engine,
        ):
            response = client.request(
                REQUEST_METHOD="POST",
                PATH_INFO=f"/stores/{self.store.pk}/new/",
                CONTENT_TYPE=MULTIPART_CONTENT,
                CONTENT_LENGTH=str(len(body)),
                **{"wsgi.input": BrokenStream(body)},
            )
        self.assertEqual(response.status_code, 500)
        self.assertNotContains(response, "synthetic upload read interruption", status_code=500)
        self.assertTrue(written)
        self.assertTrue(all(handler.file.closed for handler in written))
        engine.assert_not_called()
        self.assert_no_work()

    def test_csv_route_enforces_32_kib_before_temporary_write(self) -> None:
        self.assertEqual(MAX_CSV_BYTES, 32 * 1024)
        persisted: list[int] = []
        receive = TemporaryFileUploadHandler.receive_data_chunk

        def track_write(handler: TemporaryFileUploadHandler, raw_data: bytes, start: int) -> None:
            receive(handler, raw_data, start)
            persisted.append(handler.file.tell())

        with (
            patch.object(uploads.PhotoUploadHandler, "chunk_size", 8 * 1024),
            patch.object(TemporaryFileUploadHandler, "receive_data_chunk", track_write),
            patch("aicmo.store_app.services.engine", return_value=self.runner) as engine,
        ):
            response = self.client.post(
                f"/stores/{self.store.pk}/outcomes/preview/",
                {
                    "input_kind": "web_csv",
                    # Neither a photo MIME/filename nor a form field raises this route's cap.
                    "max_file_bytes": str(MAX_PHOTO_BYTES),
                    "csv_file": SimpleUploadedFile(
                        "sk-syntheticCsvSecret123456789.png",
                        b"x" * (MAX_CSV_BYTES + 1),
                        "image/png",
                    ),
                },
            )
        self.assertContains(response, "32 KiB", status_code=400)
        self.assertNotContains(response, "20 MiB", status_code=400)
        self.assertNotContains(response, "sk-syntheticCsvSecret123456789", status_code=400)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertTrue(persisted)
        self.assertLessEqual(max(persisted), MAX_CSV_BYTES)
        engine.assert_not_called()
        self.assert_no_work()

    def test_csv_multiple_files_and_interruption_keep_csv_recovery_guidance(self) -> None:
        source = b"date,channel,posts,inquiries,reservations,coupon_redemptions\n"
        data = {
            "input_kind": "web_csv",
            "csv_file": [SimpleUploadedFile("synthetic.csv", source) for _ in range(2)],
        }
        multiple = encode_multipart(BOUNDARY, data)
        data["csv_file"] = [SimpleUploadedFile("synthetic.csv", source)]
        interrupted = encode_multipart(BOUNDARY, data).rsplit(
            b"\r\n--" + BOUNDARY.encode() + b"--", 1
        )[0][:-16]
        for body in (multiple, interrupted):
            with (
                self.subTest(multiple=body is multiple),
                patch("aicmo.store_app.services.engine", return_value=self.runner) as engine,
            ):
                response = self.client.generic(
                    "POST",
                    f"/stores/{self.store.pk}/outcomes/preview/",
                    body,
                    content_type=MULTIPART_CONTENT,
                )
                self.assertContains(response, "CSV 파일 1개", status_code=400)
                self.assertNotContains(response, "20 MiB", status_code=400)
                engine.assert_not_called()
                self.assert_no_work()
