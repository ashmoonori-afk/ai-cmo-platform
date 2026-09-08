from __future__ import annotations

# Django owns the test database; all submitted metadata and owner data are synthetic.
# ruff: noqa: PT009
import uuid
from datetime import timedelta
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from aicmo.redaction import contains_raw_secret
from aicmo.store_app.forms import OnboardingConfirmForm
from aicmo.store_app.models import Job, OnboardingDraft, Store
from tests.store_onboarding_cases import STEPS


class MetadataInput(HTMLParser):
    def __init__(self, name: str = "revision") -> None:
        super().__init__()
        self.name = name
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag == "input" and fields.get("name") == self.name:
            self.values.append(fields.get("value") or "")


@override_settings(ALLOWED_HOSTS=["testserver"])
class OnboardingMetadataTests(TransactionTestCase):
    def test_confirmation_errors_preserve_only_valid_metadata_and_replay(self) -> None:
        owner = User.objects.create_user("metadata-synthetic-owner")
        data = {name: value for fields in STEPS.values() for name, value in fields.items()}
        draft = OnboardingDraft.objects.create(
            owner=owner, data=data, revision=7, completed_step=3
        )
        self.client.force_login(owner)
        marker = "sk-" + "SYNTHETICG22ONLYNOACCOUNT0123456789ABCDEF"
        self.assertTrue(contains_raw_secret(marker))
        self.assertEqual(OnboardingConfirmForm().fields["revision"].clean("7"), 7)

        cases: list[tuple[QueryDict, int, str]] = []
        invalid = QueryDict(mutable=True)
        invalid.update({"revision": marker, "checked": "on"})
        cases.append((invalid, 400, ""))
        unchecked = QueryDict(mutable=True)
        unchecked.update({"revision": "7"})
        cases.append((unchecked, 400, "7"))
        stale = QueryDict(mutable=True)
        stale.update({"revision": "6", "checked": "on"})
        cases.append((stale, 409, "6"))
        unknown = QueryDict(mutable=True)
        unknown.update({"revision": "7", "checked": "on", "extra": marker})
        cases.append((unknown, 409, "7"))
        duplicate = QueryDict(mutable=True)
        duplicate.update({"revision": marker, "checked": "on"})
        duplicate.appendlist("revision", "7")
        cases.append((duplicate, 409, "7"))

        for post, status, safe_revision in cases:
            response = self.client.post(
                "/onboarding/confirm/",
                post.urlencode(),
                content_type="application/x-www-form-urlencoded",
            )
            self.assertEqual(response.status_code, status)
            html = response.content.decode()
            self.assertFalse(marker in html, "Synthetic credential reached the error page")
            parsed = MetadataInput()
            parsed.feed(html)
            self.assertEqual(parsed.values, [safe_revision])
            draft.refresh_from_db()
            self.assertEqual((draft.state, draft.revision, draft.data), ("draft", 7, data))
            self.assertIsNone(draft.confirmed_at)

        valid = {"revision": "7", "checked": "on"}
        self.assertEqual(self.client.post("/onboarding/confirm/", valid).status_code, 302)
        draft.refresh_from_db()
        confirmed_at = draft.confirmed_at
        self.assertIsNotNone(confirmed_at)
        self.assertEqual(self.client.post("/onboarding/confirm/", valid).status_code, 302)
        draft.refresh_from_db()
        self.assertEqual((draft.state, draft.revision, draft.data), ("queued", 7, data))
        self.assertEqual(draft.confirmed_at, confirmed_at)
        self.assertEqual(OnboardingDraft.objects.count(), 1)
        self.assertEqual(Store.objects.count(), 0)
        self.assertEqual(Job.objects.count(), 0)


@override_settings(ALLOWED_HOSTS=["testserver"])
class ArchiveMetadataTests(TransactionTestCase):
    def test_archive_errors_discard_invalid_metadata_and_keep_valid_filters(self) -> None:
        owner = User.objects.create_user("archive-metadata-owner")
        store = Store.objects.create(owner=owner, name="합성 <가게>", client="metadata-shop")
        Job.objects.create(store=store, submission_key=uuid.uuid4(), state="success", inputs={})
        self.client.force_login(owner)
        today = timezone.localdate().isoformat()
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        marker = "sk-" + "SYNTHETICG22ONLYNOACCOUNT0123456789ABCDEF"
        valid = {"store": str(store.pk), "state": "success", "start": today, "end": today}
        for field in ("start", "end", "state", "store", "page"):
            with self.subTest(field=field):
                response = self.client.get("/archive/", {**valid, field: marker})
                self.assertEqual(response.status_code, 400)
                html = response.content.decode()
                self.assertFalse(marker in html, "Synthetic credential reached archive HTML")
                for date_field in ("start", "end"):
                    parsed = MetadataInput(date_field)
                    parsed.feed(html)
                    self.assertEqual(parsed.values, ["" if field == date_field else today])

        response = self.client.get("/archive/", {**valid, "end": yesterday})
        self.assertContains(response, "종료일은 시작일과 같거나 이후", status_code=400)
        for name, expected in (("start", today), ("end", yesterday)):
            parsed = MetadataInput(name)
            parsed.feed(response.content.decode())
            self.assertEqual(parsed.values, [expected])

        duplicate = QueryDict(mutable=True)
        duplicate.update(valid)
        duplicate.appendlist("start", marker)
        response = self.client.get("/archive/?" + duplicate.urlencode())
        self.assertEqual(response.status_code, 400)
        self.assertFalse(marker in response.content.decode(), "Duplicate date reflected a secret")

        response = self.client.get("/archive/", valid)
        self.assertContains(response, "합성 &lt;가게&gt;")
        self.assertContains(response, f'value="{store.pk}" selected')
        self.assertContains(response, 'value="success" selected')
        for name in ("start", "end"):
            parsed = MetadataInput(name)
            parsed.feed(response.content.decode())
            self.assertEqual(parsed.values, [today])
        self.assertEqual(Job.objects.count(), 1)
