from __future__ import annotations

# Real approved packs, Django jobs and the existing learning ledger; synthetic data only.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import hashlib
import json
import re
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core import signing
from django.db import DatabaseError, connection
from django.http import Http404, QueryDict
from django.test import Client, TransactionTestCase, override_settings

from aicmo import outcomes
from aicmo.errors import WorkflowExecutionError
from aicmo.export import verified_delivery
from aicmo.learning import PackFeedback, feedback_report, learning_context
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.source_input import source_checked_date
from aicmo.store import WorkflowStore
from aicmo.store_app import feedback_services, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, Store
from tests.test_delivery_manifest import PassReviewer
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _content,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

REPO = Path(__file__).resolve().parents[1]
INSIGHT = "안내 문안의 CTA는 한 문장으로 짧게 씁니다."
SECRET = "sk-syntheticFeedbackSecretNeverReflect123456789"


class FeedbackTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        for relative in (
            "workflows/weekly-report.workflow.yaml",
            "workflows/local-pack-feedback.workflow.yaml",
            "playbooks/06-analytics/weekly-report.md",
            "playbooks/07-operations/local-pack-feedback.md",
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        configured = patch.dict(
            "os.environ", {"AICMO_WEB_REVIEW_CMD": '["synthetic-review-not-executed"]'}
        )
        configured.start()
        self.addCleanup(configured.stop)
        self.owner = User.objects.create_user("feedback-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        configure_quota(self.runner.store, "shop", current_period(), 3, 3)
        self.brief = _brief(minutes=5, photos=False, reviews=0)["brief_json"]
        self.source = self.source_pack()
        self.today = source_checked_date()
        self.day = self.today.isoformat()
        self.week = (self.today - timedelta(days=self.today.weekday())).isoformat()
        self.create_url = f"/jobs/{self.source.pk}/feedback/news-1/"

    def tick(self, job: Job, *, verdict: str = "PASS") -> None:
        runner = replace(self.runner, review_adapter=PassReviewer(verdict))
        with patch("aicmo.store_app.management.commands.work.engine", return_value=runner):
            self.assertTrue(run_one())
        job.refresh_from_db()

    def source_pack(self, *, approve: bool = True) -> Job:
        job = services.submit(self.store, uuid.uuid4(), self.brief, actor=self.owner)
        self.tick(job)
        self.assertEqual(job.state, "waiting_approval")
        if approve:
            _, pack_sha, photo_sha = services.preview(job)
            services.request_approval(job, pack_sha, photo_sha, self.owner)
            self.tick(job)
            self.assertEqual(job.state, "success")
        return job

    def data(self, source: Job | None = None, **changes: str) -> dict[str, str]:
        url = f"/jobs/{(source or self.source).pk}/feedback/news-1/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return {
            "token": str(response.context["form"]["token"].value()),
            "observed_on": self.day,
            "adoption": "used",
            "reason": "승인한 영업 안내를 그대로 사용했다고 기록했습니다.",
            "insight": INSIGHT,
            "weekly_report": "",
            "checked": "on",
            "csrfmiddlewaretoken": self.csrf(response.content.decode(), "feedback-form"),
            **changes,
        }

    def csrf(self, html: str, form_id: str) -> str:
        forms = re.findall(
            rf'<form id="{re.escape(form_id)}"[^>]*>(.*?)</form>', html, flags=re.DOTALL
        )
        self.assertEqual(len(forms), 1)
        tokens = re.findall(r'name="csrfmiddlewaretoken" value="([^"]+)"', forms[0])
        self.assertEqual(len(tokens), 1)
        return tokens[0]

    def submit(self, data: dict[str, str] | None = None) -> Job:
        response = self.client.post(self.create_url, data or self.data())
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get(pk=response.headers["Location"].split("/")[2])
        self.assertEqual(job.workflow_id, "local-pack-feedback")
        return job

    def detail_url(self, job: Job) -> str:
        return f"/jobs/{job.pk}/feedback/"

    def candidate(self, job: Job) -> dict[str, str]:
        self.tick(job)
        self.assertEqual(job.state, "waiting_approval")
        shown = self.client.get(self.detail_url(job))
        self.assertEqual(shown.status_code, 200)
        raw, digest = services.feedback_candidate(job)
        self.assertEqual(shown.context["candidate"], json.loads(raw))
        self.assertEqual(shown.context["candidate_sha256"], hashlib.sha256(raw).hexdigest())
        return {
            "candidate_sha256": digest,
            "checked": "on",
            "csrfmiddlewaretoken": self.csrf(shown.content.decode(), "feedback-approve-form"),
        }

    def no_learning(self) -> None:
        self.assertFalse((self.root / "knowledge-base/shop/approved-feedback.md").exists())
        self.assertEqual(json.loads(learning_context(self.runner, "shop"))["insights"], [])
        self.assertEqual(self.learned_count(), 0)

    def learned_count(self) -> int:
        with self.runner.store.connect() as ledger:
            return cast(
                "int", ledger.execute("select count(*) from learned_feedback").fetchone()[0]
            )

    def reject_reconnected_store(self, job: Job, action: Callable[[], object]) -> None:
        initial = job.store  # Prime the exact caller's Store cache before the write begins.
        self.assertEqual((initial.pk, initial.client), (self.store.pk, "shop"))
        other, _ = Store.objects.get_or_create(
            client="other-shop", defaults={"owner": self.owner, "name": "같은 사장님의 다른 가게"}
        )
        before = list(Job.objects.order_by("pk").values())
        fresh = services.fresh_actor

        def reconnected(actor: AbstractBaseUser | AnonymousUser) -> User:
            self.assertTrue(connection.in_atomic_block)
            Store.objects.filter(pk=initial.pk).update(client="previous-shop")
            Store.objects.filter(pk=other.pk).update(client="shop")
            Job.objects.filter(pk=job.pk).update(store=other)
            current_actor = fresh(actor)
            self.assertEqual(
                services.allowed_stores(current_actor)
                .filter(pk__in=[initial.pk, other.pk])
                .count(),
                2,
            )
            moved = services.owned_job(current_actor, job.pk)
            self.assertEqual((moved.store.pk, moved.store.client), (other.pk, "shop"))
            self.assertEqual((job.store.pk, job.store.client), (initial.pk, "shop"))
            self.assertEqual(moved.inputs, job.inputs)
            return current_actor

        with (
            patch("aicmo.store_app.services.fresh_actor", side_effect=reconnected),
            self.assertRaises(Http404),
        ):
            action()
        self.assertEqual(list(Job.objects.order_by("pk").values()), before)
        self.no_learning()

    def report(self, *, channel: outcomes.Channel = "naver", week: str | None = None) -> Job:
        selected_week = week or self.week
        raw = outcomes.daily_outcome_csv(
            outcomes.DailyOutcome(
                date=self.day if selected_week == self.week else selected_week,
                channel=channel,
                posts=1,
            )
        )
        preview = outcomes.preview_outcomes_bytes(
            self.root, self.runner.store, "shop", selected_week, channel, raw
        )
        outcomes.import_outcomes_bytes(
            self.root,
            self.runner.store,
            "shop",
            selected_week,
            channel,
            raw,
            preview.confirmation_sha256,
            provenance=outcomes.OutcomeImportSource(
                kind="web_manual", recorded_by=f"web-user:{self.owner.pk}"
            ),
        )
        snapshot = outcomes.read_weekly_outcomes(
            self.root, self.runner.store, "shop", selected_week, channel
        )
        job = services.submit_weekly_report(
            self.store,
            uuid.uuid4(),
            selected_week,
            channel,
            snapshot.snapshot_sha256,
            actor=self.owner,
        )
        self.tick(job)
        self.assertEqual(job.state, "success")
        return job

    def test_source_form_is_read_only_and_only_approved_owned_items_are_eligible(self) -> None:
        with WorkflowStore(self.runner.store.db_path, read_only=True).connect() as ledger:
            before = "\n".join(ledger.iterdump())
        with patch("aicmo.store_app.services.engine") as engine:
            data = self.data()
            shown = self.client.get(self.create_url)
            engine.assert_not_called()
        self.assertIn("no-store", shown.headers["Cache-Control"])
        envelope = signing.loads(data["token"], salt=feedback_services.TOKEN_SALT)
        self.assertEqual(
            (envelope["actor_id"], envelope["store_id"], envelope["client"]),
            (self.owner.pk, self.store.pk, "shop"),
        )
        self.assertEqual(envelope["item_key"], "news-1")
        self.assertRegex(envelope["bundle_sha256"], r"^[a-f0-9]{64}$")
        self.assertRegex(envelope["file_sha256"], r"^[a-f0-9]{64}$")
        with WorkflowStore(self.runner.store.db_path, read_only=True).connect() as ledger:
            self.assertEqual("\n".join(ledger.iterdump()), before)
        pending = self.source_pack(approve=False)
        self.assertEqual(self.client.get(f"/jobs/{pending.pk}/feedback/news-1/").status_code, 409)
        self.assertEqual(
            self.client.get(self.create_url.replace("news-1", "reply-5")).status_code, 404
        )
        self.client.force_login(User.objects.create_user("feedback-other-owner"))
        self.assertEqual(self.client.get(self.create_url).status_code, 404)
        self.assertEqual(self.client.post(self.create_url, data).status_code, 404)
        self.no_learning()

    def test_explicit_approval_review_and_learning_replay_feed_only_the_next_pack(self) -> None:
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.owner)
        quota = quota_status(self.runner.store, "shop", current_period())
        data = self.data()
        job = self.submit(data)
        self.assertEqual(self.submit(data).pk, job.pk)
        approval = self.candidate(job)
        url = self.detail_url(job)
        self.no_learning()
        self.assertEqual(self.client.post(url + "learn/", approval).status_code, 409)
        self.assertEqual(self.client.post(url + "approve/", approval).status_code, 302)
        self.assertEqual(self.client.post(url + "approve/", approval).status_code, 302)
        self.assertEqual(self.client.post(url + "learn/", approval).status_code, 409)
        self.tick(job)
        self.assertEqual(job.state, "success")
        self.no_learning()
        shown = self.client.get(url)
        approval["csrfmiddlewaretoken"] = self.csrf(shown.content.decode(), "feedback-learn-form")
        unchecked = {key: value for key, value in approval.items() if key != "checked"}
        self.assertEqual(self.client.post(url + "learn/", unchecked).status_code, 400)
        self.no_learning()
        actual_learn = services.learn_web_feedback

        def response_lost(
            current: Job, candidate_sha256: str, *, actor: AbstractBaseUser | AnonymousUser
        ) -> None:
            actual_learn(current, candidate_sha256, actor=actor)
            raise DatabaseError(SECRET)

        with patch("aicmo.store_app.services.learn_web_feedback", side_effect=response_lost):
            uncertain = self.client.post(url + "learn/", approval)
        self.assertEqual(uncertain.status_code, 409)
        self.assertNotContains(uncertain, SECRET, status_code=409)
        path = self.root / "knowledge-base/shop/approved-feedback.md"
        saved = path.read_bytes()
        self.assertEqual(self.learned_count(), 1)
        activated = json.loads(learning_context(self.runner, "shop"))["insights"][0]
        self.assertEqual(
            (activated["feedback_run_id"], activated["insight"]), (job.run_id, INSIGHT)
        )
        self.assertEqual(self.client.post(url + "learn/", approval).status_code, 302)
        self.assertEqual((path.read_bytes(), saved.count(b"<!-- learned:v1:")), (saved, 1))
        self.assertTrue(self.client.get(url).context["learned"])
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), quota)
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        try:
            with self.assertRaises(Http404):
                services.learn_web_feedback(job, approval["candidate_sha256"], actor=self.owner)
        finally:
            User.objects.filter(pk=self.owner.pk).update(is_active=True)
        following = services.submit(self.store, uuid.uuid4(), self.brief, actor=self.owner)
        self.tick(following)
        context = json.loads(
            (self.root / f"artifacts/{following.run_id}/learning-context.json").read_text("utf-8")
        )
        self.assertEqual(
            tuple(
                context["insights"][0][field]
                for field in ("source_run_id", "feedback_run_id", "insight")
            ),
            (self.source.run_id, job.run_id, INSIGHT),
        )
        self.assertTrue(
            any(
                INSIGHT in ref.content_excerpt
                for ref in cast("PackAdapter", self.runner.adapter).requests[-1].artifact_refs
            )
        )

    def test_invalid_fields_expiry_source_change_and_private_text_never_leak(self) -> None:
        data = self.data()
        for changes, status in (
            ({"checked": ""}, 400),
            ({"adoption": SECRET}, 400),
            ({"observed_on": "2099-01-01"}, 400),
            ({"source_run_id": SECRET}, 400),
            ({"observed_on": (self.today - timedelta(days=1)).isoformat()}, 409),
            ({"token": SECRET}, 409),
            ({"reason": SECRET * 20}, 400),
        ):
            response = self.client.post(self.create_url, {**data, **changes})
            self.assertEqual(response.status_code, status)
            self.assertNotContains(response, SECRET, status_code=status)
        duplicated = QueryDict(mutable=True)
        duplicated.update(data)
        duplicated.appendlist("adoption", SECRET)
        response = self.client.post(
            self.create_url,
            duplicated.urlencode(),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, SECRET, status_code=400)
        with patch(
            "django.core.signing.time.time",
            return_value=time.time() + feedback_services.TOKEN_MAX_AGE + 1,
        ):
            self.assertEqual(self.client.post(self.create_url, data).status_code, 409)
        decode, calls, now = feedback_services.decode, 0, time.time()

        def expires_between_decodes(
            actor: AbstractBaseUser | AnonymousUser, source: Job, item_key: str, token: str
        ) -> feedback_services.SourceConfirmation:
            nonlocal calls
            calls += 1
            if calls == 1:
                return decode(actor, source, item_key, token)
            with patch(
                "django.core.signing.time.time",
                return_value=now + feedback_services.TOKEN_MAX_AGE + 1,
            ):
                return decode(actor, source, item_key, token)

        with patch("aicmo.store_app.feedback_services.decode", side_effect=expires_between_decodes):
            self.assertEqual(self.client.post(self.create_url, data).status_code, 409)
        self.assertEqual(calls, 2)
        path = self.root / f"artifacts/{self.source.run_id}/local-pack.json"
        raw = path.read_bytes()
        try:
            path.write_bytes(raw + SECRET.encode())
            self.assertEqual(self.client.post(self.create_url, data).status_code, 409)
        finally:
            path.write_bytes(raw)
        Store.objects.filter(pk=self.store.pk).update(client="changed-shop")
        try:
            self.assertEqual(self.client.post(self.create_url, data).status_code, 404)
        finally:
            Store.objects.filter(pk=self.store.pk).update(client="shop")
        self.assertEqual(Job.objects.count(), 1)
        masked = self.submit({**data, "reason": f"연락처 010-1234-5678은 제외합니다. {SECRET}"})
        self.assertNotIn(SECRET, json.dumps(masked.inputs))
        self.assertNotIn("010-1234-5678", json.dumps(masked.inputs))
        self.candidate(masked)
        shown = self.client.get(self.detail_url(masked))
        self.assertNotContains(shown, SECRET)
        self.assertNotContains(shown, "010-1234-5678")
        self.no_learning()

    def test_report_selection_is_bound_to_reviewed_bytes_channel_and_observation_week(self) -> None:
        current = self.report()
        other_channel = self.report(channel="instagram")
        previous = self.report(
            week=(self.today - timedelta(days=self.today.weekday() + 7)).isoformat()
        )
        data = self.data(weekly_report=str(current.pk))
        envelope = signing.loads(data["token"], salt=feedback_services.TOKEN_SALT)
        reports = {item["job_id"]: item for item in envelope["reports"]}
        self.assertIn(str(current.pk), reports)
        self.assertNotIn(str(other_channel.pk), reports)
        self.assertEqual(
            self.client.post(
                self.create_url, {**data, "weekly_report": str(other_channel.pk)}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                self.create_url, {**data, "weekly_report": str(previous.pk)}
            ).status_code,
            409,
        )
        path = self.root / f"artifacts/{current.run_id}/weekly-report.md"
        original = path.read_bytes()
        self.assertEqual(reports[str(current.pk)]["sha256"], hashlib.sha256(original).hexdigest())
        try:
            path.write_bytes(original + b" changed")
            self.assertEqual(self.client.post(self.create_url, data).status_code, 409)
        finally:
            path.write_bytes(original)
        other_store = Store.objects.create(
            owner=self.owner, name="다른 합성 가게", client="other-shop"
        )
        Job.objects.filter(pk=current.pk).update(store=other_store)
        try:
            self.assertEqual(self.client.post(self.create_url, data).status_code, 404)
        finally:
            Job.objects.filter(pk=current.pk).update(store=self.store)
        job = self.submit(data)
        self.candidate(job)
        candidate = self.client.get(self.detail_url(job)).context["candidate"]
        self.assertEqual(candidate["outcomes"]["run_id"], current.run_id)
        self.assertEqual(candidate["outcomes"]["sha256"], hashlib.sha256(original).hexdigest())
        self.no_learning()

    def test_fresh_authority_csrf_and_explicit_check_apply_at_every_write_boundary(self) -> None:
        data = self.data()
        feedback = PackFeedback(
            schema_version="aicmo.pack-feedback.v1",
            source_run_id=self.source.run_id,
            item="news-1.txt",
            observed_on=data["observed_on"],
            adoption="used",
            reason=data["reason"],
            insight=data["insight"],
        )
        self.reject_reconnected_store(
            self.source,
            lambda: feedback_services.submit(
                self.owner, self.source, "news-1", data["token"], feedback
            ),
        )
        fresh = services.fresh_actor

        def inactive(actor: AbstractBaseUser | AnonymousUser) -> User:
            self.assertTrue(connection.in_atomic_block)
            User.objects.filter(pk=self.owner.pk).update(is_active=False)
            return fresh(actor)

        with patch("aicmo.store_app.services.fresh_actor", side_effect=inactive):
            self.assertEqual(self.client.post(self.create_url, data).status_code, 404)
        self.assertEqual(Job.objects.count(), 1)
        job = self.submit(data)
        approval = self.candidate(job)
        url = self.detail_url(job)
        self.reject_reconnected_store(
            job,
            lambda: services.request_feedback_approval(
                job, approval["candidate_sha256"], actor=self.owner
            ),
        )
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(self.create_url, data).status_code, 403)
        self.assertEqual(csrf.post(url + "approve/", approval).status_code, 403)
        self.assertEqual(csrf.post(url + "learn/", approval).status_code, 403)
        self.assertEqual(self.client.get(url + "learn/").status_code, 405)
        self.assertEqual(
            self.client.post(
                url + "approve/", {"candidate_sha256": approval["candidate_sha256"]}
            ).status_code,
            400,
        )
        operator = User.objects.create_user("feedback-operator")
        permission = Permission.objects.get(codename="operate_stores")
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        self.assertTrue(services.allowed_stores(operator).exists())
        self.client.force_login(operator)

        def revoked(actor: AbstractBaseUser | AnonymousUser) -> User:
            self.assertTrue(connection.in_atomic_block)
            operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
            return fresh(actor)

        with patch("aicmo.store_app.services.fresh_actor", side_effect=revoked):
            self.assertEqual(self.client.post(url + "approve/", approval).status_code, 404)
        self.assertEqual(self.client.post(url + "approve/", approval).status_code, 302)
        self.tick(job)
        self.reject_reconnected_store(
            job,
            lambda: services.learn_web_feedback(
                job, approval["candidate_sha256"], actor=self.owner
            ),
        )
        with patch("aicmo.store_app.services.fresh_actor", side_effect=revoked):
            self.assertEqual(self.client.post(url + "learn/", approval).status_code, 404)
        operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
        with self.assertRaises(Http404):
            services.learn_web_feedback(job, approval["candidate_sha256"], actor=operator)
        self.no_learning()

    def test_changed_candidate_and_warn_review_never_enter_learning(self) -> None:
        job = self.submit(self.data(adoption="not_recorded"))
        approval = self.candidate(job)
        url = self.detail_url(job)
        path = self.root / f"artifacts/{job.run_id}/feedback.json"
        raw = path.read_bytes()
        try:
            path.write_bytes(raw + SECRET.encode())
            shown = self.client.get(url)
            self.assertEqual(shown.status_code, 409)
            self.assertNotContains(shown, SECRET, status_code=409)
            self.assertEqual(self.client.post(url + "approve/", approval).status_code, 409)
            self.assertEqual(self.client.post(url + "learn/", approval).status_code, 409)
            self.no_learning()
        finally:
            path.write_bytes(raw)
        self.assertEqual(self.client.post(url + "approve/", approval).status_code, 302)
        self.tick(job, verdict="WARN")
        self.assertEqual(job.state, "needs_work")
        self.assertEqual(self.client.post(url + "learn/", approval).status_code, 409)
        Job.objects.filter(pk=job.pk).update(state="success")
        self.assertEqual(self.client.post(url + "learn/", approval).status_code, 409)
        self.no_learning()

    def test_complete_evidence_over_capacity_is_rejected_without_truncation(self) -> None:
        payload = json.loads(_content({"client": "shop", "brief_json": self.brief}))
        payload["news"][0]["body"] = ("이번 주에도 평소대로 운영합니다. " * 60)[:1000].rstrip()
        payload["news"][0]["cta"] = ("방문 전에 안내를 확인해 주세요. " * 60)[:900].rstrip()
        adapter = cast("PackAdapter", self.runner.adapter)
        adapter.override = json.dumps(payload, ensure_ascii=False)
        try:
            long_source = self.source_pack()
        finally:
            adapter.override = None
        report = self.report()
        verified_delivery(self.runner, long_source.run_id, "local-store-pack")
        verified_delivery(self.runner, report.run_id, "weekly-report")
        feedback = PackFeedback(
            schema_version="aicmo.pack-feedback.v1",
            source_run_id=long_source.run_id,
            item="news-1.txt",
            observed_on=self.day,
            adoption="used",
            reason="안내를 확인했습니다.",
            insight=INSIGHT,
        )
        self.assertLessEqual(
            len(
                feedback_report(
                    self.runner, {"client": "shop", "feedback_json": feedback.model_dump_json()}
                )
            ),
            6000,
        )
        feedback.weekly_report_run_id = report.run_id
        with self.assertRaisesRegex(
            WorkflowExecutionError, "evidence exceeds complete review capacity"
        ):
            feedback_report(
                self.runner, {"client": "shop", "feedback_json": feedback.model_dump_json()}
            )
        data = self.data(long_source, weekly_report=str(report.pk))
        self.assertEqual(
            self.client.post(f"/jobs/{long_source.pk}/feedback/news-1/", data).status_code, 409
        )
        self.assertEqual(Job.objects.filter(workflow_id="local-pack-feedback").count(), 0)
        self.no_learning()
