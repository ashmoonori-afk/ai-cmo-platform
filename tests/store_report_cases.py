from __future__ import annotations

# Real Django/runner state, synthetic observations and a deterministic reviewer.
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
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection
from django.http import Http404, QueryDict
from django.test import Client, TransactionTestCase, override_settings
from django.utils.html import escape

from aicmo import outcomes
from aicmo.errors import WorkflowExecutionError
from aicmo.export import verified_delivery
from aicmo.quota import configure_quota, current_period, quota_status
from aicmo.store import WorkflowStore
from aicmo.store_app import report_services, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, Store
from tests.test_delivery_manifest import PassReviewer
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

    from aicmo.adapters import AgentRequest, AgentResult

REPO = Path(__file__).resolve().parents[1]
WEEK = "2026-08-31"
SECRET = "sk-syntheticReportSecretNeverReflect123456789"


class ReportTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        for relative in (
            "workflows/weekly-report.workflow.yaml",
            "playbooks/06-analytics/weekly-report.md",
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        review_command = patch.dict(
            "os.environ", {"AICMO_WEB_REVIEW_CMD": json.dumps(["synthetic-review-not-invoked"])}
        )
        review_command.start()
        self.addCleanup(review_command.stop)
        self.owner = User.objects.create_user("report-owner")
        self.store = Store.objects.create(
            owner=self.owner, name="합성 <script>store-only</script>", client="shop"
        )
        self.client.force_login(self.owner)
        self.outcomes_url = f"/stores/{self.store.pk}/outcomes/"
        self.request_url = self.outcomes_url + "report/"
        configured = patch("aicmo.store_app.services.engine", return_value=self.runner)
        self.configured = configured.start()
        self.addCleanup(configured.stop)

    def seed(self, posts: int = 1) -> None:
        raw = outcomes.daily_outcome_csv(
            outcomes.DailyOutcome(date=WEEK, channel="naver", posts=posts, reservations=0)
        )
        preview = outcomes.preview_outcomes_bytes(
            self.root, self.runner.store, "shop", WEEK, "naver", raw
        )
        outcomes.import_outcomes_bytes(
            self.root,
            self.runner.store,
            "shop",
            WEEK,
            "naver",
            raw,
            preview.confirmation_sha256,
            replace=True,
            provenance=outcomes.OutcomeImportSource(
                kind="web_manual", recorded_by=f"web-user:{self.owner.pk}"
            ),
        )

    def token(self) -> str:
        response = self.client.get(self.outcomes_url, {"week_start": WEEK, "channel": "naver"})
        self.assertEqual(response.status_code, 200)
        return str(response.context["report_form"]["token"].value())

    def submit(self, token: str | None = None) -> Job:
        response = self.client.post(
            self.request_url, {"token": token or self.token(), "checked": "on"}
        )
        self.assertEqual(response.status_code, 302)
        job = Job.objects.get(pk=response.headers["Location"].split("/")[2])
        self.assertEqual(job.workflow_id, "weekly-report")
        return job

    def work(self, job: Job, *, verdict: str = "PASS") -> None:
        runner = replace(self.runner, review_adapter=PassReviewer(verdict))
        generate = PassReviewer.generate

        def reviewed(reviewer: PassReviewer, request: AgentRequest) -> AgentResult:
            self.assertFalse(connection.in_atomic_block)
            return generate(reviewer, request)

        with (
            patch("aicmo.store_app.management.commands.work.engine", return_value=runner),
            patch.object(PassReviewer, "generate", autospec=True, side_effect=reviewed) as reviewer,
        ):
            self.assertTrue(run_one())
        self.assertEqual(reviewer.call_count, 1)
        self.assertEqual(cast("PackAdapter", self.runner.adapter).requests, [])
        job.refresh_from_db()

    def report_url(self, job: Job) -> str:
        return f"/jobs/{job.pk}/report/"

    def dump(self) -> str:
        if not self.runner.store.db_path.is_file():
            return ""
        with WorkflowStore(self.runner.store.db_path, read_only=True).connect() as ledger:
            return "\n".join(ledger.iterdump())

    def test_record_screen_signs_server_scope_without_initializing_or_creating_jobs(self) -> None:
        with patch.object(
            WorkflowStore, "initialize", side_effect=AssertionError("GET must not migrate")
        ):
            token = self.token()
        envelope = signing.loads(token, salt=report_services.TOKEN_SALT)
        self.assertEqual(envelope["actor_id"], self.owner.pk)
        self.assertEqual(envelope["store_id"], self.store.pk)
        self.assertEqual(
            (envelope["client"], envelope["week_start"], envelope["channel"]),
            ("shop", WEEK, "naver"),
        )
        self.assertEqual(str(uuid.UUID(envelope["request_key"])), envelope["request_key"])
        self.assertRegex(envelope["snapshot_sha256"], r"^[a-f0-9]{64}$")
        self.assertFalse(self.runner.store.db_path.exists())
        self.seed()
        before = self.dump()
        self.token()
        self.assertEqual(self.dump(), before)
        self.assertEqual(Job.objects.count(), 0)
        self.configured.assert_not_called()
        self.assertFalse((self.root / "artifacts").exists())

    def test_request_review_delivery_replay_and_correction_keep_report_snapshot_fixed(self) -> None:
        self.seed(posts=2)
        configure_quota(self.runner.store, "shop", current_period(), 2, 4)
        quota = quota_status(self.runner.store, "shop", current_period())
        token = self.token()
        job = self.submit(token)
        self.assertEqual(self.submit(token).pk, job.pk)
        pending = self.client.get(self.report_url(job))
        self.assertEqual((pending.status_code, pending.context["report"]), (200, None))
        self.assertEqual(self.client.post(self.report_url(job) + "download/").status_code, 409)
        self.seed(posts=3)  # The worker must use the queued snapshot, not today's ledger.
        self.work(job)
        self.assertEqual(job.state, "success")
        inputs, contents = verified_delivery(self.runner, job.run_id, "weekly-report")
        raw = contents[f"artifacts/{job.run_id}/weekly-report.md"]
        snapshot = outcomes.OutcomeSnapshot.model_validate_json(inputs["outcomes_snapshot_json"])
        self.assertEqual(snapshot.current[0].posts, 2)
        self.assertIn("| 게시 | 2 | 1/7", raw.decode())
        before = self.dump()
        shown = self.client.get(self.report_url(job))
        self.assertEqual(shown.status_code, 200)
        report = shown.context["report"]
        self.assertEqual((report.raw, report.sha256), (raw, hashlib.sha256(raw).hexdigest()))
        self.assertTrue(report.current is False)
        self.assertContains(shown, "&lt;script&gt;store-only&lt;/script&gt;")
        self.assertNotContains(shown, "<script>store-only</script>")
        self.assertContains(shown, snapshot.snapshot_sha256)
        self.assertIn("no-store", shown.headers["Cache-Control"])
        downloaded = self.client.post(self.report_url(job) + "download/")
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual((downloaded.streaming, b"".join(downloaded)), (True, raw))
        downloaded.close()
        self.assertIn("attachment", downloaded.headers["Content-Disposition"])
        self.assertTrue(downloaded.headers["Content-Type"].startswith("text/markdown"))
        self.assertEqual(downloaded.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("no-store", downloaded.headers["Cache-Control"])
        self.assertEqual(self.dump(), before)
        self.seed(posts=9)
        stale = self.client.get(self.report_url(job))
        self.assertTrue(stale.context["report"].current is False)
        self.assertEqual(stale.context["report"].raw, raw)
        self.assertContains(stale, "성과 기록이 정정되었습니다")
        self.assertEqual(self.submit(token).pk, job.pk)
        newer = self.submit()
        self.assertNotEqual(newer.pk, job.pk)
        self.work(newer)
        newest = self.client.get(self.report_url(newer)).context["report"]
        self.assertIn("| 게시 | 9 | 1/7", newest.text)
        self.assertTrue(newest.current is True)
        self.assertEqual(
            (quota_status(self.runner.store, "shop", current_period()), Job.objects.count()),
            (quota, 2),
        )
        self.assertFalse((self.root / "knowledge-base").exists())

    def test_summary_and_collapsed_original_keep_verified_source_when_ledger_changes(self) -> None:
        self.seed(posts=2)
        job = self.submit()
        self.assertNotContains(self.client.get(self.report_url(job)), 'id="report-summary"')
        self.seed(posts=3)
        source = outcomes.OutcomeSnapshot.model_validate_json(job.inputs["outcomes_snapshot_json"])
        marker = '<script>alert("synthetic-report-only")</script><a href="/unsafe">원문</a>'
        generated = (
            outcomes.weekly_outcomes_report(
                self.root, self.runner.store, "shop", WEEK, "naver", snapshot=source
            )
            + marker
            + "\n"
        )
        # Inject before the real worker writes and reviews bytes, never after approval.
        with patch("aicmo.step_executor.weekly_outcomes_report", return_value=generated):
            self.work(job)
        raw = report_services.verify(job).raw
        before = self.dump()
        shown = self.client.get(self.report_url(job))
        self.assertEqual(shown.status_code, 200)
        self.assertContains(shown, "성과 기록이 정정되었습니다")
        with patch(
            "aicmo.store_app.outcome_services.read", side_effect=OSError(SECRET)
        ):
            unreadable = self.client.get(self.report_url(job))
        self.assertEqual(unreadable.status_code, 200)
        self.assertIsNone(unreadable.context["report"].current)
        self.assertContains(unreadable, "현재 기록과 같은지 확인할 수 없습니다")
        self.assertNotContains(unreadable, SECRET)
        for response in (shown, unreadable):
            self.assertEqual(response.context["report"].raw, raw)
            for key, label, value, days in (
                ("posts", "게시", "<strong>2건</strong>", 1),
                ("inquiries", "문의", "미입력", 0),
                ("reservations", "예약", "<strong>0건</strong>", 1),
                ("coupon_redemptions", "쿠폰 사용", "미입력", 0),
            ):
                self.assertContains(
                    response,
                    f'<div id="report-metric-{key}"><dt><strong>{label}</strong></dt>'
                    f"<dd>이번 주 {value} · 입력 {days}/7일<br>"
                    "지난주 미입력 · 입력 0/7일<br>증감률: 비교 불가</dd></div>",
                    html=True,
                )
            self.assertContains(response, escape(marker))
            self.assertNotContains(response, marker)
            self.assertContains(response, f'<pre class="copy">{escape(raw.decode())}</pre>')
        html = shown.content.decode()
        self.assertLess(html.index('id="report-summary"'), html.index('id="next-actions"'))
        self.assertLess(html.index('id="next-actions"'), html.index('id="report-original"'))
        self.assertContains(shown, '<details id="report-original" class="card">', count=1)
        self.assertContains(shown, '<summary id="report-body">검토한 보고서 원문 펼치기</summary>')
        for target in ("report-summary", "next-actions"):
            self.assertContains(shown, f'href="#{target}"', count=1)
            self.assertContains(shown, f'<h2 id="{target}" tabindex="-1">', count=1)
        self.assertContains(shown, 'href="#report-body"', count=1)
        self.assertEqual(len(re.findall(r'<form id="action-[^"]+"', html)), 3)
        ids = re.findall(r'\bid="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))
        downloaded = self.client.post(self.report_url(job) + "download/")
        self.assertEqual((downloaded.status_code, b"".join(downloaded)), (200, raw))
        downloaded.close()
        self.assertEqual(self.dump(), before)
        self.assertEqual(Job.objects.count(), 1)
        self.assertFalse((self.root / "knowledge-base").exists())

    def test_complete_week_summary_matches_reviewed_percent_and_zero_denominator(self) -> None:
        for week, posts, coupons in (("2026-08-24", 1, 1), (WEEK, 2, 0)):
            first = date.fromisoformat(week)
            rows = [
                f"{first + timedelta(days=offset)},naver,{posts},,0,{coupons}"
                for offset in range(7)
            ]
            raw = (
                "date,channel,posts,inquiries,reservations,coupon_redemptions\n"
                + "\n".join(rows)
                + "\n"
            ).encode()
            preview = outcomes.preview_outcomes_bytes(
                self.root, self.runner.store, "shop", week, "naver", raw
            )
            outcomes.import_outcomes_bytes(
                self.root,
                self.runner.store,
                "shop",
                week,
                "naver",
                raw,
                preview.confirmation_sha256,
                provenance=outcomes.OutcomeImportSource(
                    kind="web_csv", recorded_by=f"web-user:{self.owner.pk}"
                ),
            )
        job = self.submit()
        self.work(job)
        before = self.dump()
        shown = self.client.get(self.report_url(job))
        self.assertEqual(shown.status_code, 200)
        for key, label, current, previous, days, change in (
            ("posts", "게시", "<strong>14건</strong>", "7건", 7, "+100.0%"),
            ("inquiries", "문의", "미입력", "미입력", 0, "비교 불가"),
            ("reservations", "예약", "<strong>0건</strong>", "0건", 7, "비교 불가"),
            ("coupon_redemptions", "쿠폰 사용", "<strong>0건</strong>", "7건", 7, "-100.0%"),
        ):
            self.assertContains(
                shown,
                f'<div id="report-metric-{key}"><dt><strong>{label}</strong></dt>'
                f"<dd>이번 주 {current} · 입력 {days}/7일<br>"
                f"지난주 {previous} · 입력 {days}/7일<br>증감률: {change}</dd></div>",
                html=True,
            )
        self.assertContains(shown, "| 게시 | 14 | 7/7 | 7 | 7/7 | +100.0% |")
        self.assertContains(shown, "| 예약 | 0 | 7/7 | 0 | 7/7 | 비교 불가")
        self.assertContains(shown, "| 쿠폰 사용 | 0 | 7/7 | 7 | 7/7 | -100.0% |")
        self.assertEqual(self.dump(), before)

    def test_invalid_metadata_expiry_and_unsubmitted_stale_digest_create_no_job(self) -> None:
        self.seed()
        token = self.token()
        original = self.dump()
        for data, status in (
            ({"token": token}, 400),
            ({"token": SECRET, "checked": "on"}, 409),
            ({"token": token, "checked": "on", "outcomes_snapshot_json": SECRET}, 400),
            ({"token": token, "checked": SECRET}, 400),
            (
                {
                    "token": token,
                    "checked": "on",
                    "file": SimpleUploadedFile("synthetic.txt", SECRET.encode()),
                },
                400,
            ),
        ):
            response = self.client.post(self.request_url, data)
            self.assertEqual(response.status_code, status)
            self.assertNotContains(response, SECRET, status_code=status)
        duplicate = QueryDict(mutable=True)
        duplicate.update({"token": token, "checked": "on"})
        duplicate.appendlist("token", SECRET)
        response = self.client.post(
            self.request_url,
            duplicate.urlencode(),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, SECRET, status_code=400)
        with patch(
            "django.core.signing.time.time",
            return_value=time.time() + report_services.TOKEN_MAX_AGE + 1,
        ):
            self.assertEqual(
                self.client.post(self.request_url, {"token": token, "checked": "on"}).status_code,
                409,
            )
        with (
            patch(
                "aicmo.store_app.services.submit_weekly_report", side_effect=DatabaseError(SECRET)
            ),
            patch("aicmo.store_app.guidance.active_job", side_effect=DatabaseError(SECRET)),
        ):
            recovery = self.client.post(self.request_url, {"token": token, "checked": "on"})
        self.assertEqual(recovery.status_code, 409)
        self.assertEqual(recovery.context["form"]["token"].value(), token)
        self.assertNotContains(recovery, SECRET, status_code=409)
        self.assertEqual(self.dump(), original)
        self.configured.assert_not_called()
        self.seed(posts=3)
        response = self.client.post(self.request_url, {"token": token, "checked": "on"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Job.objects.count(), 0)

    def test_auth_methods_csrf_and_wrong_workflow_block_access(self) -> None:
        self.seed()
        token = self.token()
        job = self.submit(token)
        self.work(job)
        url = self.report_url(job)
        self.assertEqual(self.client.get(self.request_url).status_code, 405)
        self.assertEqual(self.client.get(url + "download/").status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(
            csrf.post(self.request_url, {"token": token, "checked": "on"}).status_code, 403
        )
        self.assertEqual(csrf.post(url + "download/").status_code, 403)
        shown = csrf.get(url)
        tokens = re.findall(r'name="csrfmiddlewaretoken" value="([^"]+)"', shown.content.decode())
        self.assertTrue(tokens)
        self.assertEqual(
            csrf.post(
                self.request_url,
                {"token": token, "checked": "on", "csrfmiddlewaretoken": tokens[0]},
            ).status_code,
            302,
        )
        download = csrf.post(url + "download/", {"csrfmiddlewaretoken": tokens[0]})
        self.assertEqual(download.status_code, 200)
        download.close()
        records = csrf.get(self.outcomes_url, {"week_start": WEEK, "channel": "naver"})
        report_forms = re.findall(
            r'<form id="report-form"[^>]*>(.*?)</form>', records.content.decode(), flags=re.DOTALL
        )
        self.assertEqual(len(report_forms), 1)
        form_tokens = re.findall(r'name="token" value="([^"]+)"', report_forms[0])
        csrf_tokens = re.findall(r'name="csrfmiddlewaretoken" value="([^"]+)"', report_forms[0])
        self.assertEqual(len(form_tokens), 1)
        self.assertEqual(len(csrf_tokens), 1)
        new_request = csrf.post(
            self.request_url,
            {"token": form_tokens[0], "checked": "on", "csrfmiddlewaretoken": csrf_tokens[0]},
        )
        self.assertEqual(new_request.status_code, 302)
        self.assertEqual(Job.objects.count(), 2)
        self.work(Job.objects.get(pk=new_request.headers["Location"].split("/")[2]))
        pack = services.submit(
            self.store, uuid.uuid4(), _brief(reviews=0)["brief_json"], actor=self.owner
        )
        self.assertEqual(self.client.get(self.report_url(pack)).status_code, 404)
        self.assertEqual(self.client.post(self.report_url(pack) + "download/").status_code, 404)
        self.client.force_login(User.objects.create_user("report-other-owner"))
        with patch("aicmo.store_app.report_services.verify") as verify:
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url + "download/").status_code, 404)
            self.assertEqual(
                self.client.post(self.request_url, {"token": token, "checked": "on"}).status_code,
                404,
            )
            verify.assert_not_called()
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.post(url + "download/").status_code, 302)

    def test_request_save_rechecks_owner_client_and_cached_operator_permission(self) -> None:
        self.seed()
        token = self.token()
        other = User.objects.create_user("report-next-owner")
        fresh = services.fresh_actor
        changes: tuple[Callable[[], object], ...] = (
            lambda: User.objects.filter(pk=self.owner.pk).update(is_active=False),
            lambda: Store.objects.filter(pk=self.store.pk).update(owner=other),
            lambda: Store.objects.filter(pk=self.store.pk).update(client="changed-shop"),
        )
        for change in changes:

            def changed(
                actor: AbstractBaseUser | AnonymousUser, update: Callable[[], object] = change
            ) -> User:
                self.assertTrue(connection.in_atomic_block)
                update()
                return fresh(actor)

            try:
                with patch("aicmo.store_app.services.fresh_actor", side_effect=changed):
                    self.assertEqual(
                        self.client.post(
                            self.request_url, {"token": token, "checked": "on"}
                        ).status_code,
                        404,
                    )
                self.assertEqual(Job.objects.count(), 0)
            finally:
                User.objects.filter(pk=self.owner.pk).update(is_active=True)
                Store.objects.filter(pk=self.store.pk).update(owner=self.owner, client="shop")
        operator = User.objects.create_user("report-operator")
        permission = Permission.objects.get(codename="operate_stores")
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        self.assertTrue(services.allowed_stores(operator).exists())
        self.client.force_login(operator)
        operator_token = self.token()
        self.assertEqual(
            self.client.post(self.request_url, {"token": token, "checked": "on"}).status_code, 404
        )

        def revoked(actor: AbstractBaseUser | AnonymousUser) -> User:
            self.assertTrue(connection.in_atomic_block)
            operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
            return fresh(actor)

        with patch("aicmo.store_app.services.fresh_actor", side_effect=revoked):
            self.assertEqual(
                self.client.post(
                    self.request_url, {"token": operator_token, "checked": "on"}
                ).status_code,
                404,
            )
        self.assertEqual(Job.objects.count(), 0)
        operator.user_permissions.add(permission)  # pyright: ignore[reportUnknownMemberType]
        job = self.submit(operator_token)
        envelope = report_services.decode(operator, self.store, operator_token)
        operator.user_permissions.remove(permission)  # pyright: ignore[reportUnknownMemberType]
        with self.assertRaises(Http404):
            services.submit_weekly_report(
                self.store,
                uuid.UUID(envelope.request_key),
                WEEK,
                "naver",
                envelope.snapshot_sha256,
                actor=operator,
            )
        self.assertEqual(Job.objects.get().pk, job.pk)

    def test_report_bytes_manifest_and_job_source_tampering_prevent_delivery(self) -> None:
        self.seed()
        job = self.submit()
        self.work(job)
        url = self.report_url(job)
        for filename in ("weekly-report.md", "delivery-review.json"):
            path = self.root / "artifacts" / job.run_id / filename
            raw = path.read_bytes()
            try:
                path.write_bytes(raw + SECRET.encode())
                with self.assertRaises(WorkflowExecutionError):
                    verified_delivery(self.runner, job.run_id, "weekly-report")
                response = self.client.get(url)
                self.assertEqual(response.status_code, 409)
                self.assertIsNone(response.context["report"])
                self.assertNotContains(response, SECRET, status_code=409)
                self.assertNotContains(response, "| 게시 | 1 | 1/7", status_code=409)
                self.assertNotContains(response, "저장 가능", status_code=409)
                self.assertNotContains(response, 'id="report-summary"', status_code=409)
                self.assertNotContains(response, 'id="next-actions"', status_code=409)
                self.assertEqual(self.client.post(url + "download/").status_code, 409)
            finally:
                path.write_bytes(raw)
        original = dict(job.inputs)
        Job.objects.filter(pk=job.pk).update(inputs={**original, "channel": "instagram"})
        mismatched = self.client.get(url)
        self.assertEqual(mismatched.status_code, 409)
        self.assertIsNone(mismatched.context["report"])
        self.assertEqual(self.client.post(url + "download/").status_code, 409)
        Job.objects.filter(pk=job.pk).update(inputs=original)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_warn_is_not_deliverable_even_if_web_state_claims_success(self) -> None:
        self.seed()
        job = self.submit()
        self.work(job, verdict="WARN")
        self.assertEqual(self.runner.store.get_run(job.run_id)["status"], "success")
        self.assertEqual(job.state, "needs_work")
        manifest = json.loads(
            (self.root / "artifacts" / job.run_id / "delivery-review.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(manifest["deliverable"])
        self.assertEqual(manifest["semantic_review"]["status"], "WARN")
        with self.assertRaises(WorkflowExecutionError):
            verified_delivery(self.runner, job.run_id, "weekly-report")
        url = self.report_url(job)
        shown = self.client.get(url)
        self.assertEqual(shown.status_code, 200)
        self.assertIsNone(shown.context["report"])
        self.assertNotContains(shown, 'id="report-summary"')
        self.assertEqual(self.client.post(url + "download/").status_code, 409)
        Job.objects.filter(pk=job.pk).update(state="success")
        forged = self.client.get(url)
        self.assertEqual(forged.status_code, 409)
        self.assertIsNone(forged.context["report"])
        self.assertNotContains(forged, "| 게시 | 1 | 1/7", status_code=409)
        self.assertNotContains(forged, "저장 가능", status_code=409)
        self.assertNotContains(forged, 'id="report-summary"', status_code=409)
        self.assertNotContains(forged, 'id="next-actions"', status_code=409)
        self.assertEqual(self.client.post(url + "download/").status_code, 409)
