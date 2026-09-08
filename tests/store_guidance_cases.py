from __future__ import annotations

# Django owns test isolation and assertions; all store inputs below are synthetic.
# ruff: noqa: PT009
# pyright: reportUninitializedInstanceVariable=false
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TransactionTestCase, override_settings

from aicmo.onboarding import scaffold_client
from aicmo.quota import configure_quota, current_period
from aicmo.store_app import guidance, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, Store
from tests.test_local_pack import (
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_onboarding import sample_answers


class GuidanceTests(TransactionTestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.runner = _runner(self.root)
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        commands = patch.dict(
            os.environ,
            {
                "AICMO_WEB_EXECUTOR_CMD": json.dumps([sys.executable, "synthetic-generator"]),
                "AICMO_WEB_REVIEW_CMD": json.dumps([sys.executable, "synthetic-reviewer"]),
            },
        )
        commands.start()
        self.addCleanup(commands.stop)
        self.owner = User.objects.create_user("guidance-owner")
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        self.client.force_login(self.owner)
        self.url = f"/stores/{self.store.pk}/new/"
        scaffold_client(
            self.root,
            replace(
                sample_answers(), client="shop", objective="리뷰 답글 준비", weekly_capacity="10분"
            ),
            force=True,
            pdf=False,
        )

    def data(self, **changes: str) -> dict[str, str]:
        return {
            "submission_key": str(uuid.uuid4()),
            "fact": "이번 주 평소대로 영업합니다.",
            "reviews": "",
            "owner_minutes": "10",
            **changes,
        }

    def test_new_store_guidance_reads_without_creating_engine_database(self) -> None:
        database = self.root / ".aicmo/runs.sqlite3"
        self.assertFalse(database.exists())
        response = self.client.get("/")
        self.assertContains(response, "주당 <strong>10분</strong>", html=False)
        self.assertContains(response, "실제 이번 주 안내 1건과 함께")
        self.assertContains(response, "답글 최대 2개", count=3)
        self.assertEqual(response.content.count(b"?intent="), 3)
        self.assertContains(response, "오늘은 알릴 소식이 없어요")
        self.assertContains(response, "사용 건수 기록이 아직 없습니다")
        self.assertContains(self.client.get(self.url), 'value="10"')
        self.assertFalse(database.exists())
        self.assertFalse((self.root / ".aicmo").exists())
        self.assertEqual(Job.objects.count(), 0)

    def test_all_intents_keep_facts_empty_and_only_help_changes(self) -> None:
        for intent, (_, help_text) in guidance.INTENTS.items():
            with self.subTest(intent=intent):
                response = self.client.get(self.url, {"intent": intent, "client": "outside"})
                self.assertContains(response, help_text)
                self.assertEqual(response.context["form"].initial.get("fact", ""), "")
                self.assertEqual(response.context["form"].initial["owner_minutes"], 10)
                self.assertEqual(response.context["store"].client, "shop")
        for invalid in ("../../outside", "<script>", "unknown"):
            response = self.client.get(self.url, {"intent": invalid})
            self.assertEqual(response.context["intent"], "news")
        response = self.client.post(
            self.url + "?intent=review", self.data(fact="", reviews="실제 후기입니다.")
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Job.objects.count(), 0)

    def test_profile_missing_duplicate_invalid_and_current_source_only(self) -> None:
        path = self.root / "clients/shop/config.md"
        original = path.read_bytes()
        invalid = [
            b"\xff",
            b"x" * (64 * 1024 + 1),
            original.replace(b"aicmo.smb-profile.v1", b"old-profile"),
            original + "\n- **이번 목적**: 가게 소식 안내\n".encode(),
            original.replace("10분".encode(), "3시간".encode()),
            original.replace("10분".encode(), "241분".encode()),
            original.replace("10분".encode(), "0분".encode()),
            original + "\u2028숨은 줄".encode(),
        ]
        for content in invalid:
            with self.subTest(size=len(content)):
                path.write_bytes(content)
                self.assertEqual(guidance.profile_hints(self.store), guidance.ProfileHints())
                self.assertContains(self.client.get(self.url), 'value="20"')
        path.write_bytes(
            original.replace("10분".encode(), "30분".encode()).replace(
                "리뷰 답글 준비".encode(), "방문·문의 안내".encode()
            )
        )
        hints = guidance.profile_hints(self.store)
        self.assertEqual(hints.minutes, 30)
        self.assertEqual(guidance.task_cards(hints)[0]["intent"], "closure")
        path.unlink()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(guidance.profile_hints(self.store), guidance.ProfileHints())

    def test_wrong_store_and_unsafe_identifier_never_read_another_profile(self) -> None:
        other = User.objects.create_user("other-guidance")
        self.client.force_login(other)
        with patch("aicmo.store_app.guidance.profile_hints", side_effect=AssertionError):
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url, self.data()).status_code, 404)
        self.store.client = "../outside"
        self.assertEqual(guidance.profile_hints(self.store), guidance.ProfileHints())

    def test_redirected_profile_is_not_used(self) -> None:
        target = self.root / "clients/shop"
        outside = self.root / "other-profile"
        target.rename(outside)
        if sys.platform == "win32":
            result = subprocess.run(  # noqa: S603 — fixed command and temporary test paths
                [r"C:\Windows\System32\cmd.exe", "/c", "mklink", "/J", str(target), str(outside)],
                capture_output=True,
                check=False,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            target.symlink_to(outside, target_is_directory=True)
        self.assertEqual(guidance.profile_hints(self.store), guidance.ProfileHints())
        self.assertContains(self.client.get(self.url), 'value="20"')

    def test_reserved_consumed_and_draft_counts_follow_actual_run(self) -> None:
        configure_quota(self.runner.store, "shop", current_period(), 2, 3)
        self.assertEqual(
            self.runner.run("local-store-pack", "guidance-counts", _brief()).status,
            "waiting_approval",
        )
        reserved = guidance.allowance(self.store)
        self.assertIn("새 작업 1건 가능 · 진행 중 예약 1건 · 저장 완료 0건", reserved["detail"])
        self.assertIn("작성 시도 2회 남음", reserved["detail"])
        self.runner.approve("guidance-counts", "owner_gate", "synthetic-owner", "test")
        self.assertEqual(self.runner.resume("guidance-counts").status, "success")
        self.assertIn(
            "새 작업 1건 가능 · 진행 중 예약 0건 · 저장 완료 1건",
            guidance.allowance(self.store)["detail"],
        )
        with patch("pathlib.Path.stat", side_effect=PermissionError):
            self.assertEqual(guidance.allowance(self.store)["code"], "unavailable")

    def test_active_job_wins_get_and_post_before_provider_configuration(self) -> None:
        job = services.submit(self.store, uuid.uuid4(), _brief()["brief_json"])
        with patch("aicmo.store_app.services.engine", side_effect=AssertionError):
            for state in ("queued", "running", "waiting_approval"):
                Job.objects.filter(pk=job.pk).update(state=state, cancel_requested=True)
                response = self.client.get("/")
                self.assertContains(response, "진행 중인 작업 이어 보기")
                self.assertNotContains(response, "?intent=")
                for result in (self.client.get(self.url), self.client.post(self.url, self.data())):
                    self.assertRedirects(result, f"/jobs/{job.id}/", fetch_redirect_response=False)
        self.assertEqual(Job.objects.count(), 1)

    def test_allowance_states_and_read_only_snapshot(self) -> None:
        self.assertEqual(guidance.allowance(self.store)["code"], "not_started")
        self.runner.store.initialize()
        self.assertEqual(guidance.allowance(self.store)["code"], "unmetered")
        configure_quota(self.runner.store, "shop", "2026-01", 2, 3)
        with patch("aicmo.store_app.guidance.current_period", return_value="2026-02"):
            result = guidance.allowance(self.store)
            self.assertEqual(result["code"], "missing_period")
            self.assertTrue(result["blocked"])
        configure_quota(self.runner.store, "shop", current_period(), 2, 3)
        before = self.runner.store.db_path.read_bytes()
        with patch(
            "aicmo.db.StoreDb.initialize", side_effect=AssertionError("GET must not initialize")
        ):
            self.assertContains(self.client.get("/"), "새 작업 2건 가능")
            self.assertEqual(guidance.allowance(self.store)["code"], "available")
        self.assertEqual(before, self.runner.store.db_path.read_bytes())
        configure_quota(self.runner.store, "shop", current_period(), 0, 3)
        self.assertEqual(guidance.allowance(self.store)["code"], "exhausted")
        configure_quota(self.runner.store, "shop", current_period(), 2, 0)
        self.assertTrue(guidance.allowance(self.store)["blocked"])

    def test_old_schema_and_unreadable_database_are_not_unmetered(self) -> None:
        database = self.runner.store.db_path
        database.parent.mkdir()
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("create table old_marker(value text)")
        original = database.read_bytes()
        self.assertEqual(guidance.allowance(self.store)["code"], "unavailable")
        self.assertContains(
            self.client.get(self.url), "사용 가능 건수를 확인하지 못했습니다", status_code=200
        )
        self.assertEqual(database.read_bytes(), original)
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("create table product_quotas(client text, period text)")
            connection.execute("create table product_usage(client text, period text, state text)")
        self.assertEqual(guidance.allowance(self.store)["code"], "unavailable")
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute(
                "insert into product_quotas values(?, ?)", ("shop", current_period())
            )
        partial = database.read_bytes()
        self.assertEqual(guidance.allowance(self.store)["code"], "unavailable")
        self.assertContains(self.client.get("/"), "사용 가능 건수를 확인하지 못했습니다")
        self.assertContains(self.client.get(self.url), "사용 가능 건수를 확인하지 못했습니다")
        self.assertEqual(database.read_bytes(), partial)
        database.write_bytes(b"not sqlite")
        self.assertEqual(guidance.allowance(self.store)["code"], "unavailable")

    def test_post_rechecks_allowance_and_worker_enforces_later_change(self) -> None:
        configure_quota(self.runner.store, "shop", current_period(), 1, 1)
        self.assertContains(self.client.get(self.url), "새 작업 1건 가능")
        configure_quota(self.runner.store, "shop", current_period(), 0, 0)
        result = self.client.post(self.url, self.data())
        self.assertEqual(result.status_code, 409)
        self.assertContains(result, "새 요청에 쓸 건수가 부족", status_code=409)
        self.assertEqual(Job.objects.count(), 0)
        configure_quota(self.runner.store, "shop", current_period(), 1, 1)
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            self.assertEqual(self.client.post(self.url, self.data()).status_code, 302)
        job = Job.objects.get()
        self.assertEqual(set(job.inputs), {"client", "brief_json"})
        configure_quota(self.runner.store, "shop", current_period(), 0, 0)
        with patch("aicmo.store_app.management.commands.work.engine", return_value=self.runner):
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertEqual(job.state, "failed")
        self.assertEqual(self.runner.store.get_step_attempt(job.run_id, "drafts"), 0)

    def test_completed_submission_replay_survives_exhaustion_and_missing_provider(self) -> None:
        data = self.data()
        with patch("aicmo.store_app.services.engine", return_value=self.runner):
            self.assertEqual(self.client.post(self.url, data).status_code, 302)
        job = Job.objects.get()
        Job.objects.filter(pk=job.pk).update(state="success")
        configure_quota(self.runner.store, "shop", current_period(), 0, 0)
        with patch("aicmo.store_app.services.engine", side_effect=AssertionError):
            self.assertRedirects(
                self.client.post(self.url, data), f"/jobs/{job.id}/", fetch_redirect_response=False
            )
            self.assertEqual(
                self.client.post(self.url, {**data, "fact": "다른 소식"}).status_code, 400
            )
        self.assertEqual(Job.objects.count(), 1)
