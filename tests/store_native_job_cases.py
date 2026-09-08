from __future__ import annotations

# Django owns the test lifecycle; all engine inputs and reviewers below are synthetic.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import uuid
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import Http404
from django.test import TransactionTestCase, override_settings

from aicmo.adapters import CommandAdapter
from aicmo.errors import RunNotFoundError
from aicmo.learning import PackFeedback, learning_context
from aicmo.models import ApprovalDecision
from aicmo.outcomes import (
    DailyOutcome,
    OutcomeImportSource,
    OutcomeSnapshot,
    daily_outcome_csv,
    import_outcomes_bytes,
    preview_outcomes_bytes,
    read_weekly_outcomes,
)
from aicmo.quota import configure_quota, current_period, quota_status, run_quota_status
from aicmo.runner import WorkflowRunner
from aicmo.source_input import source_checked_date
from aicmo.store import WorkflowStore
from aicmo.store_app import editor, rewrites, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import EditDraft, EditVersion, Job, PublicationReport, Store
from tests.store_boundary_cases import no_customer_work
from tests.test_delivery_manifest import PassReviewer
from tests.test_learning import feedback_inputs
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)

REPO = Path(__file__).resolve().parents[1]


class NativeJobTests(TransactionTestCase):
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
        commands = patch.dict(
            os.environ,
            {
                "AICMO_WEB_REVIEW_CMD": json.dumps(
                    [sys.executable, "synthetic-reviewer-not-executed"]
                ),
                "AICMO_WEB_EXECUTOR_CMD": "",
            },
        )
        commands.start()
        self.addCleanup(commands.stop)
        self.owner = User.objects.create_user("native-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        today = source_checked_date()
        self.day = today.isoformat()
        self.week = (today - timedelta(days=today.weekday())).isoformat()
        configure_quota(self.runner.store, "shop", current_period(), 1, 1)

    def tick(self, job: Job, runner: WorkflowRunner | None = None) -> None:
        with patch(
            "aicmo.store_app.management.commands.work.engine", return_value=runner or self.runner
        ) as engine:
            self.assertTrue(run_one())
            engine.assert_called_once_with(job.workflow_id)
        job.refresh_from_db()

    def source_pack(self) -> Job:
        job = services.submit(self.store, uuid.uuid4(), _brief()["brief_json"], actor=self.owner)
        self.assertEqual(job.workflow_id, "local-store-pack")
        self.tick(job)
        self.assertEqual(job.state, "waiting_approval")
        _, pack_sha, photo_sha = services.preview(job)
        services.request_approval(job, pack_sha, photo_sha, self.owner)
        self.tick(job)
        self.assertEqual(job.state, "success")
        self.assertEqual(
            (run_quota_status(self.runner.store, job.run_id) or {})["state"], "consumed"
        )
        return job

    def save_posts(self, posts: int) -> OutcomeSnapshot:
        raw = daily_outcome_csv(DailyOutcome(date=self.day, channel="naver", posts=posts))
        preview = preview_outcomes_bytes(
            self.root, self.runner.store, "shop", self.week, "naver", raw
        )
        import_outcomes_bytes(
            self.root,
            self.runner.store,
            "shop",
            self.week,
            "naver",
            raw,
            preview.confirmation_sha256,
            replace=True,
            provenance=OutcomeImportSource(
                kind="web_manual", recorded_by=f"web-user:{self.owner.pk}"
            ),
        )
        return read_weekly_outcomes(self.root, self.runner.store, "shop", self.week, "naver")

    def report(self, key: uuid.UUID | None = None, digest: str | None = None) -> Job:
        snapshot = read_weekly_outcomes(self.root, self.runner.store, "shop", self.week, "naver")
        return services.submit_weekly_report(
            self.store,
            key or uuid.uuid4(),
            self.week,
            "naver",
            digest or snapshot.snapshot_sha256,
            actor=self.owner,
        )

    def feedback(self, source: Job, key: uuid.UUID | None = None) -> Job:
        feedback = PackFeedback.model_validate_json(
            feedback_inputs(
                source_run_id=source.run_id,
                reason="사장님은 승인한 안내 문안을 그대로 사용했습니다.",
            )["feedback_json"]
        )
        return services.submit_feedback(self.store, key or uuid.uuid4(), feedback, actor=self.owner)

    def approve_feedback(self, job: Job) -> str:
        self.tick(job)
        self.assertEqual(job.state, "waiting_approval")
        raw, digest = services.feedback_candidate(job)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        services.request_feedback_approval(job, digest, actor=self.owner)
        job.refresh_from_db()
        self.assertEqual(job.state, "queued")
        return digest

    def cancel_without_provider(self, job: Job) -> None:
        services.request_cancel(job, self.owner)
        with (
            patch("aicmo.store_app.management.commands.work.engine", side_effect=AssertionError),
            patch.object(PackAdapter, "generate", side_effect=AssertionError),
            patch.object(PassReviewer, "generate", side_effect=AssertionError),
        ):
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertFalse(job.cancel_requested)

    def assert_no_learning(self, job: Job) -> None:
        self.assertFalse((self.root / "knowledge-base/shop/approved-feedback.md").exists())
        self.assertEqual(json.loads(learning_context(self.runner, "shop"))["insights"], [])
        with self.runner.store.connect() as connection:
            self.assertEqual(
                connection.execute("select count(*) from learned_feedback").fetchone()[0], 0
            )
            self.assertEqual(
                connection.execute(
                    "select count(*) from kb_updates where run_id=?", (job.run_id,)
                ).fetchone()[0],
                0,
            )

    def test_default_pack_and_cross_kind_submission_and_active_collisions(self) -> None:
        source = self.source_pack()
        with self.assertRaises(services.StoreActionError):
            self.report(source.submission_key)
        with self.assertRaises(services.StoreActionError):
            self.feedback(source, source.submission_key)
        report = self.report()
        for key in (report.submission_key, uuid.uuid4()):
            with self.assertRaises(services.StoreActionError):
                services.submit(self.store, key, _brief()["brief_json"], actor=self.owner)
            with self.assertRaises(services.StoreActionError):
                self.feedback(source, key)
        self.assertEqual(Job.objects.count(), 2)
        self.cancel_without_provider(report)
        self.assertEqual(report.state, "cancelled")
        # A terminal job still owns its submission key across workflow kinds.
        with self.assertRaises(services.StoreActionError):
            self.feedback(source, report.submission_key)
        feedback = self.feedback(source)
        for key in (feedback.submission_key, uuid.uuid4()):
            with self.assertRaises(services.StoreActionError):
                self.report(key)
            with self.assertRaises(services.StoreActionError):
                services.submit(self.store, key, _brief()["brief_json"], actor=self.owner)
        self.assertEqual(Job.objects.count(), 3)
        self.cancel_without_provider(feedback)
        pack = services.submit(self.store, uuid.uuid4(), _brief()["brief_json"], actor=self.owner)
        for key in (pack.submission_key, uuid.uuid4()):
            with self.assertRaises(services.StoreActionError):
                self.report(key)
            with self.assertRaises(services.StoreActionError):
                self.feedback(source, key)
        self.assertEqual(Job.objects.count(), 4)

    def test_report_freezes_snapshot_and_replays_after_ledger_correction(self) -> None:
        original = self.save_posts(1)
        key = uuid.uuid4()
        job = self.report(key, original.snapshot_sha256)
        frozen = dict(job.inputs)
        self.assertEqual(
            OutcomeSnapshot.model_validate_json(frozen["outcomes_snapshot_json"]), original
        )
        corrected = self.save_posts(9)
        self.assertNotEqual(original.snapshot_sha256, corrected.snapshot_sha256)
        replay = self.report(key, original.snapshot_sha256)
        self.assertEqual(replay.pk, job.pk)
        self.assertEqual(replay.inputs, frozen)
        with self.assertRaises(services.StoreActionError):
            self.report(key, corrected.snapshot_sha256)
        with patch.object(PackAdapter, "generate", side_effect=AssertionError):
            self.tick(job)
        self.assertEqual(job.state, "success")
        report = (self.root / f"artifacts/{job.run_id}/weekly-report.md").read_text("utf-8")
        self.assertIn("| 게시 | 1 | 1/7 |", report)
        self.assertNotIn("| 게시 | 9 | 1/7 |", report)
        self.assertEqual(self.runner.store.get_inputs(job.run_id), frozen)
        # No active job masks this stale-preview rejection.
        with self.assertRaises(services.StoreActionError):
            self.report(digest=original.snapshot_sha256)
        self.assertEqual(Job.objects.count(), 1)
        new = self.report(digest=corrected.snapshot_sha256)
        self.assertNotEqual(new.pk, job.pk)
        self.assertEqual(
            OutcomeSnapshot.model_validate_json(new.inputs["outcomes_snapshot_json"]), corrected
        )

    def test_report_pass_warn_failure_use_no_pack_quota_or_generator(self) -> None:
        configure_quota(self.runner.store, "shop", current_period(), 0, 0)
        self.save_posts(0)
        quota = quota_status(self.runner.store, "shop", current_period())
        for verdict, state in (("PASS", "success"), ("WARN", "needs_work"), ("FAIL", "failed")):
            with self.subTest(verdict=verdict):
                job = self.report()
                with patch.object(PackAdapter, "generate", side_effect=AssertionError):
                    self.tick(job, replace(self.runner, review_adapter=PassReviewer(verdict)))
                self.assertEqual(job.workflow_id, "weekly-report")
                self.assertEqual(job.state, state)
                self.assertIsNone(run_quota_status(self.runner.store, job.run_id))
                self.assertEqual(quota_status(self.runner.store, "shop", current_period()), quota)
                self.assertEqual(job.approval, {})
                self.assert_no_learning(job)

    def test_feedback_approved_source_candidate_review_does_not_learn(self) -> None:
        source = self.source_pack()
        quota = quota_status(self.runner.store, "shop", current_period())
        job = self.feedback(source)
        replay = self.feedback(source, job.submission_key)
        self.assertEqual((replay.pk, replay.inputs), (job.pk, job.inputs))
        changed = PackFeedback.model_validate_json(job.inputs["feedback_json"]).model_copy(
            update={"reason": "같은 제출 번호에서 바뀐 합성 관측입니다."}
        )
        with self.assertRaises(services.StoreActionError):
            services.submit_feedback(self.store, job.submission_key, changed, actor=self.owner)
        with patch.object(PackAdapter, "generate", side_effect=AssertionError):
            self.tick(job)
            self.assertEqual(job.state, "waiting_approval")
            self.assertEqual(job.approval, {})
            raw, digest = services.feedback_candidate(job)
            candidate = json.loads(raw)
            self.assertEqual(candidate["feedback"]["source_run_id"], source.run_id)
            self.assertEqual(candidate["original"], candidate["approved"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            with self.assertRaises(services.StoreActionError):
                services.request_feedback_approval(job, "0" * 64, actor=self.owner)
            self.assert_no_learning(job)
            services.request_feedback_approval(job, digest, actor=self.owner)
            job.refresh_from_db()
            receipt = dict(job.approval)
            services.request_feedback_approval(job, digest, actor=self.owner)
            job.refresh_from_db()
            self.assertEqual(job.approval, receipt)
            self.tick(job)
        self.assertEqual(job.state, "success")
        self.assertEqual(job.workflow_id, "local-pack-feedback")
        self.assertEqual(
            self.runner.store.approval_for(job.run_id, "owner_gate"), ApprovalDecision.APPROVED
        )
        self.assertIsNone(run_quota_status(self.runner.store, job.run_id))
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), quota)
        self.assert_no_learning(job)

    def test_feedback_engine_approval_crash_replays_one_durable_approval(self) -> None:
        job = self.feedback(self.source_pack())
        digest = self.approve_feedback(job)
        receipt = dict(job.approval)
        with (
            patch.object(WorkflowRunner, "resume", side_effect=RuntimeError("synthetic crash")),
            self.assertRaises(RuntimeError),
        ):
            self.tick(job)
        self.assertEqual(
            self.runner.store.approval_for(job.run_id, "owner_gate"), ApprovalDecision.APPROVED
        )
        services.request_feedback_approval(job, digest, actor=self.owner)
        job.refresh_from_db()
        self.assertEqual(job.approval, receipt)
        with patch.object(PackAdapter, "generate", side_effect=AssertionError):
            self.tick(job)
        self.assertEqual(job.state, "success")
        with self.runner.store.connect() as connection:
            rows = connection.execute(
                "select reviewer from approvals where run_id=? and step_id='owner_gate'",
                (job.run_id,),
            ).fetchall()
        self.assertEqual([row["reviewer"] for row in rows], [f"web-user:{self.owner.pk}"])
        self.assert_no_learning(job)

    def test_both_native_completions_win_cancel_without_providers(self) -> None:
        source = self.source_pack()
        self.save_posts(1)
        quota = quota_status(self.runner.store, "shop", current_period())
        for kind in ("weekly-report", "local-pack-feedback"):
            with self.subTest(kind=kind):
                job = self.report() if kind == "weekly-report" else self.feedback(source)
                if kind == "local-pack-feedback":
                    self.approve_feedback(job)
                with (
                    patch.object(
                        WorkflowStore,
                        "mark_run_success",
                        side_effect=RuntimeError("synthetic crash"),
                    ),
                    self.assertRaises(RuntimeError),
                ):
                    self.tick(job)
                self.assertEqual(self.runner.store.get_run(job.run_id)["status"], "running")
                self.assertTrue(
                    all(
                        row["status"] == "success"
                        for row in self.runner.store.list_steps(job.run_id)
                    )
                )
                self.cancel_without_provider(job)
                self.assertEqual(job.state, "success")
                self.assertEqual(self.runner.store.get_run(job.run_id)["status"], "success")
                # Also reconcile a crash after engine success but before the web completion write.
                Job.objects.filter(pk=job.pk).update(state="running", cancel_requested=True)
                self.cancel_without_provider(job)
                self.assertEqual(job.state, "success")
                self.assertIsNone(run_quota_status(self.runner.store, job.run_id))
                self.assertEqual(quota_status(self.runner.store, "shop", current_period()), quota)
                self.assert_no_learning(job)

    def test_both_native_jobs_cancel_before_run_without_providers(self) -> None:
        source = self.source_pack()
        quota = quota_status(self.runner.store, "shop", current_period())
        for kind in ("weekly-report", "local-pack-feedback"):
            with self.subTest(kind=kind):
                job = self.report() if kind == "weekly-report" else self.feedback(source)
                with self.assertRaises(RunNotFoundError):
                    self.runner.store.get_run(job.run_id)
                self.cancel_without_provider(job)
                self.assertEqual(job.state, "cancelled")
                with self.assertRaises(RunNotFoundError):
                    self.runner.store.get_run(job.run_id)
                self.assertFalse((self.root / f"artifacts/{job.run_id}").exists())
                self.assertIsNone(run_quota_status(self.runner.store, job.run_id))
                self.assertEqual(quota_status(self.runner.store, "shop", current_period()), quota)
                self.assert_no_learning(job)
        waiting = self.feedback(source)
        self.tick(waiting)
        self.assertEqual(waiting.state, "waiting_approval")
        self.cancel_without_provider(waiting)
        self.assertEqual(waiting.state, "cancelled")
        self.assertEqual(self.runner.store.get_run(waiting.run_id)["status"], "cancelled")
        self.assertIsNone(self.runner.store.approval_for(waiting.run_id, "owner_gate"))
        self.assert_no_learning(waiting)

    def test_native_new_and_replayed_submissions_recheck_current_authority(self) -> None:
        source = self.source_pack()
        snapshot = self.save_posts(1)
        report = self.report()
        self.cancel_without_provider(report)
        feedback = self.feedback(source)
        self.cancel_without_provider(feedback)
        payload = PackFeedback.model_validate_json(feedback.inputs["feedback_json"])
        other = User.objects.create_user("native-other-owner")
        before = list(Job.objects.order_by("pk").values())
        for boundary in ("inactive", "owner_changed", "client_changed"):
            with self.subTest(boundary=boundary):
                User.objects.filter(pk=self.owner.pk).update(is_active=boundary != "inactive")
                Store.objects.filter(pk=self.store.pk).update(
                    owner_id=other.pk if boundary == "owner_changed" else self.owner.pk,
                    client="moved-client" if boundary == "client_changed" else "shop",
                )
                # Both Python objects still carry their old active/owner/client values.
                with patch("aicmo.store_app.services.reader", side_effect=AssertionError):
                    for key in (report.submission_key, uuid.uuid4()):
                        with self.assertRaises(Http404):
                            services.submit_weekly_report(
                                self.store,
                                key,
                                self.week,
                                "naver",
                                snapshot.snapshot_sha256,
                                actor=self.owner,
                            )
                    for key in (feedback.submission_key, uuid.uuid4()):
                        with self.assertRaises(Http404):
                            services.submit_feedback(self.store, key, payload, actor=self.owner)
                self.assertEqual(list(Job.objects.order_by("pk").values()), before)

    def test_native_engine_requires_only_reviewer_configuration(self) -> None:
        command = [sys.executable, "synthetic-reviewer-not-executed"]
        with (
            patch.dict(
                os.environ,
                {
                    "AICMO_WEB_EXECUTOR_CMD": "",
                    "AICMO_WEB_REVIEW_CMD": json.dumps(command),
                },
            ),
            patch.object(CommandAdapter, "generate", side_effect=AssertionError),
        ):
            for kind in ("weekly-report", "local-pack-feedback"):
                runner = services.engine(kind)
                self.assertIsInstance(runner.review_adapter, CommandAdapter)
                assert isinstance(runner.review_adapter, CommandAdapter)
                self.assertEqual(runner.review_adapter.command, tuple(command))
            with self.assertRaises(services.StoreActionError):
                services.engine()
            with self.assertRaises(services.StoreActionError):
                services.engine("unsupported")
            with patch.dict(os.environ, {"AICMO_WEB_REVIEW_CMD": ""}):
                for kind in ("weekly-report", "local-pack-feedback"):
                    with self.assertRaises(services.StoreActionError):
                        services.engine(kind)

    def test_missing_reviewer_blocks_new_native_jobs_but_preserves_replay(self) -> None:
        source = self.source_pack()
        snapshot = self.save_posts(1)
        report = self.report()
        self.cancel_without_provider(report)
        feedback = self.feedback(source)
        self.cancel_without_provider(feedback)
        payload = PackFeedback.model_validate_json(feedback.inputs["feedback_json"])
        before = list(Job.objects.order_by("pk").values())
        # The setup has no valid generator configuration; both native submissions succeeded.
        for setting in ("", "not-json"):
            with (
                self.subTest(setting=setting),
                patch.dict(os.environ, {"AICMO_WEB_REVIEW_CMD": setting}),
                patch.object(CommandAdapter, "generate", side_effect=AssertionError),
            ):
                with patch("aicmo.store_app.services.reader", side_effect=AssertionError):
                    with self.assertRaises(services.StoreActionError):
                        services.submit_weekly_report(
                            self.store,
                            uuid.uuid4(),
                            self.week,
                            "naver",
                            snapshot.snapshot_sha256,
                            actor=self.owner,
                        )
                    with self.assertRaises(services.StoreActionError):
                        services.submit_feedback(
                            self.store, uuid.uuid4(), payload, actor=self.owner
                        )
                repeated_report = self.report(report.submission_key, snapshot.snapshot_sha256)
                repeated_feedback = self.feedback(source, feedback.submission_key)
                self.assertEqual(
                    (repeated_report.pk, repeated_report.inputs), (report.pk, report.inputs)
                )
                self.assertEqual(
                    (repeated_feedback.pk, repeated_feedback.inputs), (feedback.pk, feedback.inputs)
                )
                self.assertEqual(list(Job.objects.order_by("pk").values()), before)

    def test_native_jobs_cannot_enter_pack_urls_before_source_or_form_work(self) -> None:
        self.client.force_login(self.owner)
        for kind in ("weekly-report", "local-pack-feedback"):
            job = Job.objects.create(
                store=self.store,
                submission_key=uuid.uuid4(),
                workflow_id=kind,
                inputs=_brief(),
                state="success",
            )
            before = Job.objects.values().get(pk=job.pk)
            prefix = f"/jobs/{job.pk}/"
            with (
                no_customer_work(),
                patch("aicmo.store_app.views.ApprovalForm", side_effect=AssertionError),
                patch("aicmo.store_app.publication.submitted", side_effect=AssertionError),
                patch("aicmo.store_app.editor_views.validate_post", side_effect=AssertionError),
                patch("aicmo.store_app.rewrites.validate_post", side_effect=AssertionError),
            ):
                for suffix in ("photo/", "edit/", "edit/confirm/", "rewrite/", "delivery/"):
                    with self.subTest(kind=kind, method="GET", suffix=suffix):
                        self.assertEqual(self.client.get(prefix + suffix).status_code, 404)
                for suffix in (
                    "edit/",
                    "edit/confirm/",
                    "edit/restore/",
                    "rewrite/",
                    "approve/",
                    "download/",
                    "publication/news-1/",
                ):
                    with self.subTest(kind=kind, method="POST", suffix=suffix):
                        response = self.client.post(
                            prefix + suffix,
                            {"stage": "confirm", "fact": "synthetic wrong kind form marker"},
                        )
                        self.assertNotContains(
                            response, "synthetic wrong kind form marker", status_code=404
                        )
            self.assertEqual(Job.objects.values().get(pk=job.pk), before)
            self.assertFalse((self.root / f"artifacts/{job.run_id}").exists())
            with self.assertRaises(RunNotFoundError):
                self.runner.store.get_run(job.run_id)
        self.assertFalse(EditDraft.objects.exists())
        self.assertFalse(EditVersion.objects.exists())
        self.assertFalse(PublicationReport.objects.exists())

    def test_direct_pack_edit_and_rewrite_services_reject_native_jobs_before_source(self) -> None:
        for kind in ("weekly-report", "local-pack-feedback"):
            job = Job.objects.create(
                store=self.store,
                submission_key=uuid.uuid4(),
                workflow_id=kind,
                inputs=_brief(),
                state="success",
            )
            before = Job.objects.values().get(pk=job.pk)
            with (
                self.subTest(kind=kind),
                patch("aicmo.store_app.editor.inspect_base", side_effect=AssertionError),
                patch("aicmo.store_app.editor.current", side_effect=AssertionError),
                patch("aicmo.store_app.rewrites.source", side_effect=AssertionError),
                patch("aicmo.store_app.rewrites.signing.loads", side_effect=AssertionError),
                patch("aicmo.store_app.services.engine", side_effect=AssertionError),
                patch.object(WorkflowStore, "get_inputs", side_effect=AssertionError),
                patch.object(PackAdapter, "generate", side_effect=AssertionError),
            ):
                with self.assertRaises(Http404):
                    editor.save(job, self.runner, "0" * 64, 0, {}, actor=self.owner)
                with self.assertRaises(Http404):
                    editor.save(job, self.runner, "0" * 64, 0, actor=self.owner, restore=0)
                with self.assertRaises(Http404):
                    editor.confirm(job, self.runner, 0, "0" * 64, "0" * 64, self.owner)
                with self.assertRaises(Http404):
                    rewrites.submit(job, self.runner, "synthetic-unsigned-token", self.owner)
            self.assertEqual(Job.objects.values().get(pk=job.pk), before)
            self.assertFalse((self.root / f"artifacts/{job.run_id}").exists())
            with self.assertRaises(RunNotFoundError):
                self.runner.store.get_run(job.run_id)
        self.assertFalse(EditDraft.objects.exists())
        self.assertFalse(EditVersion.objects.exists())

    def test_worker_setup_failure_releases_new_job_and_preserves_existing_run(self) -> None:
        source = self.source_pack()
        quota = quota_status(self.runner.store, "shop", current_period())
        job = self.report()
        with (
            patch.dict(os.environ, {"AICMO_WEB_REVIEW_CMD": ""}),
            patch("aicmo.store_app.management.commands.work.execute", side_effect=AssertionError),
            patch.object(CommandAdapter, "generate", side_effect=AssertionError),
        ):
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.notice, "작업을 시작하지 못했습니다. 운영자에게 문의해 주세요.")
        self.assertFalse((self.root / f"artifacts/{job.run_id}").exists())
        with self.assertRaises(RunNotFoundError):
            self.runner.store.get_run(job.run_id)
        # The failed job releases the store's active slot and cannot poison later work.
        following = self.report()
        self.tick(following)
        self.assertEqual(following.state, "success")
        feedback = self.feedback(source)
        self.approve_feedback(feedback)
        receipt = dict(feedback.approval)
        with (
            patch.dict(os.environ, {"AICMO_WEB_REVIEW_CMD": ""}),
            patch("aicmo.store_app.management.commands.work.execute", side_effect=AssertionError),
        ):
            self.assertFalse(run_one())
            feedback.refresh_from_db()
            self.assertEqual(feedback.state, "queued")
            self.assertEqual(feedback.approval, receipt)
            self.assertEqual(
                feedback.notice,
                "작업 설정을 확인하지 못했습니다. 운영자에게 문의하거나 취소해 주세요.",
            )
            self.assertEqual(
                self.runner.store.get_run(feedback.run_id)["status"], "waiting_approval"
            )
            self.cancel_without_provider(feedback)
        self.assertEqual(feedback.state, "cancelled")
        self.assertEqual(self.runner.store.get_run(feedback.run_id)["status"], "cancelled")
        self.assertIsNone(self.runner.store.approval_for(feedback.run_id, "owner_gate"))
        self.assertEqual(quota_status(self.runner.store, "shop", current_period()), quota)
        self.assert_no_learning(feedback)

    def test_worker_setup_failure_preserves_early_and_late_cancel_intents(self) -> None:
        early = self.report()
        provider_detail = "synthetic provider detail not for the owner"

        def unavailable(workflow_id: str) -> WorkflowRunner:
            self.assertEqual(workflow_id, early.workflow_id)
            services.request_cancel(early, self.owner)
            raise services.StoreActionError(provider_detail)

        with (
            patch("aicmo.store_app.management.commands.work.engine", side_effect=unavailable),
            patch("aicmo.store_app.management.commands.work.execute", side_effect=AssertionError),
        ):
            self.assertTrue(run_one())
        early.refresh_from_db()
        self.assertEqual(early.state, "cancelled")
        self.assertFalse(early.cancel_requested)
        self.assertEqual(early.notice, "")
        late = self.report()
        lookup = WorkflowStore.get_run

        def lookup_after_cancel(store: WorkflowStore, run_id: str) -> sqlite3.Row:
            if run_id == late.run_id:
                services.request_cancel(late, self.owner)
            return lookup(store, run_id)

        with (
            patch(
                "aicmo.store_app.management.commands.work.engine",
                side_effect=services.StoreActionError(provider_detail),
            ),
            patch.object(WorkflowStore, "get_run", lookup_after_cancel),
        ):
            self.assertTrue(run_one())
        late.refresh_from_db()
        self.assertEqual(late.state, "queued")
        self.assertTrue(late.cancel_requested)
        self.assertEqual(late.notice, "")
        self.cancel_without_provider(late)
        self.assertEqual(late.state, "cancelled")
        for job in (early, late):
            self.assertFalse((self.root / f"artifacts/{job.run_id}").exists())
            with self.assertRaises(RunNotFoundError):
                self.runner.store.get_run(job.run_id)
