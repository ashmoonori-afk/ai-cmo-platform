from __future__ import annotations

import json

# Django owns isolation; all accounts/files below are synthetic.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core import signing
from django.http import Http404
from django.test import TransactionTestCase, override_settings

from aicmo.local_pack import LocalPack, PackBrief, parse_brief
from aicmo.pack_edits import digest, editable_values, inspect_base
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.runner import WorkflowRunner
from aicmo.store_app import editor, onboarding, rewrites, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import EditDraft, EditVersion, Job, OnboardingDraft, Store
from aicmo.web_run_lock import web_run_lock
from tests.store_onboarding_cases import STEPS
from tests.store_photo_cases import upload
from tests.test_local_pack import _brief, _runner  # pyright: ignore[reportPrivateUsage]


class AuthorityTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        configure_quota(self.runner.store, "shop", current_period(), 2, 4)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("authority-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)

    def wait_for_owner(self) -> Job:
        brief = json.loads(_brief(reviews=1)["brief_json"])
        brief["facts"] = brief["facts"][:1]
        job = services.submit(self.store, uuid.uuid4(), json.dumps(brief), actor=self.owner)
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertEqual(job.state, "waiting_approval")
        return job

    @contextmanager
    def revoke_before_lock_yields(self, change: Callable[[], None]) -> Iterator[None]:
        @contextmanager
        def changed_lock(repo: Path, run_id: str, *, blocking: bool = True) -> Iterator[None]:
            with web_run_lock(repo, run_id, blocking=blocking):
                change()  # A committed DB change in the gap before the write transaction.
                yield

        with patch("aicmo.store_app.editor.web_run_lock", side_effect=changed_lock):
            yield

    def test_create_rechecks_account_before_persistence(self) -> None:
        def revoke() -> WorkflowRunner:
            User.objects.filter(pk=self.owner.pk).update(is_active=False)
            return self.runner

        with patch("aicmo.store_app.services.engine", side_effect=revoke):
            response = self.client.post(
                f"/stores/{self.store.pk}/new/",
                {
                    "submission_key": str(uuid.uuid4()),
                    "fact": "이번 주 평소대로 영업합니다.",
                    "reviews": "",
                    "owner_minutes": "20",
                },
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Job.objects.count(), 0)

    def test_photo_persistence_and_job_submission_recheck_their_own_boundaries(self) -> None:
        data = {
            "submission_key": str(uuid.uuid4()),
            "fact": "평소대로 영업합니다.",
            "reviews": "",
            "owner_minutes": "20",
            "photo": upload(),
            "photo_caption": "합성 가게",
            "photo_rights": "own_photo",
            "photo_privacy": "on",
        }
        other = User.objects.create_user("authority-next-owner")

        def transfer() -> WorkflowRunner:
            Store.objects.filter(pk=self.store.pk).update(owner=other)
            return self.runner

        with patch("aicmo.store_app.services.engine", side_effect=transfer):
            self.assertEqual(
                self.client.post(f"/stores/{self.store.pk}/new/", data).status_code, 404
            )
        self.assertEqual(list(self.root.rglob("*.png")), [])
        Store.objects.filter(pk=self.store.pk).update(owner=self.owner)
        original_parse = parse_brief

        def transfer_after_photo(inputs: dict[str, str]) -> PackBrief:
            transfer()
            return original_parse(inputs)

        data["photo"] = upload()
        with (
            patch("aicmo.store_app.services.engine", return_value=self.runner),
            patch("aicmo.store_app.services.parse_brief", side_effect=transfer_after_photo),
        ):
            self.assertEqual(
                self.client.post(f"/stores/{self.store.pk}/new/", data).status_code, 404
            )
        self.assertEqual(len(list(self.root.rglob("*.png"))), 1)
        self.assertEqual(Job.objects.count(), 0)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period())["draft_used"], 0)
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/stores/{self.store.pk}/new/").status_code, 200)

    def test_edit_save_checkpoint_restore_and_confirmation_use_current_authority(self) -> None:
        job = self.wait_for_owner()
        base, pack = inspect_base(self.runner, job.run_id)
        token = digest(base.model_dump_json())
        values = {**editable_values(pack), "news_0_title": "사장님 수정"}

        def deactivate() -> None:
            User.objects.filter(pk=self.owner.pk).update(is_active=False)

        with self.revoke_before_lock_yields(deactivate), self.assertRaises(Http404):
            editor.save(job, self.runner, token, 0, values, actor=self.owner)
        self.assertFalse(EditDraft.objects.exists())
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        draft = editor.save(job, self.runner, token, 0, values, actor=self.owner)
        before = EditDraft.objects.values().get(pk=draft.pk)
        other = User.objects.create_user("authority-edit-owner")

        def transfer() -> None:
            Store.objects.filter(pk=self.store.pk).update(owner=other)

        with self.revoke_before_lock_yields(transfer), self.assertRaises(Http404):
            editor.save(
                job, self.runner, token, draft.revision, values, actor=self.owner, checkpoint=True
            )
        self.assertEqual(EditDraft.objects.values().get(pk=draft.pk), before)
        Store.objects.filter(pk=self.store.pk).update(owner=self.owner)
        operator = User.objects.create_user("authority-edit-operator")
        permission = Permission.objects.get(codename="operate_stores")
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        self.assertTrue(services.allowed_stores(operator).exists())  # Prime the permission cache.

        def revoke() -> None:
            operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]

        versions = EditVersion.objects.count()
        with self.revoke_before_lock_yields(revoke), self.assertRaises(Http404):
            editor.save(job, self.runner, token, draft.revision, actor=operator, restore=0)
        self.assertEqual(EditDraft.objects.values().get(pk=draft.pk), before)
        self.assertEqual(EditVersion.objects.count(), versions)
        with self.revoke_before_lock_yields(deactivate), self.assertRaises(Http404):
            editor.confirm(job, self.runner, draft.revision, token, digest(draft.body), self.owner)
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        editor.confirm(job, self.runner, draft.revision, token, digest(draft.body), self.owner)
        job.refresh_from_db()
        approval = job.approval
        with self.revoke_before_lock_yields(transfer), self.assertRaises(Http404):
            editor.confirm(job, self.runner, draft.revision, token, digest(draft.body), self.owner)
        job.refresh_from_db()
        self.assertEqual(job.approval, approval)

    def test_edit_confirmation_replay_rechecks_current_store_and_inputs(self) -> None:
        job = self.wait_for_owner()
        base, pack = inspect_base(self.runner, job.run_id)
        base_token = digest(base.model_dump_json())
        draft = editor.save(
            job, self.runner, base_token, 0, editable_values(pack), actor=self.owner
        )
        url = f"/jobs/{job.pk}/edit/confirm/"
        data = {
            "revision": draft.revision,
            "base_token": base_token,
            "edited_sha": digest(draft.body),
            "checked": "on",
        }
        self.assertEqual(self.client.post(url, data).status_code, 302)
        job.refresh_from_db()
        approval = job.approval
        self.assertEqual(self.client.post(url, data).status_code, 302)
        for change in ("store", "inputs"):
            with self.subTest(change=change):
                if change == "store":
                    Store.objects.filter(pk=self.store.pk).update(client="different-client")
                else:
                    brief = {**json.loads(job.inputs["brief_json"]), "owner_minutes": 5}
                    Job.objects.filter(pk=job.pk).update(
                        inputs={**job.inputs, "brief_json": json.dumps(brief)}
                    )
                try:
                    self.assertEqual(self.client.post(url, data).status_code, 404)
                finally:
                    Store.objects.filter(pk=self.store.pk).update(client=self.store.client)
                    Job.objects.filter(pk=job.pk).update(inputs=job.inputs)
        job.refresh_from_db()
        self.assertEqual(job.approval, approval)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(EditDraft.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 1)

    def test_original_approval_cancel_and_submission_replays_require_current_owner(self) -> None:
        job = self.wait_for_owner()
        original_preview = services.preview

        def deactivate_after_preview(value: Job) -> tuple[LocalPack, str, str]:
            result = original_preview(value)
            User.objects.filter(pk=self.owner.pk).update(is_active=False)
            return result

        _, pack_sha, photo_sha = original_preview(job)
        with (
            patch("aicmo.store_app.services.preview", side_effect=deactivate_after_preview),
            self.assertRaises(Http404),
        ):
            services.request_approval(job, pack_sha, photo_sha, self.owner)
        job.refresh_from_db()
        self.assertEqual(job.approval, {})
        self.assertEqual(job.state, "waiting_approval")
        with self.assertRaises(Http404):
            services.request_cancel(job, self.owner)
        with self.assertRaises(Http404):
            services.submit(
                self.store, job.submission_key, job.inputs["brief_json"], actor=self.owner
            )
        job.refresh_from_db()
        self.assertFalse(job.cancel_requested)
        self.assertEqual(Job.objects.count(), 1)
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        services.request_cancel(job, self.owner)
        job.refresh_from_db()
        self.assertTrue(job.cancel_requested)

    def test_rewrite_and_replay_reject_revoked_operator_without_an_extra_job(self) -> None:
        job = self.wait_for_owner()
        services.request_cancel(job, self.owner)
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertEqual(job.state, "cancelled")
        operator = User.objects.create_user("authority-rewrite-operator")
        permission = Permission.objects.get(codename="operate_stores")
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        self.assertTrue(services.allowed_stores(operator).exists())
        form = rewrites.RewriteForm(
            {"action": "friendly", "fact": parse_brief(job.inputs).facts[0], "checked": "on"}
        )
        self.assertTrue(form.is_valid())
        payload = rewrites.prepare(job, self.runner, form, str(operator.pk))
        token = signing.dumps(payload, salt="aicmo.web-rewrite.v1", compress=True)
        before = quota_status(self.runner.store, "shop", current_period())

        def revoke() -> WorkflowRunner:
            operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
            return self.runner

        with (
            patch("aicmo.store_app.services.engine", side_effect=revoke),
            self.assertRaises(Http404),
        ):
            rewrites.submit(job, self.runner, token, operator)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), before)
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            created = rewrites.submit(job, self.runner, token, operator)
        self.assertEqual(rewrites.submit(job, self.runner, token, operator).pk, created.pk)
        revoke()
        with self.assertRaises(Http404):
            rewrites.submit(job, self.runner, token, operator)
        self.assertEqual(Job.objects.count(), 2)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), before)

    def test_rewrite_rechecks_store_client_after_source_validation(self) -> None:
        job = self.wait_for_owner()
        services.request_cancel(job, self.owner)
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            self.assertTrue(run_one())
        job.refresh_from_db()
        form = rewrites.RewriteForm(
            {"action": "shorten", "fact": parse_brief(job.inputs).facts[0], "checked": "on"}
        )
        self.assertTrue(form.is_valid())
        payload = rewrites.prepare(job, self.runner, form, str(self.owner.pk))
        token = signing.dumps(payload, salt="aicmo.web-rewrite.v1", compress=True)
        before = quota_status(self.runner.store, "shop", current_period())

        def change_client() -> WorkflowRunner:
            Store.objects.filter(pk=self.store.pk).update(client="different-client")
            return self.runner

        with (
            patch("aicmo.store_app.services.engine", side_effect=change_client),
            self.assertRaises(Http404),
        ):
            rewrites.submit(job, self.runner, token, self.owner)
        self.assertEqual(Job.objects.count(), 1)
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), before)
        Store.objects.filter(pk=self.store.pk).update(client=self.store.client)
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            created = rewrites.submit(job, self.runner, token, self.owner)
        self.assertEqual(created.inputs["client"], "shop")
        self.assertEqual(rewrites.submit(job, self.runner, token, self.owner).pk, created.pk)

    def test_onboarding_stale_actor_and_new_store_never_change_saved_draft(self) -> None:
        permission = Permission.objects.get(codename="operate_stores")
        for action in ("save", "confirm"):
            for change in ("inactive", "operator", "store"):
                actor = User.objects.create_user(f"authority-onboard-{action}-{change}")
                draft = None
                for step, values in STEPS.items():
                    draft = onboarding.save_step(
                        actor, step, draft.revision if draft else 0, values, completed=True
                    )
                assert draft is not None
                self.assertTrue(onboarding.new_owner(actor))
                before = OnboardingDraft.objects.values().get(pk=draft.pk)
                if change == "inactive":
                    User.objects.filter(pk=actor.pk).update(is_active=False)
                elif change == "operator":
                    actor.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
                else:
                    Store.objects.create(owner=actor, name="새 연결", client=f"linked-{actor.pk}")
                with self.assertRaises((Http404, services.StoreActionError)):
                    if action == "save":
                        onboarding.save_step(
                            actor, 1, draft.revision, {"company_name": "바뀐 이름"}, completed=True
                        )
                    else:
                        onboarding.confirm(actor, draft.revision)
                self.assertEqual(OnboardingDraft.objects.values().get(pk=draft.pk), before)
