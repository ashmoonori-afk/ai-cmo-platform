from __future__ import annotations

# Django owns assertions and isolation. These are app-boundary checks, not proxy/HTTPS evidence.
# ruff: noqa: PT009
# pyright: reportUninitializedInstanceVariable=false
import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Permission, User
from django.contrib.sessions.models import Session
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from aicmo.store_app import guidance
from aicmo.store_app.models import EditDraft, Job, OnboardingDraft, PublicationReport, Store
from tests.store_onboarding_cases import STEPS
from tests.test_local_pack import _brief  # pyright: ignore[reportPrivateUsage]


@contextmanager
def no_customer_work() -> Iterator[None]:
    """A rejected request must stop before source reads, file preparation or business writes."""
    with ExitStack() as stack:
        for target in (
            "services.reader",
            "services.preview",
            "services.engine",
            "services.submit",
            "services.request_approval",
            "services.request_cancel",
            "services.download",
            "services.verified_files",
            "guidance.profile_hints",
            "photos.store_photo",
            "photos.verify_photo_assets",
            "editor.inspect_base",
            "editor.save",
            "editor.confirm",
            "rewrites.source",
            "delivery.snapshot",
            "onboarding.save_step",
            "onboarding.confirm",
            "auth.LimitedBackend.authenticate",
        ):
            stack.enter_context(
                patch(
                    f"aicmo.store_app.{target}",
                    side_effect=AssertionError(f"Rejected request reached {target}"),
                )
            )
        yield


class BoundaryTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("boundary-owner")
        self.other = User.objects.create_user("boundary-other-owner")
        self.staff = User.objects.create_user("boundary-staff", is_staff=True)
        self.inactive = User.objects.create_user("boundary-inactive", is_active=False)
        self.store = Store.objects.create(
            owner=self.owner, name="비공개 대상 가게 표식", client="boundary-shop"
        )
        self.other_store = Store.objects.create(
            owner=self.other, name="다른 사장님의 가게", client="boundary-other"
        )
        # No engine run is needed: denial must precede reading even a successful job's files.
        self.job = Job.objects.create(
            store=self.store, submission_key=uuid.uuid4(), inputs=_brief(), state="success"
        )
        self.new_owner = User.objects.create_user("boundary-onboarding-owner")
        values = {name: value for step in STEPS.values() for name, value in step.items()}
        values["company_name"] = "비공개 온보딩 가게 표식"
        self.draft = OnboardingDraft.objects.create(
            owner=self.new_owner, data=values, completed_step=3, revision=7
        )
        prefix = f"/jobs/{self.job.pk}/"
        self.target_gets = [
            f"/stores/{self.store.pk}/new/",
            prefix,
            *(
                prefix + suffix
                for suffix in ("photo/", "edit/", "edit/confirm/", "rewrite/", "delivery/")
            ),
        ]
        self.target_posts = [
            f"/stores/{self.store.pk}/new/",
            *(
                prefix + suffix
                for suffix in (
                    "edit/",
                    "edit/confirm/",
                    "edit/restore/",
                    "rewrite/",
                    "approve/",
                    "cancel/",
                    "download/",
                    "publication/news-1/",
                )
            ),
        ]

    def test_target_urls_reject_before_source_file_or_business_work(self) -> None:
        before = Job.objects.values().get(pk=self.job.pk)
        for actor, expected in (
            (self.other, 404),
            (self.staff, 404),
            (None, 302),
            (self.inactive, 302),
        ):
            client = Client()
            if actor is not None:
                client.force_login(actor)
            with no_customer_work():
                for method, urls in (("get", self.target_gets), ("post", self.target_posts)):
                    for url in urls:
                        with self.subTest(actor=actor, method=method, url=url):
                            response = getattr(client, method)(url)
                            self.assertEqual(response.status_code, expected)
                            self.assertNotIn(self.store.name.encode(), response.content)
                            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                            if expected == 302:
                                self.assertTrue(response["Location"].startswith("/login/?next="))
        self.assertEqual(Job.objects.values().get(pk=self.job.pk), before)
        self.assertEqual(Job.objects.count(), 1)
        self.assertFalse(EditDraft.objects.exists())
        self.assertFalse(PublicationReport.objects.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_listing_and_onboarding_only_use_the_current_account(self) -> None:
        original_profile = guidance.profile_hints

        def own_profile(store: Store) -> guidance.ProfileHints:
            self.assertEqual(store.pk, self.other_store.pk)
            return original_profile(store)

        self.client.force_login(self.other)
        with patch("aicmo.store_app.guidance.profile_hints", side_effect=own_profile) as profile:
            home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertEqual(profile.call_count, 1)
        self.assertNotContains(home, self.store.name)
        self.assertNotContains(home, str(self.job.pk))
        self.assertIn("no-store", home["Cache-Control"])
        with no_customer_work():
            archive = self.client.get("/archive/")
            self.assertEqual(archive.status_code, 200)
            self.assertNotContains(archive, self.store.name)
            self.assertNotContains(archive, str(self.job.pk))
            self.assertIn("no-store", archive["Cache-Control"])
            filtered = self.client.get("/archive/", {"store": self.store.pk})
            self.assertEqual(filtered.status_code, 400)
            self.assertNotContains(filtered, self.store.name, status_code=400)
            for actor in (self.other, self.staff):
                self.client.force_login(actor)
                for path in ("/onboarding/", "/onboarding/1/", "/onboarding/confirm/"):
                    response = self.client.get(
                        path, {"owner": self.new_owner.pk, "draft": str(self.draft.pk)}
                    )
                    self.assertIn(response.status_code, (200, 302))
                    self.assertNotIn(self.draft.data["company_name"].encode(), response.content)
                self.assertEqual(
                    self.client.post(
                        "/onboarding/confirm/", {"revision": 7, "checked": "on"}
                    ).status_code,
                    302,
                )
            for actor in (None, self.inactive):
                client = Client()
                if actor is not None:
                    client.force_login(actor)
                for path in (
                    "/",
                    "/archive/",
                    "/onboarding/",
                    "/onboarding/2/",
                    "/onboarding/confirm/",
                ):
                    self.assertEqual(client.get(path).status_code, 302)
        self.draft.refresh_from_db()
        self.assertEqual((self.draft.revision, self.draft.state), (7, "draft"))
        self.assertEqual(OnboardingDraft.objects.count(), 1)

    def test_all_new_post_boundaries_require_csrf_and_accept_no_foreign_origin(self) -> None:
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.get("/login/").status_code, 200)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        paths = [
            *self.target_posts,
            "/onboarding/",
            "/onboarding/1/",
            "/onboarding/2/",
            "/onboarding/3/",
            "/onboarding/confirm/",
            "/login/",
            "/logout/",
            "/operator/login/",
            "/operator/logout/",
        ]
        with (
            no_customer_work(),
            patch(
                "aicmo.store_app.services.owned_store",
                side_effect=AssertionError("CSRF reached store lookup"),
            ),
            patch(
                "aicmo.store_app.services.owned_job",
                side_effect=AssertionError("CSRF reached job lookup"),
            ),
            patch(
                "aicmo.store_app.onboarding.new_owner",
                side_effect=AssertionError("CSRF reached onboarding"),
            ),
        ):
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(client.post(path).status_code, 403)
                    self.assertEqual(
                        client.post(
                            path,
                            {"csrfmiddlewaretoken": token},
                            secure=True,
                            HTTP_ORIGIN="https://foreign.invalid",
                        ).status_code,
                        403,
                    )
            self.assertEqual(client.session[SESSION_KEY], str(self.owner.pk))
            # The same real cookie/token succeeds with its own HTTPS Origin.
            self.assertEqual(
                client.post(
                    "/logout/",
                    {"csrfmiddlewaretoken": token},
                    secure=True,
                    HTTP_ORIGIN="https://testserver",
                ).status_code,
                302,
            )
        self.assertNotIn(SESSION_KEY, client.session)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(OnboardingDraft.objects.count(), 1)

    def test_expired_logged_out_password_changed_and_inactive_sessions_stop_at_login(self) -> None:
        for invalidation in ("expired", "logout", "password", "inactive"):
            with self.subTest(invalidation=invalidation):
                self.owner.refresh_from_db()
                client = Client()
                client.force_login(self.owner)
                session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
                self.assertEqual(client.session[SESSION_KEY], str(self.owner.pk))
                if invalidation == "expired":
                    Session.objects.filter(session_key=session_key).update(
                        expire_date=timezone.now() - timedelta(seconds=1)
                    )
                elif invalidation == "logout":
                    self.assertEqual(client.post("/logout/").status_code, 302)
                elif invalidation == "password":
                    self.owner.set_password("synthetic-boundary-changed-password")
                    self.owner.save(update_fields=["password"])
                else:
                    User.objects.filter(pk=self.owner.pk).update(is_active=False)
                client.cookies[settings.SESSION_COOKIE_NAME] = session_key
                with no_customer_work():
                    for method, path in (
                        ("get", f"/jobs/{self.job.pk}/delivery/"),
                        ("post", f"/jobs/{self.job.pk}/download/"),
                    ):
                        response = getattr(client, method)(path)
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(response["Location"].startswith("/login/?next="))
                if invalidation != "inactive":
                    self.assertNotIn(SESSION_KEY, client.session)
                User.objects.filter(pk=self.owner.pk).update(is_active=True)
        # This verifies the next request; it does not revoke an already-authorized streaming ZIP.
        self.assertEqual(Job.objects.count(), 1)

    def test_real_admin_separates_staff_business_and_model_permissions(self) -> None:
        model_paths = [
            "/operator/store_app/store/",
            f"/operator/store_app/store/{self.store.pk}/change/",
            "/operator/store_app/onboardingdraft/",
            f"/operator/store_app/onboardingdraft/{self.draft.pk}/change/",
            "/operator/auth/user/",
            "/operator/auth/group/",
        ]
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/operator/").status_code, 200)
        operate = Permission.objects.get(codename="operate_stores")
        for business_permission in (False, True):
            if business_permission:
                self.staff.user_permissions.add(operate)  # pyright: ignore[reportUnknownMemberType]
            with no_customer_work():
                for path in model_paths:
                    self.assertEqual(self.client.get(path).status_code, 403)
                self.assertEqual(
                    self.client.post(model_paths[1], {"name": "forbidden"}).status_code, 403
                )
            archive = self.client.get("/archive/")
            self.assertEqual(self.store.name.encode() in archive.content, business_permission)
        self.staff.user_permissions.remove(operate)  # pyright: ignore[reportUnknownMemberType]
        self.staff.user_permissions.add(Permission.objects.get(codename="view_store"))  # pyright: ignore[reportUnknownMemberType]
        self.assertContains(self.client.get(model_paths[0]), self.store.name)
        self.assertEqual(self.client.get(model_paths[1]).status_code, 200)
        self.assertEqual(self.client.post(model_paths[1], {"name": "forbidden"}).status_code, 403)
        with no_customer_work():
            self.assertEqual(self.client.get(f"/jobs/{self.job.pk}/delivery/").status_code, 404)
        self.other.user_permissions.add(operate)  # pyright: ignore[reportUnknownMemberType]
        self.client.force_login(self.other)
        self.assertContains(self.client.get("/archive/"), self.store.name)
        for actor in (self.other, self.inactive, None):
            client = Client()
            if actor is not None:
                client.force_login(actor)
            for path in ("/operator/", *model_paths):
                response = client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/operator/login/?next="))
        self.store.refresh_from_db()
        self.assertEqual(self.store.name, "비공개 대상 가게 표식")

    def test_existing_private_files_have_no_public_django_route(self) -> None:
        marker = b"synthetic-private-file-boundary-only"
        paths = (
            ".aicmo/web.sqlite3",
            ".aicmo/photos/shop/example.png",
            f"artifacts/{self.job.run_id}/local-pack.json",
            "clients/boundary-shop/config.md",
            "knowledge-base/boundary-shop/insights.md",
        )
        for path in paths:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(marker)
        for actor in (None, self.owner):
            client = Client()
            if actor is not None:
                client.force_login(actor)
            with no_customer_work():
                for path in paths:
                    for prefix in ("/", "/static/"):
                        response = client.get(prefix + path)
                        self.assertEqual(response.status_code, 404)
                        self.assertNotIn(marker, response.content)
        self.assertTrue(all((self.root / path).read_bytes() == marker for path in paths))
        # Proxy/WSGI aliases and deployed static mappings still require separate H evidence.
