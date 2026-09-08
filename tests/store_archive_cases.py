from __future__ import annotations

# ruff: noqa: PT009
# pyright: reportUninitializedInstanceVariable=false
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings

from aicmo.store_app.models import Job, Store


@override_settings(ALLOWED_HOSTS=["testserver"])
class ArchiveTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user("archive-owner")
        other = User.objects.create_user("archive-other")
        self.store = Store.objects.create(owner=self.owner, name="합성 우리 가게", client="archive")
        self.other = Store.objects.create(owner=other, name="비공개 다른 가게", client="other")
        self.client.force_login(self.owner)

    def job(self, store: Store, state: str = "success", day: int = 8) -> Job:
        job = Job.objects.create(store=store, submission_key=uuid.uuid4(), inputs={}, state=state)
        Job.objects.filter(pk=job.pk).update(
            created_at=datetime(2026, 9, day, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        )
        return job

    def test_tenant_scope_and_operator_access(self) -> None:
        own, other = self.job(self.store), self.job(self.other)
        response = self.client.get("/archive/")
        self.assertContains(response, str(own.id))
        self.assertNotContains(response, str(other.id))
        self.assertNotContains(response, self.other.name)
        response = self.client.get("/archive/", {"store": self.other.pk})
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, self.other.name, status_code=400)
        self.owner.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(codename="operate_stores")
        )
        self.assertContains(self.client.get("/archive/"), str(other.id))
        self.client.logout()
        self.assertEqual(self.client.get("/archive/").status_code, 302)

    def test_date_boundaries_status_and_invalid_filters(self) -> None:
        first = self.job(self.store, day=8)
        last = self.job(self.store, day=9)
        outside = self.job(self.store, day=10)
        failed = self.job(self.store, state="failed", day=8)
        response = self.client.get(
            "/archive/", {"start": "2026-09-08", "end": "2026-09-09", "state": "success"}
        )
        self.assertContains(response, str(first.id))
        self.assertContains(response, str(last.id))
        self.assertNotContains(response, str(outside.id))
        self.assertNotContains(response, str(failed.id))
        for query in (
            {"start": "not-a-date"},
            {"end": "2026-02-30"},
            {"start": "2026-09-09", "end": "2026-09-08"},
            {"state": "private"},
            {"store": "invalid"},
            {"page": "-1"},
            {"page": "abc"},
            {"page": "9999"},
            {"state": ["success", "failed"]},
        ):
            with self.subTest(query=query):
                response = self.client.get("/archive/", query)
                self.assertContains(response, "검색 조건을 확인", status_code=400)
                self.assertNotContains(response, str(first.id), status_code=400)

    def test_stable_pagination_preserves_filters_and_resets_page(self) -> None:
        jobs = [self.job(self.store) for _ in range(23)]
        self.job(self.other)
        query = {
            "store": str(self.store.pk),
            "state": "success",
            "start": "2026-09-08",
            "end": "2026-09-08",
        }
        first = self.client.get("/archive/", query)
        second = self.client.get("/archive/", {**query, "page": "2", "untrusted": "secret"})
        expected = sorted((job.id for job in jobs), reverse=True)
        self.assertEqual([job.id for job in first.context["page_obj"]], expected[:20])
        self.assertEqual([job.id for job in second.context["page_obj"]], expected[20:])
        self.assertContains(
            first, "state=success&amp;start=2026-09-08&amp;end=2026-09-08&amp;page=2"
        )
        self.assertContains(
            second, "state=success&amp;start=2026-09-08&amp;end=2026-09-08&amp;page=1"
        )
        self.assertNotContains(second, "secret")
        self.assertNotContains(second, 'name="page"')

    def test_empty_results_and_read_only(self) -> None:
        self.assertContains(self.client.get("/archive/"), "조건에 맞는 작업이 없습니다")
        self.assertEqual(self.client.post("/archive/").status_code, 405)
        self.job(self.store)
        response = self.client.get("/archive/", {"state": "cancelled"})
        self.assertContains(response, "조건에 맞는 작업이 없습니다")
        self.assertIn("no-store", response.headers["Cache-Control"])
