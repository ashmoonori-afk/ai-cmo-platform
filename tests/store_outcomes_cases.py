from __future__ import annotations

# Real Django/engine databases; all accounts and observations below are synthetic.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import base64
import csv
import hashlib
import io
import json
import re
import sqlite3
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from django.http import Http404, QueryDict
from django.test import Client, TransactionTestCase, override_settings

from aicmo.outcomes import CSV_COLUMNS
from aicmo.store import WorkflowStore
from aicmo.store_app import outcome_services, services
from aicmo.store_app.models import Job, Store
from tests.test_local_pack import _runner  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

WEEK = "2026-08-31"
DAY = "2026-09-01"
SECRET = "sk-syntheticOutcomeSecretNeverReflect123456789"


class OutcomesTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("outcomes-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        self.url = f"/stores/{self.store.pk}/outcomes/"
        provider = patch("aicmo.store_app.services.engine")
        unused = provider.start()
        self.addCleanup(provider.stop)
        self.addCleanup(unused.assert_not_called)

    def manual(self, **changes: str) -> dict[str, str]:
        return {
            "input_kind": "web_manual",
            "week_start": WEEK,
            "channel": "naver",
            "date": DAY,
            "posts": "0",
            "inquiries": "",
            "reservations": "2",
            "coupon_redemptions": "0",
            **changes,
        }

    def preview(self, data: Mapping[str, object] | None = None) -> dict[str, object]:
        response = self.client.post(self.url + "preview/", data or self.manual())
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        return cast("dict[str, object]", response.context["confirmation"])

    def confirmation(self, prepared: dict[str, object], **changes: str) -> dict[str, str]:
        return {
            "token": str(prepared["token"]),
            "raw_csv": str(prepared["raw_csv"]),
            "checked": "on",
            **changes,
        }

    def rows(self) -> list[dict[str, object]]:
        path = self.runner.store.db_path
        if not path.is_file():
            return []
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in connection.execute(
                    "select * from manual_outcomes order by client, channel, observed_on"
                )
            ]

    def upload(self, raw: bytes) -> dict[str, object]:
        return {
            "input_kind": "web_csv",
            "week_start": WEEK,
            "channel": "naver",
            "csv_file": SimpleUploadedFile("synthetic.csv", raw, content_type="text/csv"),
        }

    def csv_bytes(self, *rows: str) -> bytes:
        return (",".join(CSV_COLUMNS) + "\n" + "\n".join(rows) + "\n").encode()

    def save(self, prepared: dict[str, object], actor: User | None = None) -> int:
        return outcome_services.save(
            actor or self.owner,
            self.store,
            str(prepared["token"]),
            str(prepared["raw_csv"]),
            replace=False,
        )

    def test_manual_confirmation_replay_and_correction_preserve_missing_and_other_dates(
        self,
    ) -> None:
        prepared = self.preview()
        self.assertFalse(self.runner.store.db_path.exists())
        self.assertFalse(prepared["replace_required"])
        raw = base64.b64decode(str(prepared["raw_csv"]), validate=True)
        parsed = next(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(parsed["posts"], "0")
        self.assertEqual(parsed["inquiries"], "")
        data = self.confirmation(prepared)
        unchecked = {key: value for key, value in data.items() if key != "checked"}
        self.assertEqual(self.client.post(self.url + "confirm/", unchecked).status_code, 400)
        self.assertFalse(self.runner.store.db_path.exists())
        actual_save = outcome_services.save

        def response_lost(
            actor: AbstractBaseUser | AnonymousUser,
            store: Store,
            token: str,
            raw_csv: str,
            *,
            replace: bool,
        ) -> int:
            actual_save(actor, store, token, raw_csv, replace=replace)
            raise DatabaseError(SECRET)

        with patch("aicmo.store_app.outcome_services.save", side_effect=response_lost):
            uncertain = self.client.post(self.url + "confirm/", data)
        self.assertEqual(uncertain.status_code, 409)
        self.assertNotContains(uncertain, SECRET, status_code=409)
        original = self.rows()
        self.assertEqual(
            json.loads(str(original[0]["payload_json"])),
            {
                "date": DAY,
                "channel": "naver",
                "posts": 0,
                "inquiries": None,
                "reservations": 2,
                "coupon_redemptions": 0,
            },
        )
        self.assertEqual(original[0]["input_kind"], "web_manual")
        self.assertEqual(original[0]["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(original[0]["recorded_by"], f"web-user:{self.owner.pk}")
        self.assertTrue(original[0]["recorded_at"])
        self.assertEqual(self.client.post(self.url + "confirm/", data).status_code, 302)
        self.assertEqual(self.rows(), original)
        next_day = self.preview(self.manual(date="2026-09-02", inquiries="4"))
        self.assertEqual(self.save(next_day), 1)
        preserved = self.rows()[1]
        correction = self.preview(
            self.manual(posts="5", inquiries="6", reservations="7", coupon_redemptions="8")
        )
        self.assertTrue(correction["replace_required"])
        self.assertEqual(
            self.client.post(self.url + "confirm/", self.confirmation(correction)).status_code, 400
        )
        self.assertEqual(self.rows()[0], original[0])
        self.assertEqual(
            self.client.post(
                self.url + "confirm/", self.confirmation(correction, replace="on")
            ).status_code,
            302,
        )
        changed = self.rows()
        self.assertEqual(changed[0]["revision"], 2)
        self.assertEqual(
            json.loads(str(changed[0]["payload_json"])),
            {
                "date": DAY,
                "channel": "naver",
                "posts": 5,
                "inquiries": 6,
                "reservations": 7,
                "coupon_redemptions": 8,
            },
        )
        self.assertEqual(changed[1], preserved)
        self.assertEqual(self.client.post(self.url + "confirm/", data).status_code, 409)
        self.assertEqual(self.rows(), changed)
        self.assertEqual(Job.objects.count(), 0)
        self.assertFalse((self.root / "knowledge-base").exists())

    def test_csv_bom_and_invalid_uploads_never_echo_raw_cells(self) -> None:
        prepared = self.preview(
            self.upload(b"\xef\xbb\xbf" + self.csv_bytes(f"{DAY},naver,1,,0,2"))
        )
        self.assertEqual(self.save(prepared), 1)
        original = self.rows()
        self.assertEqual(original[0]["input_kind"], "web_csv")
        for raw in (
            self.csv_bytes(f"{DAY},naver,1,2,3,4", f"{DAY},naver,1,2,3,4"),
            self.csv_bytes(f"{DAY},naver,={SECRET},2,3,4"),
            self.csv_bytes(f"{DAY},instagram,1,2,3,4"),
            self.csv_bytes("2099-01-01,naver,1,2,3,4"),
            "한글".encode("cp949"),
            (SECRET.encode() * 800)[: 32 * 1024 + 1],
        ):
            with self.subTest(raw_size=len(raw)):
                response = self.client.post(self.url + "preview/", self.upload(raw))
                self.assertEqual(response.status_code, 400)
                self.assertNotContains(response, SECRET, status_code=400)
                self.assertEqual(self.rows(), original)
        self.assertEqual(Job.objects.count(), 0)

    def test_invalid_fields_duplicate_metadata_and_signed_source_fail_safely(self) -> None:
        for change in (
            {"posts": "-1"},
            {"inquiries": "1.5"},
            {"channel": SECRET},
            {"extra": SECRET},
        ):
            response = self.client.post(self.url + "preview/", self.manual(**change))
            self.assertEqual(response.status_code, 400)
            self.assertNotContains(response, SECRET, status_code=400)
        duplicate = QueryDict(mutable=True)
        duplicate.update(self.manual())
        duplicate.appendlist("posts", SECRET)
        response = self.client.post(
            self.url + "preview/",
            duplicate.urlencode(),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, SECRET, status_code=400)
        prepared = self.preview()
        for change in (
            {"token": SECRET},
            {"raw_csv": SECRET},
            {"raw_csv": base64.b64encode(self.csv_bytes(f"{DAY},naver,9,9,9,9")).decode()},
        ):
            response = self.client.post(
                self.url + "confirm/", self.confirmation(prepared, **change)
            )
            self.assertEqual(response.status_code, 409)
            self.assertNotContains(response, SECRET, status_code=409)
        response = self.client.post(
            self.url + "confirm/", self.confirmation(prepared, client=SECRET)
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, SECRET, status_code=400)
        self.assertFalse(self.runner.store.db_path.exists())

    def test_expired_and_stale_confirmation_cannot_overwrite_new_values(self) -> None:
        stale = self.preview()
        with patch(
            "django.core.signing.time.time",
            return_value=time.time() + outcome_services.TOKEN_MAX_AGE + 1,
        ):
            self.assertEqual(
                self.client.post(self.url + "confirm/", self.confirmation(stale)).status_code, 409
            )
        self.assertFalse(self.runner.store.db_path.exists())
        current = self.preview(self.manual(posts="4"))
        self.assertEqual(self.save(current), 1)
        original = self.rows()
        self.assertEqual(
            self.client.post(
                self.url + "confirm/", self.confirmation(stale, replace="on")
            ).status_code,
            409,
        )
        self.assertEqual(self.rows(), original)
        other = User.objects.create_user("outcomes-operator-token")
        other.user_permissions.add(Permission.objects.get(codename="operate_stores"))  # pyright: ignore[reportUnknownMemberType]
        self.client.force_login(other)
        self.assertEqual(
            self.client.post(self.url + "confirm/", self.confirmation(current)).status_code, 404
        )
        self.assertEqual(self.rows(), original)

    def test_read_only_screen_never_initializes_and_separates_channels(self) -> None:
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        with patch.object(
            WorkflowStore, "initialize", side_effect=AssertionError("GET must not migrate")
        ):
            response = self.client.get(self.url, {"week_start": WEEK, "channel": "naver"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(
            sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*")), before
        )
        self.assertEqual(self.save(self.preview(self.manual(posts="371"))), 1)
        self.assertEqual(
            self.save(self.preview(self.manual(channel="google-business", posts="829"))), 1
        )
        before_bytes = self.runner.store.db_path.read_bytes()
        original = self.rows()
        with patch.object(
            WorkflowStore, "initialize", side_effect=AssertionError("GET must not migrate")
        ):
            naver = self.client.get(self.url, {"week_start": WEEK, "channel": "naver"})
            google = self.client.get(self.url, {"week_start": WEEK, "channel": "google-business"})
        self.assertContains(naver, "게시 371")
        self.assertNotContains(naver, "게시 829")
        self.assertContains(google, "게시 829")
        self.assertNotContains(google, "게시 371")
        self.assertEqual(self.rows(), original)
        self.assertEqual(self.runner.store.db_path.read_bytes(), before_bytes)
        self.assertEqual(Job.objects.count(), 0)

    def test_methods_current_store_access_and_csrf_are_required(self) -> None:
        prepared = self.preview()
        self.assertEqual(self.client.get(self.url + "preview/").status_code, 405)
        self.assertEqual(self.client.get(self.url + "confirm/").status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(self.url + "preview/", self.manual()).status_code, 403)
        self.assertEqual(
            csrf.post(self.url + "confirm/", self.confirmation(prepared)).status_code, 403
        )
        self.client.force_login(User.objects.create_user("outcomes-other-owner"))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url + "preview/", self.manual()).status_code, 404)
        self.assertEqual(
            self.client.post(self.url + "confirm/", self.confirmation(prepared)).status_code, 404
        )
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url + "preview/", self.manual()).status_code, 302)
        self.assertEqual(
            self.client.post(self.url + "confirm/", self.confirmation(prepared)).status_code, 302
        )
        self.assertFalse(self.runner.store.db_path.exists())
        shown = csrf.get(self.url)
        tokens = re.findall(r'name="csrfmiddlewaretoken" value="([^"]+)"', shown.content.decode())
        self.assertTrue(tokens)
        preview = csrf.post(
            self.url + "preview/", {**self.manual(), "csrfmiddlewaretoken": tokens[0]}
        )
        self.assertEqual(preview.status_code, 200)
        tokens = re.findall(r'name="csrfmiddlewaretoken" value="([^"]+)"', preview.content.decode())
        self.assertTrue(tokens)
        accepted = cast("dict[str, object]", preview.context["confirmation"])
        self.assertEqual(
            csrf.post(
                self.url + "confirm/", self.confirmation(accepted, csrfmiddlewaretoken=tokens[0])
            ).status_code,
            302,
        )
        self.assertEqual(len(self.rows()), 1)

    def test_day_correction_and_edit_return_preserve_values_without_writing(self) -> None:
        prepared = self.preview()
        self.assertEqual(self.save(prepared), 1)
        self.assertEqual(
            self.save(self.preview(self.manual(channel="google-business", posts="83"))), 1
        )
        original = self.rows()
        before_bytes = self.runner.store.db_path.read_bytes()
        scope = {"week_start": WEEK, "channel": "naver", "day": DAY}
        shown = self.client.get(self.url, scope)
        self.assertEqual(shown.status_code, 200)
        form = shown.context["daily_form"]
        self.assertEqual(str(form["date"].value()), DAY)
        self.assertEqual(
            [form[name].value() for name in CSV_COLUMNS[2:]],
            [0, None, 2, 0],
        )
        self.assertNotIn("day", shown.context["scope"].fields)
        google = self.client.get(self.url, {**scope, "channel": "google-business"})
        self.assertEqual(google.context["daily_form"]["posts"].value(), 83)
        for day in (SECRET, "2026-02-30", "2026-09-07", "2099-01-01"):
            invalid = self.client.get(self.url, {**scope, "day": day})
            self.assertEqual(invalid.status_code, 400)
            self.assertNotContains(invalid, SECRET, status_code=400)
        duplicate = QueryDict(mutable=True)
        duplicate.update(scope)
        duplicate.appendlist("day", SECRET)
        invalid = self.client.get(self.url + "?" + duplicate.urlencode())
        self.assertEqual(invalid.status_code, 400)
        self.assertNotContains(invalid, SECRET, status_code=400)
        edit = {
            "token": str(prepared["token"]),
            "raw_csv": str(prepared["raw_csv"]),
            "action": "edit",
        }
        returned = self.client.post(self.url + "confirm/", edit)
        self.assertEqual(returned.status_code, 200)
        form = returned.context["daily_form"]
        self.assertEqual(str(form["date"].value()), DAY)
        self.assertEqual([form[name].value() for name in CSV_COLUMNS[2:]], [0, None, 2, 0])
        tampered = self.client.post(self.url + "confirm/", {**edit, "raw_csv": SECRET})
        self.assertEqual(tampered.status_code, 409)
        self.assertNotContains(tampered, SECRET, status_code=409)
        self.client.force_login(User.objects.create_user("outcomes-day-other-owner"))
        self.assertEqual(self.client.get(self.url, scope).status_code, 404)
        self.assertEqual(self.rows(), original)
        self.assertEqual(self.runner.store.db_path.read_bytes(), before_bytes)

    def test_save_rechecks_active_owner_store_assignment_and_client(self) -> None:
        prepared = self.preview()
        other = User.objects.create_user("outcomes-next-owner")
        fresh = services.fresh_actor
        changes: tuple[Callable[[], object], ...] = (
            lambda: User.objects.filter(pk=self.owner.pk).update(is_active=False),
            lambda: Store.objects.filter(pk=self.store.pk).update(owner=other),
            lambda: Store.objects.filter(pk=self.store.pk).update(client="changed-shop"),
        )
        for change in changes:

            def changed_actor(
                actor: AbstractBaseUser | AnonymousUser,
                update: Callable[[], object] = change,
            ) -> User:
                self.assertTrue(connection.in_atomic_block)
                update()
                return fresh(actor)

            try:
                with (
                    patch("aicmo.store_app.services.fresh_actor", side_effect=changed_actor),
                    self.assertRaises(Http404),
                ):
                    self.save(prepared)
                self.assertFalse(self.runner.store.db_path.exists())
            finally:
                User.objects.filter(pk=self.owner.pk).update(is_active=True)
                Store.objects.filter(pk=self.store.pk).update(owner=self.owner, client="shop")
        self.assertEqual(self.save(prepared), 1)
        original = self.rows()
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        with self.assertRaises(Http404):
            self.save(prepared)
        self.assertEqual(self.rows(), original)

    def test_operator_permission_cache_cannot_authorize_save_or_receipt_replay(self) -> None:
        operator = User.objects.create_user("outcomes-authority-operator")
        permission = Permission.objects.get(codename="operate_stores")
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        self.client.force_login(operator)
        prepared = self.preview()
        self.assertTrue(services.allowed_stores(operator).exists())
        fresh = services.fresh_actor

        def revoked_actor(actor: AbstractBaseUser | AnonymousUser) -> User:
            self.assertTrue(connection.in_atomic_block)
            operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
            return fresh(actor)

        with (
            patch("aicmo.store_app.services.fresh_actor", side_effect=revoked_actor),
            self.assertRaises(Http404),
        ):
            self.save(prepared, operator)
        self.assertFalse(self.runner.store.db_path.exists())
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        self.assertEqual(self.save(prepared, operator), 1)
        original = self.rows()
        operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
        with self.assertRaises(Http404):
            self.save(prepared, operator)
        self.assertEqual(self.rows(), original)
