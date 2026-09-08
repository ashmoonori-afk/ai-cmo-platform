from __future__ import annotations

# Django owns isolation; these stores and all text are synthetic.
# ruff: noqa: PT009
# pyright: reportUninitializedInstanceVariable=false
import json
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core import signing
from django.test import TransactionTestCase, override_settings

from aicmo.pack_edits import digest, editable_values, inspect_base
from aicmo.pack_rewrite import facts_sha, parse_rewrite
from aicmo.photos import normalize_photo
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.store_app import editor, photos, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import EditDraft, Job, Store
from tests.store_photo_cases import upload
from tests.test_local_pack import (
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


class RewriteTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("rewrite-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        configure_quota(self.runner.store, "shop", current_period(), 3, 6)
        brief = json.loads(_brief()["brief_json"])
        brief["facts"] = [brief["facts"][0]]
        self.fact = brief["facts"][0]
        self.job = services.submit(
            self.store, uuid.uuid4(), json.dumps(brief, ensure_ascii=False), actor=self.owner
        )
        self.assertTrue(self.tick())
        self.job.refresh_from_db()
        self.base, self.original = inspect_base(self.runner, self.job.run_id)
        editor.save(
            self.job,
            self.runner,
            digest(self.base.model_dump_json()),
            0,
            {**editable_values(self.original), "news_0_body": "저장한 재작성 기준 문안입니다."},
            actor=self.owner,
        )
        self.saved = EditDraft.objects.get(job=self.job).body
        self.url = f"/jobs/{self.job.id}/rewrite/"

    def tick(self) -> bool:
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            return run_one()

    def cancel(self) -> None:
        services.request_cancel(self.job, self.owner)
        self.assertTrue(self.tick())
        self.job.refresh_from_db()
        self.assertEqual(self.job.state, "cancelled")

    def preview(self, **changes: str):  # noqa: ANN201 — preserve Django test response typing
        return self.client.post(
            self.url,
            {
                "stage": "preview",
                "action": "shorten",
                "fact": self.fact,
                "checked": "on",
                **changes,
            },
        )

    def confirmation(self) -> dict[str, str]:
        response = self.preview()
        self.assertEqual(response.status_code, 200, response.content.decode())
        return {
            "stage": "confirm",
            "token": response.context["confirmation"].initial["token"],
            "checked": "on",
        }

    def test_invalid_action_never_echoes_secret_and_valid_token_stays_exact(self) -> None:
        self.cancel()
        secret = "sk-syntheticRewriteSecret123456789"
        response = self.preview(action=secret)
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, secret, status_code=400)
        self.assertContains(response, self.fact, status_code=400)
        confirmation = self.confirmation()
        payload = signing.loads(confirmation["token"], salt="aicmo.web-rewrite.v1", max_age=3600)
        self.assertEqual(payload["source_id"], str(self.job.pk))
        self.assertEqual(payload["store_id"], str(self.store.pk))
        self.assertEqual(payload["user_id"], str(self.owner.pk))
        request = parse_rewrite(payload["rewrite_json"])
        self.assertEqual(request.source_body, self.saved)
        self.assertEqual(request.edited_sha, digest(self.saved))
        self.assertEqual(request.action, "shorten")

    def test_cancel_first_preview_and_idempotent_submission_preserve_saved_text(self) -> None:
        self.assertContains(self.client.get(self.url), "먼저 기존 작업의 취소")
        self.assertEqual(self.preview().status_code, 409)
        self.cancel()
        before = quota_status(self.runner.store, "shop", current_period())
        data = self.confirmation()
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), before)
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            first = self.client.post(self.url, data)
            second = self.client.post(self.url, data)
        self.assertEqual(first.status_code, 302, first.content.decode())
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first["Location"], second["Location"])
        self.assertEqual(Job.objects.count(), 2)
        new = Job.objects.exclude(pk=self.job.pk).get()
        request = parse_rewrite(new.inputs["rewrite_json"])
        self.assertEqual(request.source_run_id, self.job.run_id)
        self.assertEqual(request.source_body, self.saved)
        self.assertEqual(request.revision, 1)
        self.assertEqual(request.action, "shorten")
        self.assertEqual(EditDraft.objects.get(job=self.job).body, self.saved)
        self.assertTrue(self.tick())
        new.refresh_from_db()
        self.assertEqual(new.state, "waiting_approval")
        self.assertEqual(quota_status(self.runner.store, "shop", current_period())["draft_used"], 2)

    def test_price_change_becomes_new_fact_provenance_and_requires_owner_check(self) -> None:
        self.cancel()
        fact = "신메뉴 라떼 6500원, 9월 10일부터 판매합니다."
        self.assertEqual(self.preview(fact=fact).status_code, 409)
        self.assertEqual(self.preview(action="price", fact=fact, checked="").status_code, 400)
        response = self.preview(action="price", fact=fact)
        self.assertContains(response, fact)
        data = {
            "stage": "confirm",
            "checked": "on",
            "token": response.context["confirmation"].initial["token"],
        }
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
        new = Job.objects.exclude(pk=self.job.pk).get()
        self.assertEqual(json.loads(new.inputs["brief_json"])["facts"], [fact])
        self.assertEqual(parse_rewrite(new.inputs["rewrite_json"]).facts_sha, facts_sha([fact]))
        self.assertEqual(json.loads(self.job.inputs["brief_json"])["facts"], [self.fact])

    def test_stale_version_and_changed_source_do_not_submit(self) -> None:
        self.cancel()
        data = self.confirmation()
        EditDraft.objects.filter(job=self.job).update(revision=2)
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.assertEqual(Job.objects.count(), 1)
        EditDraft.objects.filter(job=self.job).update(revision=1)
        path = self.root / f"artifacts/{self.job.run_id}/local-pack.json"
        path.write_text("{}", encoding="utf-8")
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.assertEqual(Job.objects.count(), 1)

    def test_original_photo_is_reused_with_exact_rights_and_hash(self) -> None:
        self.cancel()
        photo_json = photos.store_photo(
            self.store, normalize_photo(upload().read()), "합성 가게 내부", "own_photo"
        )
        self.job = services.submit(
            self.store,
            uuid.uuid4(),
            self.job.inputs["brief_json"],
            photos_json=photo_json,
            actor=self.owner,
        )
        self.assertTrue(self.tick())
        self.cancel()
        self.url = f"/jobs/{self.job.id}/rewrite/"
        response = self.preview(action="friendly")
        self.assertContains(response, f"/jobs/{self.job.id}/photo/")
        data = {
            "stage": "confirm",
            "checked": "on",
            "token": response.context["confirmation"].initial["token"],
        }
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            result = self.client.post(self.url, data)
        self.assertEqual(result.status_code, 302, result.content.decode())
        new = Job.objects.get(state="queued")
        self.assertEqual(new.inputs["photos_json"], photo_json)
        self.assertEqual(parse_rewrite(new.inputs["rewrite_json"]).action, "friendly")
        self.assertTrue(self.tick())
        new.refresh_from_db()
        self.assertEqual(new.state, "waiting_approval")

    def test_large_korean_source_uses_compressed_confirmation_within_http_limit(self) -> None:
        text = "".join(chr(0xAC00 + index) for index in range(1000))
        editor.save(
            self.job,
            self.runner,
            digest(self.base.model_dump_json()),
            1,
            {
                **editable_values(self.original),
                "news_0_title": text,
                "news_0_body": text[::-1],
                "reply_0": text,
            },
            actor=self.owner,
        )
        self.cancel()
        data = self.confirmation()
        self.assertTrue(data["token"].startswith("."))
        self.assertLess(len(urlencode(data).encode("utf-8")), 64 * 1024)
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            self.assertEqual(self.client.post(self.url, data).status_code, 302)

    def test_quota_and_confirmation_gate_block_without_new_job(self) -> None:
        self.cancel()
        data = self.confirmation()
        self.assertEqual(self.client.post(self.url, {**data, "checked": ""}).status_code, 409)
        configure_quota(self.runner.store, "shop", current_period(), 3, 1)
        with patch("aicmo.store_app.services.engine", side_effect=AssertionError):
            self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.assertEqual(Job.objects.count(), 1)

    def test_other_owner_and_tampered_token_never_read_source_or_submit(self) -> None:
        self.cancel()
        data = self.confirmation()
        other = User.objects.create_user("rewrite-other")
        self.client.force_login(other)
        with patch("aicmo.store_app.rewrites.source", side_effect=AssertionError):
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url, data).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(self.url, {**data, "token": data["token"] + "x"}).status_code, 409
        )
        self.assertEqual(Job.objects.count(), 1)

    def test_unsafe_or_duplicate_preview_input_is_not_reflected(self) -> None:
        self.cancel()
        secret = "비밀번호: synthetic-rewrite-secret"
        response = self.preview(action="price", fact=secret)
        self.assertEqual(response.status_code, 409)
        self.assertNotContains(response, secret, status_code=409)
        self.assertEqual(
            self.client.post(
                self.url,
                "stage=preview&action=shorten&action=price",
                content_type="application/x-www-form-urlencoded",
            ).status_code,
            409,
        )
        self.assertEqual(Job.objects.count(), 1)
