from __future__ import annotations

# Django owns isolation and assertions; all owners and marketing text are synthetic.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.http import QueryDict
from django.test import TransactionTestCase, override_settings

from aicmo.pack_edits import digest, editable_values, inspect_base
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.runner import WorkflowRunner
from aicmo.store_app import editor, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import EditDraft, EditVersion, Job, Store
from aicmo.web_run_lock import web_run_lock
from tests.test_local_pack import (
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


class EditorTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("editor-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        configure_quota(self.runner.store, "shop", current_period(), 2, 4)
        self.job = services.submit(
            self.store, uuid.uuid4(), _brief()["brief_json"], actor=self.owner
        )
        self.assertTrue(self.tick())
        self.job.refresh_from_db()
        self.url = f"/jobs/{self.job.id}/edit/"
        self.base, self.original = inspect_base(self.runner, self.job.run_id)
        self.source = self.root / f"artifacts/{self.job.run_id}/local-pack.json"
        self.original_bytes = self.source.read_bytes()

    def tick(self) -> bool:
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            return run_one()

    def data(self, revision: int = 0, **values: str) -> dict[str, str]:
        return {
            **editable_values(self.original),
            "revision": str(revision),
            "base_token": digest(self.base.model_dump_json()),
            "action": "checkpoint",
            **values,
        }

    def confirmation(self) -> dict[str, str]:
        draft = EditDraft.objects.get(job=self.job)
        return {
            "revision": str(draft.revision),
            "base_token": digest(self.base.model_dump_json()),
            "edited_sha": digest(draft.body),
            "checked": "on",
        }

    def test_edit_confirm_and_exact_delivery(self) -> None:
        self.assertContains(self.client.get(self.url), "문안 고치기")
        self.assertEqual(EditDraft.objects.count(), 0)
        self.assertEqual(
            self.client.post(self.url, self.data(news_0_title="사장님이 고친 안내")).status_code,
            302,
        )
        draft = EditDraft.objects.get()
        self.assertEqual(draft.revision, 1)
        self.assertEqual(
            list(EditVersion.objects.order_by("revision").values_list("revision", flat=True)),
            [0, 1],
        )
        self.assertEqual(self.source.read_bytes(), self.original_bytes)
        self.assertContains(self.client.get(self.url + "confirm/"), "사장님이 고친 안내")
        _, pack_sha, photo_sha = services.preview(self.job)
        self.assertEqual(
            self.client.post(
                f"/jobs/{self.job.id}/approve/",
                {"pack_sha": pack_sha, "photo_sha": photo_sha, "checked": "on"},
            ).status_code,
            409,
        )
        confirmation = self.confirmation()
        self.assertEqual(self.client.post(self.url + "confirm/", confirmation).status_code, 302)
        self.assertEqual(self.client.post(self.url + "confirm/", confirmation).status_code, 302)
        self.assertEqual(
            self.client.post(self.url, self.data(1, news_0_title="수정하면 안 됨")).status_code, 409
        )
        self.assertTrue(self.tick())
        self.job.refresh_from_db()
        self.assertEqual(self.job.state, "success")
        self.assertIn("사장님이 고친 안내", self.source.read_text(encoding="utf-8"))
        self.assertTrue(services.download(self.job).is_file())
        self.assertEqual(self.runner.store.get_step_attempt(self.job.run_id, "drafts"), 1)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period())["draft_used"], 1)

    def test_autosave_replay_conflict_relogin_and_restore(self) -> None:
        data = self.data(news_0_body="사장님이 저장한 안내입니다.", action="autosave")
        for _ in range(2):
            response = self.client.post(self.url, data, HTTP_ACCEPT="application/json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["revision"], 1)
        self.assertEqual(EditVersion.objects.count(), 1)
        conflict = self.client.post(self.url, self.data(news_0_body="다른 창에 남아야 할 문안"))
        self.assertContains(conflict, "다른 창에 남아야 할 문안", status_code=409)
        self.client.logout()
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(self.url), "사장님이 저장한 안내입니다.")
        restore = {"revision": "1", "base_token": data["base_token"], "version": "0"}
        self.assertEqual(self.client.post(self.url + "restore/", restore).status_code, 302)
        self.assertEqual(self.client.post(self.url + "restore/", restore).status_code, 302)
        draft = EditDraft.objects.get()
        self.assertEqual(draft.revision, 2)
        self.assertEqual(json.loads(draft.body)["news"][0]["body"], self.original.news[0].body)
        self.assertEqual(EditVersion.objects.count(), 3)

    def test_private_duplicate_and_protected_input_are_not_saved_or_echoed(self) -> None:
        secret = "비밀번호: synthetic-editor-private-value"
        for changes in (
            {"news_0_body": secret},
            {"news_0_body": "숨은\u2028문자"},
            {"source_index": "1"},
        ):
            response = self.client.post(self.url, {**self.data(), **changes})
            self.assertEqual(response.status_code, 409)
            self.assertNotContains(response, secret, status_code=409)
        self.assertEqual(
            self.client.post(
                self.url, "revision=0&revision=1", content_type="application/x-www-form-urlencoded"
            ).status_code,
            409,
        )
        self.assertFalse(EditDraft.objects.exists())
        self.assertFalse(EditVersion.objects.exists())
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_hash_and_revision_are_not_redacted_as_customer_phone_numbers(self) -> None:
        post = QueryDict(mutable=True)
        post.update({**self.data(), "base_token": "a" * 53 + "01012345678", "revision": "15881234"})
        form = editor.submitted_form(editor.EditForm(self.original), post)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["base_token"], post["base_token"])
        self.assertEqual(form.cleaned_data["revision"], 15881234)
        for name, value in (("base_token", "비밀번호: do-not-reflect"), ("revision", "NaN")):
            post[name] = value
            with self.assertRaises(services.StoreActionError):
                editor.submitted_form(editor.EditForm(self.original), post)

    def test_other_owner_cannot_read_save_restore_or_confirm(self) -> None:
        other = User.objects.create_user("editor-other")
        self.client.force_login(other)
        with patch("aicmo.store_app.editor.inspect_base", side_effect=AssertionError):
            for url in (self.url, self.url + "confirm/", self.url + "restore/"):
                self.assertEqual(self.client.post(url, self.data()).status_code, 404)
            self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertFalse(EditDraft.objects.exists())

    def test_stale_confirmation_and_changed_base_do_not_approve(self) -> None:
        self.client.post(self.url, self.data(news_0_title="첫 수정"))
        confirmation = self.confirmation()
        self.client.post(self.url, self.data(1, news_0_title="두 번째 수정"))
        self.assertEqual(self.client.post(self.url + "confirm/", confirmation).status_code, 409)
        source = self.root / "agents/copywriter.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
        self.assertEqual(self.client.get(self.url).status_code, 409)
        self.assertEqual(
            self.client.post(self.url + "confirm/", self.confirmation()).status_code, 409
        )
        self.job.refresh_from_db()
        self.assertEqual(self.job.approval, {})
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_checkpoint_limit_preserves_current_draft_and_allows_confirmation(self) -> None:
        self.client.post(self.url, self.data(news_0_title="버전으로 보관"))
        with patch("aicmo.store_app.editor.MAX_CHECKPOINTS", 2):
            latest = self.data(1, news_0_title="자동저장은 계속 유지", action="autosave")
            self.assertEqual(
                self.client.post(self.url, latest, HTTP_ACCEPT="application/json").status_code, 200
            )
            self.assertEqual(
                self.client.post(
                    self.url, self.data(2, news_0_title="자동저장은 계속 유지")
                ).status_code,
                409,
            )
            self.assertEqual(EditVersion.objects.count(), 2)
            self.assertEqual(
                self.client.post(self.url + "confirm/", self.confirmation()).status_code, 302
            )

    def test_cancel_before_confirm_and_during_interrupted_apply(self) -> None:
        response = self.client.post(self.url, self.data(news_0_title="취소와 경합하는 수정"))
        self.assertEqual(response.status_code, 302, response.content.decode())
        Job.objects.filter(pk=self.job.pk).update(cancel_requested=True)
        self.assertEqual(
            self.client.post(self.url + "confirm/", self.confirmation()).status_code, 409
        )
        Job.objects.filter(pk=self.job.pk).update(cancel_requested=False)
        self.assertEqual(
            self.client.post(self.url + "confirm/", self.confirmation()).status_code, 302
        )

        class Crash(BaseException):
            pass

        original_write = WorkflowRunner._write_pack_edit  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        def interrupt(path: Path, body: str) -> None:
            original_write(path, body)
            raise Crash

        with (
            patch.object(WorkflowRunner, "_write_pack_edit", staticmethod(interrupt)),
            self.assertRaises(Crash),
        ):
            self.tick()
        self.assertEqual(self.client.post(f"/jobs/{self.job.id}/cancel/").status_code, 302)
        with patch("aicmo.store_app.management.commands.work.engine", side_effect=AssertionError):
            self.assertTrue(run_one())  # Cancellation must not configure or call a provider.
        self.job.refresh_from_db()
        self.assertEqual(self.job.state, "cancelled")
        self.assertEqual(
            self.runner.store.get_output_hashes(self.job.run_id, "drafts")[
                f"artifacts/{self.job.run_id}/local-pack.json"
            ],
            digest(EditDraft.objects.get().body),
        )
        self.assertEqual(self.runner.store.get_step_attempt(self.job.run_id, "drafts"), 1)
        with self.runner.store.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "select state from pack_edit_receipts where run_id=?", (self.job.run_id,)
                ).fetchone()[0],
                "applied",
            )
        quota = quota_status(self.runner.store, "shop", current_period())
        self.assertEqual(quota["draft_used"], 1)
        self.assertEqual(
            quota["packs"],
            {
                "reserved": 0,
                "consumed": 0,
                "released": 1,
                "credited": 0,
                "unmetered": 0,
            },
        )
        self.assertEqual(self.client.post(f"/jobs/{self.job.id}/download/").status_code, 409)

    def test_no_javascript_safe_input_survives_busy_lock_and_changed_base(self) -> None:
        entered, release = Event(), Event()

        def hold_lock() -> None:
            with web_run_lock(self.root, self.job.run_id):
                entered.set()
                self.assertTrue(release.wait(10))

        text = "입력 보존 <script>alert('synthetic')</script>"
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(hold_lock)
            self.assertTrue(entered.wait(10))
            try:
                response = self.client.post(self.url, self.data(news_0_body=text))
                self.assertContains(response, "입력 보존 &lt;script&gt;", status_code=409)
                self.assertNotContains(response, text, status_code=409)
            finally:
                release.set()
            pending.result(timeout=10)
        source = self.root / "agents/copywriter.md"
        source.write_text(source.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
        response = self.client.post(self.url, self.data(news_0_body=text))
        self.assertContains(response, "입력 보존 &lt;script&gt;", status_code=409)
        self.assertFalse(EditDraft.objects.exists())
        self.assertEqual(self.source.read_bytes(), self.original_bytes)

    def test_first_save_and_legacy_approval_cannot_mix(self) -> None:
        entered, release = Event(), Event()
        checkpoint = editor._checkpoint  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        _, pack_sha, photo_sha = services.preview(self.job)

        def pause(draft: EditDraft) -> None:
            checkpoint(draft)
            entered.set()
            self.assertTrue(release.wait(10))

        def save() -> None:
            try:
                job = Job.objects.get(pk=self.job.pk)
                editor.save(
                    job,
                    self.runner,
                    digest(self.base.model_dump_json()),
                    0,
                    {**editable_values(self.original), "news_0_title": "최초 수정"},
                    actor=self.owner,
                )
            finally:
                close_old_connections()

        with (
            patch("aicmo.store_app.editor._checkpoint", side_effect=pause),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            pending = pool.submit(save)
            self.assertTrue(entered.wait(10))
            try:
                with self.assertRaises(OSError):
                    services.request_approval(self.job, pack_sha, photo_sha, self.owner)
            finally:
                release.set()
            pending.result(timeout=10)
        with self.assertRaises(services.StoreActionError):
            services.request_approval(self.job, pack_sha, photo_sha, self.owner)
        self.job.refresh_from_db()
        self.assertEqual(self.job.approval, {})
        self.assertEqual(self.job.state, "waiting_approval")
        self.assertEqual(EditDraft.objects.count(), 1)
