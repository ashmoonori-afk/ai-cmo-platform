from __future__ import annotations

# Django owns the transaction lifecycle and assertions.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth.models import Permission, User
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase, override_settings

from aicmo.onboarding import scaffold_client
from aicmo.paths import native_io_path
from aicmo.store_app import onboarding, onboarding_publish
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, OnboardingDraft, Store
from aicmo.store_app.services import StoreActionError

STEPS = {
    1: {
        "company_name": "합성 동네 카페",
        "neighborhood": "성수동",
        "business_type": "카페",
        "website": "",
    },
    2: {
        "offer": "아메리카노",
        "price": "4,000원",
        "business_hours": "월~금 10~18시",
        "differentiator": "",
    },
    3: {
        "objective": "가게 소식 안내",
        "channel": "네이버",
        "weekly_capacity": "20",
        "market_type": "unknown",
        "audience": "",
        "proof": "",
        "cta": "",
    },
}


class OnboardingTests(TransactionTestCase):
    def setUp(self) -> None:
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "workflows").mkdir()
        (self.root / "registry").mkdir()
        (self.root / "registry/capabilities.yaml").write_text(
            "# synthetic fixture", encoding="utf-8"
        )
        setting = override_settings(REPO_ROOT=self.root, ALLOWED_HOSTS=["testserver"])
        setting.enable()
        self.addCleanup(setting.disable)
        self.owner = User.objects.create_user("new-owner")
        self.client.force_login(self.owner)

    def step(self, step: int, **changes: str) -> None:
        draft = OnboardingDraft.objects.filter(owner=self.owner).first()
        revision = 0 if draft is None else draft.revision
        response = self.client.post(
            f"/onboarding/{step}/",
            {**STEPS[step], "revision": str(revision), "action": "next", **changes},
        )
        self.assertEqual(response.status_code, 302, response.content.decode())

    def ready(self) -> OnboardingDraft:
        for step in STEPS:
            self.step(step)
        draft = OnboardingDraft.objects.get(owner=self.owner)
        self.assertContains(self.client.get("/onboarding/confirm/"), "아직 정하지 않았어요")
        self.assertEqual(
            self.client.post(
                "/onboarding/confirm/", {"revision": draft.revision, "checked": "on"}
            ).status_code,
            302,
        )
        draft.refresh_from_db()
        self.assertEqual(draft.state, "queued")
        return draft

    def tick(self) -> bool:
        with patch(
            "aicmo.store_app.management.commands.work.engine",
            side_effect=AssertionError("onboarding must not call a provider"),
        ):
            return run_one()

    def test_three_steps_publish_unknowns_and_first_request_without_auto_job(self) -> None:
        draft = self.ready()
        self.assertFalse(Store.objects.exists())
        self.assertFalse((self.root / "clients").exists())
        self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "complete")
        self.assertEqual(Store.objects.count(), 1)
        config = (self.root / "clients" / draft.client / "config.md").read_text("utf-8")
        for value in ("unknown", "후기없음", "미입력", "[미확인 — 추정 작성 금지]", "4,000원"):
            self.assertIn(value, config)
        self.assertEqual(len(draft.output_hashes), 8)
        response = self.client.get("/onboarding/confirm/", follow=True)
        self.assertContains(response, "이번 주 알릴 소식")
        self.assertNotContains(response, ">아메리카노</textarea>")
        self.assertEqual(Job.objects.count(), 0)
        self.assertFalse(self.tick())

    def test_draft_save_back_login_and_stale_tab(self) -> None:
        self.step(1)
        self.step(2, action="save", price="-3")
        self.client.logout()
        self.assertEqual(self.client.get("/onboarding/2/").status_code, 302)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get("/onboarding/2/"), 'value="-3"')
        self.assertEqual(
            self.client.post(
                "/onboarding/1/",
                {**STEPS[1], "revision": "0", "action": "next", "company_name": "오래된 덮어쓰기"},
            ).status_code,
            409,
        )
        draft = OnboardingDraft.objects.get()
        self.assertEqual(draft.data["company_name"], STEPS[1]["company_name"])
        self.step(2, action="back", offer="수정된 커피")
        self.assertContains(self.client.get("/onboarding/2/"), "수정된 커피")

    def test_boundary_validation_and_no_secret_echo(self) -> None:
        invalid = [
            {"company_name": ""},
            {"company_name": "x" * 121},
            {"company_name": "\x00"},
            {"company_name": "\u200b"},
            {"company_name": "가게\n# heading"},
            {"company_name": "가게\u202e표시"},
            {"company_name": "가게\u2028# injected"},
            {"company_name": "가게\u2029# injected"},
            {"website": "javascript:alert(1)"},
            {"website": "https://alice:supersecret@example.com"},
            {"company_name": "sk-" + "a" * 48},
            {"company_name": "env:KEY sk-" + "a" * 48},
            {"company_name": "비밀번호=supersecret"},
            {"company_name": "암호: supersecret"},
            {"company_name": "인증키=abcdefgh12345678"},
            {"company_name": "토큰=abcdefgh12345678"},
            {"company_name": "비밀번호\uff1dsupersecret"},
            {"client": "other"},
            {"action": "publish"},
        ]
        for changes in invalid:
            with self.subTest(changes=changes):
                result = self.client.post(
                    "/onboarding/1/", {**STEPS[1], "revision": "0", "action": "next", **changes}
                )
                self.assertIn(result.status_code, (400, 409))
                self.assertNotContains(result, "sk-" + "a" * 48, status_code=result.status_code)
                self.assertNotContains(result, "supersecret", status_code=result.status_code)
                self.assertNotContains(result, "abcdefgh12345678", status_code=result.status_code)
                self.assertFalse(OnboardingDraft.objects.exists())
        duplicate = urlencode(
            [*STEPS[1].items(), ("revision", "0"), ("revision", "0"), ("action", "next")]
        )
        self.assertEqual(
            self.client.post(
                "/onboarding/1/", duplicate, content_type="application/x-www-form-urlencoded"
            ).status_code,
            409,
        )
        self.step(1)
        self.assertEqual(
            self.client.post(
                "/onboarding/2/", {**STEPS[2], "price": "-4000원", "revision": "1"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/onboarding/2/", {**STEPS[2], "price": "-\u200b1000원", "revision": "1"}
            ).status_code,
            409,
        )
        self.step(2)
        for minutes in ("0", "241", "n/a"):
            self.assertEqual(
                self.client.post(
                    "/onboarding/3/", {**STEPS[3], "weekly_capacity": minutes, "revision": "2"}
                ).status_code,
                400,
            )

    def test_preparation_retry_cap_leaves_no_unbounded_stage_growth(self) -> None:
        draft = self.ready()
        for _ in range(OnboardingDraft.MAX_ATTEMPTS):
            with patch("aicmo.store_app.onboarding_publish.scaffold_client", side_effect=OSError):
                self.assertTrue(self.tick())
            draft.refresh_from_db()
            self.assertEqual(draft.state, "failed")
            self.assertEqual(draft.failure_code, "prepare_failed")
            if draft.attempts < OnboardingDraft.MAX_ATTEMPTS:
                onboarding.confirm(self.owner, draft.revision)
        with self.assertRaises(StoreActionError):
            onboarding.confirm(self.owner, draft.revision)
        self.assertFalse(self.tick())
        self.assertEqual(len(list((self.root / ".aicmo/onboarding" / draft.id.hex).iterdir())), 3)

    def test_customer_pii_masked_and_corrupt_saved_data_fails_closed(self) -> None:
        self.step(1)
        self.step(2)
        self.step(3, proof="문의 010-1234-5678 customer@example.com")
        draft = OnboardingDraft.objects.get()
        self.assertNotIn("010-1234-5678", str(draft.data))
        self.assertNotIn("customer@example.com", str(draft.data))
        self.assertEqual(self.client.get("/onboarding/confirm/").status_code, 200)
        draft.data["proof"] = "sk-" + "b" * 48
        draft.save(update_fields=["data"])
        self.assertEqual(self.client.get("/onboarding/confirm/").status_code, 409)
        self.assertEqual(self.client.get("/onboarding/3/").status_code, 409)
        self.assertEqual(
            self.client.post(
                "/onboarding/confirm/", {"revision": draft.revision, "checked": "on"}
            ).status_code,
            409,
        )

    def test_confirmation_csrf_duplicates_isolation_and_frozen_edits(self) -> None:
        draft = self.ready()
        self.assertEqual(
            self.client.post(
                "/onboarding/confirm/",
                {"revision": draft.revision, "checked": "on", "owner": "other"},
            ).status_code,
            409,
        )
        duplicate = urlencode(
            [("revision", str(draft.revision)), ("checked", "on"), ("checked", "on")]
        )
        self.assertEqual(
            self.client.post(
                "/onboarding/confirm/", duplicate, content_type="application/x-www-form-urlencoded"
            ).status_code,
            409,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(
            csrf_client.post(
                "/onboarding/confirm/", {"revision": draft.revision, "checked": "on"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/onboarding/1/", {**STEPS[1], "revision": draft.revision, "company_name": "변경"}
            ).status_code,
            302,
        )
        draft.refresh_from_db()
        self.assertEqual(draft.data["company_name"], STEPS[1]["company_name"])
        other = User.objects.create_user("other")
        self.client.force_login(other)
        self.assertEqual(self.client.get("/onboarding/confirm/").status_code, 302)
        self.assertNotContains(self.client.get("/onboarding/"), STEPS[1]["company_name"])

    def test_existing_store_and_operator_preserved(self) -> None:
        client = self.root / "clients" / "existing"
        client.mkdir(parents=True)
        original = b"existing private config"
        (client / "config.md").write_bytes(original)
        Store.objects.create(owner=self.owner, name="기존 가게", client="existing")
        self.assertEqual(self.client.get("/onboarding/").status_code, 302)
        self.assertEqual(
            self.client.post("/onboarding/1/", {**STEPS[1], "revision": "0"}).status_code, 302
        )
        self.assertFalse(OnboardingDraft.objects.exists())
        self.assertEqual((client / "config.md").read_bytes(), original)
        Store.objects.all().delete()
        self.owner.user_permissions.add(Permission.objects.get(codename="operate_stores"))  # pyright: ignore[reportUnknownMemberType]
        self.assertNotContains(self.client.get("/"), "가게 정보 입력·이어 쓰기")

    def test_manifest_crash_reuses_outputs_and_korean_confirmation_date(self) -> None:
        draft = self.ready()
        OnboardingDraft.objects.filter(pk=draft.pk).update(
            confirmed_at=datetime(2026, 9, 5, 15, 1, tzinfo=UTC)
        )
        with (
            patch(
                "aicmo.store_app.onboarding_publish._promote",
                side_effect=SystemExit("synthetic crash"),
            ),
            self.assertRaises(SystemExit),
        ):
            self.tick()
        draft.refresh_from_db()
        self.assertEqual(draft.state, "running")
        self.assertIsNotNone(draft.stage_id)
        stamps = draft.output_hashes
        with patch(
            "aicmo.store_app.onboarding_publish.scaffold_client",
            side_effect=AssertionError("no second scaffold"),
        ):
            self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "complete")
        self.assertEqual(draft.output_hashes, stamps)
        self.assertIn(
            "2026-09-06", (self.root / "clients" / draft.client / "config.md").read_text("utf-8")
        )

    def test_crash_after_each_directory_rename_recovers_without_overwrite(self) -> None:
        draft = self.ready()
        original = Path.rename
        calls = 0

        def crash(source: Path, target: Path) -> Path:
            nonlocal calls
            original(source, target)
            calls += 1
            raise SystemExit

        for _ in range(2):
            with patch.object(Path, "rename", crash), self.assertRaises(SystemExit):
                self.tick()
        self.assertEqual(calls, 2)
        self.assertFalse(Store.objects.exists())
        with patch(
            "aicmo.store_app.onboarding_publish.scaffold_client",
            side_effect=AssertionError("no second scaffold"),
        ):
            self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "complete")
        self.assertEqual(Store.objects.count(), 1)

    def test_failed_publish_preserves_conflict_and_retries_same_receipt(self) -> None:
        draft = self.ready()
        target = self.root / "clients" / draft.client
        target.mkdir(parents=True)
        (target / "config.md").write_bytes(b"do not overwrite")
        self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "failed")
        stamps = draft.output_hashes
        self.assertEqual((target / "config.md").read_bytes(), b"do not overwrite")
        self.assertFalse(Store.objects.exists())
        onboarding.confirm(self.owner, draft.revision)
        self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "failed")
        self.assertEqual(draft.output_hashes, stamps)

    def test_post_manifest_tampering_and_new_store_prevent_completion(self) -> None:
        draft = self.ready()
        with (
            patch("aicmo.store_app.onboarding_publish._finish", side_effect=SystemExit),
            self.assertRaises(SystemExit),
        ):
            self.tick()
        path = self.root / "clients" / draft.client / "config.md"
        path.write_bytes(b"tampered")
        self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "failed")
        self.assertFalse(Store.objects.exists())
        Store.objects.create(owner=self.owner, name="operator assigned", client="existing")
        with self.assertRaises(StoreActionError):
            onboarding.confirm(self.owner, draft.revision)
        self.assertEqual(Store.objects.count(), 1)

    def test_two_worker_processes_publish_once_without_provider(self) -> None:
        draft = self.ready()
        env = {
            **os.environ,
            "AICMO_REPO": str(self.root),
            "AICMO_TEST_DB": str(connection.settings_dict["NAME"]),
        }
        for key in ("AICMO_WEB_EXECUTOR_CMD", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            env.pop(key, None)
        workers = [
            subprocess.Popen(
                [sys.executable, "-m", "tests.run_store_app_tests", "--worker"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        for worker in workers:
            output, errors = worker.communicate(timeout=60)
            self.assertEqual(worker.returncode, 0, output + errors)
        draft.refresh_from_db()
        self.assertEqual(draft.state, "complete")
        self.assertEqual(Store.objects.count(), 1)
        self.assertEqual(len(list((self.root / ".aicmo/onboarding" / draft.id.hex).iterdir())), 1)
        for relative, stamp in draft.output_hashes.items():
            self.assertEqual(
                hashlib.sha256(native_io_path(self.root / relative).read_bytes()).hexdigest(),
                stamp["sha256"],
            )

    def test_orphan_pre_manifest_stage_uses_fresh_attempt(self) -> None:
        self.ready()

        def crash(*args: object, **kwargs: object) -> object:
            scaffold_client(*args, **kwargs)  # pyright: ignore[reportArgumentType]
            raise SystemExit

        with (
            patch("aicmo.store_app.onboarding_publish.scaffold_client", side_effect=crash),
            self.assertRaises(SystemExit),
        ):
            self.tick()
        draft = OnboardingDraft.objects.get()
        self.assertIsNone(draft.stage_id)
        self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "complete")
        self.assertEqual(len(list((self.root / ".aicmo/onboarding" / draft.id.hex).iterdir())), 2)

    def test_simultaneous_first_drafts_keep_one_revision(self) -> None:
        def submit(_index: int) -> str:
            close_old_connections()
            try:
                owner = User.objects.get(pk=self.owner.pk)
                values = dict(STEPS[1])
                onboarding.save_step(owner, 1, 0, values, completed=True)
            except StoreActionError:
                return "stale"
            else:
                return "saved"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(submit, range(2)), ["saved", "stale"])
        self.assertEqual(OnboardingDraft.objects.count(), 1)
        self.assertEqual(OnboardingDraft.objects.get().revision, 1)

    def test_final_transaction_rechecks_new_owner(self) -> None:
        draft = self.ready()
        original = onboarding_publish._finish  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        def assign_store(current: OnboardingDraft, values: dict[str, str]) -> None:
            Store.objects.create(owner=self.owner, name="운영자 연결", client="existing")
            original(current, values)

        with patch("aicmo.store_app.onboarding_publish._finish", side_effect=assign_store):
            self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "failed")
        self.assertEqual(draft.failure_code, "store_changed")
        self.assertEqual(Store.objects.get().client, "existing")

    def test_redirected_destination_is_not_written(self) -> None:
        draft = self.ready()
        outside = self.root / "existing-private"
        outside.mkdir()
        (outside / "config.md").write_bytes(b"keep original")
        target = self.root / "clients" / draft.client
        target.parent.mkdir()
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
        self.assertTrue(self.tick())
        draft.refresh_from_db()
        self.assertEqual(draft.state, "failed")
        self.assertEqual(draft.failure_code, "profile_conflict")
        self.assertFalse(Store.objects.exists())
        self.assertEqual((outside / "config.md").read_bytes(), b"keep original")
