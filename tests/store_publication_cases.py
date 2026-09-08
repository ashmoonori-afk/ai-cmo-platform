from __future__ import annotations

# Real Django/engine databases; every owner and result below is synthetic.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from typing import cast
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.db import IntegrityError, connections, transaction
from django.http import QueryDict
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.store_app import delivery, publication, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, PublicationReport, Store
from aicmo.web_run_lock import web_run_lock
from tests.test_local_pack import (
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


class PublicationTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("publication-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        configure_quota(self.runner.store, "shop", current_period(), 2, 4)
        self.job = services.submit(
            self.store, uuid.uuid4(), _brief(reviews=1)["brief_json"], actor=self.owner
        )
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            self.assertTrue(run_one())
            self.job.refresh_from_db()
            _, pack_sha, photo_sha = services.preview(self.job)
            services.request_approval(self.job, pack_sha, photo_sha, self.owner)
            self.assertTrue(run_one())
        self.job.refresh_from_db()
        self.assertEqual(self.job.state, "success")
        self.snapshot = delivery.snapshot(self.job)
        self.card = self.snapshot.cards[0]
        self.url = f"/jobs/{self.job.pk}/publication/{self.card.key}/"
        self.delivery_url = f"/jobs/{self.job.pk}/delivery/"

    def data(self, revision: int = 0, *, cancel: bool = False) -> dict[str, object]:
        data: dict[str, object] = {
            "bundle_sha": self.snapshot.bundle_sha,
            "file_sha": self.card.file_sha,
            "expected_revision": revision,
            "request_key": str(uuid.uuid4()),
            "action": "cancel" if cancel else "report",
        }
        if not cancel:
            data["posted_on"] = timezone.localdate(timezone=publication.KST).isoformat()
        return data

    def test_report_correction_cancel_replay_preserves_history_and_usage(self) -> None:
        prior_day = timezone.localdate(timezone=publication.KST) - timedelta(days=1)
        Job.objects.filter(pk=self.job.pk).update(created_at=timezone.now() - timedelta(days=2))
        before = quota_status(self.runner.store, "shop", current_period())
        first = self.data()
        self.assertEqual(self.client.post(self.url, first).status_code, 302)
        self.assertEqual(self.client.post(self.url, first).status_code, 302)
        original = PublicationReport.objects.get()
        corrected = {**self.data(1), "posted_on": prior_day.isoformat()}
        self.assertEqual(self.client.post(self.url, corrected).status_code, 302)
        self.assertEqual(self.client.post(self.url, first).status_code, 302)
        cancellation = self.data(2, cancel=True)
        self.assertEqual(self.client.post(self.url, cancellation).status_code, 302)
        self.assertEqual(self.client.post(self.url, cancellation).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.data(3, cancel=True)).status_code, 409)
        self.assertEqual(self.client.post(self.url, self.data(1)).status_code, 409)
        self.assertEqual(self.client.post(self.url, self.data(3)).status_code, 302)
        original.refresh_from_db()
        self.assertEqual(original.posted_on, date.fromisoformat(str(first["posted_on"])))
        rows = list(PublicationReport.objects.order_by("revision"))
        self.assertEqual([row.revision for row in rows], [1, 2, 3, 4])
        self.assertEqual(
            [row.posted_on for row in rows],
            [original.posted_on, prior_day, None, original.posted_on],
        )
        self.assertTrue(all(row.recorded_by_id == self.owner.pk for row in rows))
        self.assertTrue(all(row.file_sha256 == self.card.file_sha for row in rows))
        self.assertContains(self.client.get(self.delivery_url), "외부 게시 여부는 확인하지 않으며")
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), before)
        self.assertEqual(Job.objects.count(), 1)
        self.assertFalse((self.root / f"artifacts/{self.job.run_id}/exports").exists())
        self.assertFalse((self.root / "knowledge-base").exists())

    def test_request_key_cannot_change_actor_action_date_or_source(self) -> None:
        Job.objects.filter(pk=self.job.pk).update(created_at=timezone.now() - timedelta(days=2))
        first = self.data()
        self.assertEqual(self.client.post(self.url, first).status_code, 302)
        for change in (
            {"action": "cancel", "posted_on": ""},
            {"expected_revision": 1},
            {"bundle_sha": "0" * 64},
            {"file_sha": "0" * 64},
            {
                "posted_on": (
                    timezone.localdate(timezone=publication.KST) - timedelta(days=1)
                ).isoformat()
            },
        ):
            self.assertEqual(self.client.post(self.url, {**first, **change}).status_code, 409)
        other_card = self.snapshot.cards[1]
        self.assertEqual(
            self.client.post(
                self.url.replace(self.card.key, other_card.key),
                {**first, "file_sha": other_card.file_sha},
            ).status_code,
            409,
        )
        operator = User.objects.create_user("publication-operator")
        operator.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(codename="operate_stores")
        )
        self.client.force_login(operator)
        self.assertEqual(self.client.post(self.url, first).status_code, 409)
        self.assertEqual(PublicationReport.objects.count(), 1)

    def test_auth_method_csrf_and_invalid_inputs_fail_without_disclosure(self) -> None:
        self.assertEqual(self.client.get(self.url).status_code, 405)
        other = User.objects.create_user("publication-other")
        self.client.force_login(other)
        with patch("aicmo.store_app.delivery.snapshot") as snapshot:
            self.assertEqual(self.client.post(self.url, self.data()).status_code, 404)
            snapshot.assert_not_called()
        self.client.logout()
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 302)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(self.url, self.data()).status_code, 403)
        self.client.force_login(self.owner)
        for change in (
            {"posted_on": ""},
            {"posted_on": "2026-02-30"},
            {"request_key": "sk-syntheticSecretNeverReflect123456789"},
            {"action": "cancel"},
            {"extra": "sk-syntheticSecretNeverReflect123456789"},
            {"expected_revision": -1},
            {"expected_revision": 2**63 - 1},
        ):
            response = self.client.post(self.url, {**self.data(), **change})
            self.assertEqual(response.status_code, 400)
            self.assertNotContains(response, "sk-syntheticSecret", status_code=400)
        data = QueryDict(mutable=True)
        data.update({name: str(value) for name, value in self.data().items()})
        data.appendlist("file_sha", "sk-syntheticSecretNeverReflect123456789")
        response = self.client.post(
            self.url, data.urlencode(), content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "sk-syntheticSecret", status_code=400)
        self.assertEqual(
            self.client.post(self.url.replace(self.card.key, "unknown"), self.data()).status_code,
            409,
        )
        self.assertEqual(PublicationReport.objects.count(), 0)

    def test_every_replay_revalidates_approval_and_current_bytes(self) -> None:
        first = self.data()
        self.assertEqual(self.client.post(self.url, first).status_code, 302)
        source = self.root / f"artifacts/{self.job.run_id}/local-pack.json"
        original = source.read_bytes()
        source.write_bytes(original + b" ")
        self.assertEqual(self.client.post(self.url, first).status_code, 409)
        source.write_bytes(original)
        Job.objects.filter(pk=self.job.pk).update(state="waiting_approval")
        self.assertEqual(self.client.post(self.url, first).status_code, 409)
        Job.objects.filter(pk=self.job.pk).update(
            state="success", inputs={**self.job.inputs, "client": "other"}
        )
        self.assertEqual(self.client.post(self.url, first).status_code, 404)
        self.assertEqual(PublicationReport.objects.count(), 1)

    def test_korean_date_boundaries_ignore_the_active_display_timezone(self) -> None:
        instant = datetime(2026, 9, 8, 15, 30, tzinfo=UTC)
        Job.objects.filter(pk=self.job.pk).update(created_at=instant - timedelta(minutes=15))
        self.job.refresh_from_db()
        with (
            patch("aicmo.store_app.publication.timezone.now", return_value=instant),
            timezone.override("UTC"),
        ):
            # Authenticate at the test clock; the earlier session has an eight-hour lifetime.
            self.client.force_login(self.owner)
            view = publication.context(
                self.job, self.snapshot.bundle_sha, self.card.key, self.card.file_sha
            )
            form = cast("publication.ReportForm", view["form"])
            self.assertEqual(form.fields["posted_on"].widget.attrs["min"], "2026-09-09")
            self.assertEqual(form.fields["posted_on"].widget.attrs["max"], "2026-09-09")
            for day in ("2026-09-08", "2026-09-10"):
                self.assertEqual(
                    self.client.post(self.url, {**self.data(), "posted_on": day}).status_code, 409
                )
            self.assertEqual(
                self.client.post(self.url, {**self.data(), "posted_on": "2026-09-09"}).status_code,
                302,
            )
            self.assertContains(self.client.get(self.delivery_url), "2026-09-09 00:30 (한국 시간)")
        report = PublicationReport.objects.get()
        self.assertEqual(report.posted_on, date(2026, 9, 9))
        self.assertEqual(report.created_at, instant)

    def test_permission_and_active_status_are_rechecked_after_lock(self) -> None:
        operator = User.objects.create_user("publication-revoked-operator")
        permission = Permission.objects.get(codename="operate_stores")
        for revoke in ("permission", "active"):
            operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
            User.objects.filter(pk=operator.pk).update(is_active=True)
            self.client.force_login(operator)

            @contextmanager
            def revoked_lock(
                repo: Path, run_id: str, *, blocking: bool = True, revoke: str = revoke
            ) -> Iterator[None]:
                if revoke == "permission":
                    operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
                else:
                    User.objects.filter(pk=operator.pk).update(is_active=False)
                with web_run_lock(repo, run_id, blocking=blocking):
                    yield

            with patch("aicmo.store_app.publication.web_run_lock", side_effect=revoked_lock):
                self.assertEqual(self.client.post(self.url, self.data()).status_code, 404)
        self.assertEqual(PublicationReport.objects.count(), 0)

    def test_concurrent_posts_are_idempotent_or_stale_with_real_database(self) -> None:
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(self.owner)

        def race(payloads: list[dict[str, object]]) -> list[int]:
            barrier = Barrier(2)

            def post(index: int) -> int:
                try:
                    barrier.wait(timeout=10)
                    return clients[index].post(self.url, payloads[index]).status_code
                finally:
                    connections.close_all()

            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(post, range(2)))

        identical = self.data()
        statuses = race([identical, identical])
        self.assertIn(302, statuses)
        self.assertTrue(set(statuses) <= {302, 409})
        self.assertEqual(self.client.post(self.url, identical).status_code, 302)
        self.assertEqual(PublicationReport.objects.count(), 1)
        self.assertEqual(sorted(race([self.data(1), self.data(1)])), [302, 409])
        self.assertEqual(
            list(PublicationReport.objects.order_by("revision").values_list("revision", flat=True)),
            [1, 2],
        )

    def test_database_constraints_and_bounded_history_preserve_older_events(self) -> None:
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 302)
        first = PublicationReport.objects.get()
        values = {
            "job": self.job,
            "bundle_sha256": first.bundle_sha256,
            "file_sha256": first.file_sha256,
            "item_key": first.item_key,
            "recorded_by": self.owner,
            "posted_on": first.posted_on,
        }
        for revision, key in ((1, uuid.uuid4()), (0, uuid.uuid4()), (2, first.request_key)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                PublicationReport.objects.create(**values, revision=revision, request_key=key)
        PublicationReport.objects.bulk_create(
            [
                PublicationReport(**values, revision=revision, request_key=uuid.uuid4())
                for revision in range(2, 24)
            ]
        )
        view = publication.context(self.job, first.bundle_sha256, first.item_key, first.file_sha256)
        self.assertEqual(len(cast("list[PublicationReport]", view["history"])), 20)
        self.assertTrue(view["history_more"])
        self.assertEqual(cast("PublicationReport", view["latest"]).revision, 23)
        self.assertContains(self.client.get(self.delivery_url), "더 오래된 이력도 삭제하지 않고")
        self.assertEqual(PublicationReport.objects.count(), 23)
