from __future__ import annotations

# Actual Django/runner state with synthetic observations and deterministic review.
# ruff: noqa: PT009, PT027
# pyright: reportUninitializedInstanceVariable=false
import hashlib
import json
import shutil
import sqlite3
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import close_old_connections
from django.http import Http404
from django.test import TransactionTestCase, override_settings

from aicmo import outcomes
from aicmo.errors import AicmoError
from aicmo.quota import configure_quota, current_period
from aicmo.redaction import contains_raw_secret
from aicmo.store import WorkflowStore
from aicmo.store_app import action_services, report_services, services
from aicmo.store_app.management.commands.work import run_one
from aicmo.store_app.models import Job, Store
from tests.test_delivery_manifest import PassReviewer
from tests.test_local_pack import (
    PackAdapter,
    _runner,  # pyright: ignore[reportPrivateUsage]
)

REPO = Path(__file__).resolve().parents[1]
WEEK = "2026-08-31"


class ActionTests(TransactionTestCase):
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
        commands = patch.dict(
            "os.environ",
            {"AICMO_WEB_REVIEW_CMD": json.dumps(["synthetic-reviewer-not-executed"])},
        )
        commands.start()
        self.addCleanup(commands.stop)
        self.owner = User.objects.create_user("action-owner", pk=15881234)
        self.store = Store.objects.create(owner=self.owner, name="합성 가게", client="shop")
        configure_quota(self.runner.store, "shop", current_period(), 0, 0)
        raw = outcomes.daily_outcome_csv(
            outcomes.DailyOutcome(
                date=WEEK,
                channel="naver",
                posts=0,
                inquiries=0,
                reservations=0,
                coupon_redemptions=0,
            )
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
            provenance=outcomes.OutcomeImportSource(
                kind="web_manual", recorded_by=f"web-user:{self.owner.pk}"
            ),
        )

    def report(self, *, channel: outcomes.Channel = "naver", verdict: str = "PASS") -> Job:
        snapshot = outcomes.read_weekly_outcomes(
            self.root, self.runner.store, "shop", WEEK, channel
        )
        job = services.submit_weekly_report(
            self.store, uuid.uuid4(), WEEK, channel, snapshot.snapshot_sha256, actor=self.owner
        )
        with (
            patch(
                "aicmo.store_app.management.commands.work.engine",
                return_value=replace(self.runner, review_adapter=PassReviewer(verdict)),
            ),
            patch.object(PackAdapter, "generate", side_effect=AssertionError),
        ):
            self.assertTrue(run_one())
        job.refresh_from_db()
        self.assertEqual(job.state, "success" if verdict == "PASS" else "needs_work")
        return job

    def record(
        self,
        job: Job,
        report: report_services.ReviewedReport,
        *,
        key: uuid.UUID | None = None,
        code: action_services.ActionCode = "review_records",
        decision: action_services.Decision = "selected",
        reason: str = "확인한 날짜의 기록부터 살펴보겠습니다.",
    ) -> action_services.ActionReceipt:
        return action_services.record_action(
            job,
            code,
            decision,
            reason,
            key or uuid.uuid4(),
            report.sha256,
            report.source.snapshot_sha256,
            actor=self.owner,
        )

    def events(self, job: Job) -> list[sqlite3.Row]:
        with WorkflowStore(self.runner.store.db_path, read_only=True).connect() as connection:
            return connection.execute(
                "select * from events where run_id=? and event_type='owner.action.v1' "
                "order by event_id",
                (job.run_id,),
            ).fetchall()

    def protected_state(self) -> dict[str, object]:
        # Fixed real tables cover observations, quota, execution and learning independently.
        tables = (
            "runs",
            "steps",
            "approvals",
            "manual_outcomes",
            "manual_outcome_imports",
            "product_quotas",
            "product_usage",
            "kb_updates",
            "learned_feedback",
        )
        with WorkflowStore(self.runner.store.db_path, read_only=True).connect() as connection:
            state: dict[str, object] = {}
            for name in tables:
                query = f"select * from {name} order by rowid"  # noqa: S608 — fixed names above
                state[name] = [tuple(row) for row in connection.execute(query)]
        state["jobs"] = list(Job.objects.order_by("pk").values())
        state["files"] = {
            str(path.relative_to(self.root)): path.read_bytes()
            for folder in ("artifacts", "knowledge-base")
            for path in (self.root / folder).rglob("*")
            if path.is_file()
        }
        return state

    def test_cards_distinguish_missing_zero_complete_and_channel_without_new_facts(self) -> None:
        job = self.report()
        reviewed = report_services.verify(job)
        zero = reviewed.source
        missing = outcomes.OutcomeSnapshot(
            client="shop", week_start=WEEK, channel="naver", current=(), previous=()
        )
        start = date.fromisoformat(WEEK)
        row = zero.current[0]
        complete = outcomes.OutcomeSnapshot(
            client="shop",
            week_start=WEEK,
            channel="naver",
            current=tuple(
                row.model_copy(update={"date": str(start + timedelta(days=n)), "posts": 1})
                for n in range(7)
            ),
            previous=tuple(
                row.model_copy(update={"date": str(start + timedelta(days=n)), "posts": 2})
                for n in range(-7, 0)
            ),
        )
        before = self.protected_state()
        for snapshot in (missing, zero, complete):
            with self.subTest(posts=snapshot.totals["posts"].current):
                cards = action_services.cards(replace(reviewed, source=snapshot))
                self.assertEqual(
                    [card.code for card in cards],
                    ["review_records", "check_existing_news", "add_real_news"],
                )
                self.assertEqual([card.target for card in cards], ["outcomes", "archive", "create"])
                self.assertEqual([card.intent for card in cards], [None, None, "news"])
                self.assertIn(WEEK, cards[0].evidence)
                self.assertIn("naver", cards[0].evidence)
                for label in ("게시", "문의", "예약", "쿠폰 사용"):
                    self.assertIn(label, cards[0].evidence)
                self.assertIn("있다면", cards[2].title)
                self.assertEqual(cards[2], action_services.cards(reviewed)[2])
        missing_cards = action_services.cards(replace(reviewed, source=missing))
        self.assertIn("확인한 날이 없습니다", missing_cards[1].evidence)
        self.assertNotIn("0건", missing_cards[1].evidence)
        self.assertIn("0건", action_services.cards(reviewed)[1].evidence)
        full_cards = action_services.cards(replace(reviewed, source=complete))
        self.assertIn("같은 기준", full_cards[0].title)
        self.assertIn("7/7일", full_cards[1].evidence)
        self.assertIn("7건", full_cards[1].evidence)
        for channel in ("google-business", "instagram", "offline"):
            snapshot = outcomes.OutcomeSnapshot(
                client="shop", week_start=WEEK, channel=channel, current=(), previous=()
            )
            cards = action_services.cards(replace(reviewed, source=snapshot))
            self.assertEqual([card.code for card in cards], ["review_records"])
        self.assertEqual(
            action_services.cards(replace(reviewed, current=False)), action_services.cards(reviewed)
        )
        self.assertEqual(self.protected_state(), before)

    def test_selected_and_declined_actions_write_events_only(self) -> None:
        job = self.report()
        report = report_services.verify(job)
        before = self.protected_state()
        receipts = [
            self.record(job, report, decision=decision) for decision in ("selected", "declined")
        ]
        rows = self.events(job)
        self.assertEqual(len(rows), 2)
        for row, receipt in zip(rows, receipts, strict=True):
            self.assertEqual((row["run_id"], row["step_id"]), (job.run_id, None))
            self.assertEqual(
                action_services.ActionReceipt.model_validate_json(row["payload_json"]), receipt
            )
            self.assertEqual(receipt.schema_version, "aicmo.owner-action.v1")
        self.assertEqual(self.protected_state(), before)

    def test_same_key_replays_and_changed_payload_is_rejected(self) -> None:
        job = self.report()
        report = report_services.verify(job)
        key = uuid.uuid4()
        receipt = self.record(job, report, key=key)
        before = self.protected_state()
        self.assertEqual(self.record(job, report, key=key), receipt)
        changes: tuple[tuple[action_services.ActionCode, action_services.Decision, str], ...] = (
            ("review_records", "declined", receipt.reason),
            ("add_real_news", "selected", receipt.reason),
            ("review_records", "selected", "다른 이유입니다."),
        )
        for code, decision, reason in changes:
            with (
                self.subTest(code=code, decision=decision),
                self.assertRaises(services.StoreActionError),
            ):
                self.record(job, report, key=key, code=code, decision=decision, reason=reason)
        self.assertEqual(len(self.events(job)), 1)
        self.assertEqual(self.protected_state(), before)
        # A changed stored event must not become valid by cleaning it again during replay.
        pii_key = uuid.uuid4()
        raw_reason = "연락처 010-1234-5678을 제외하고 기록을 확인합니다."
        safe = self.record(job, report, key=pii_key, reason=raw_reason)
        self.assertNotEqual(safe.reason, raw_reason)
        row = self.events(job)[-1]
        payload = json.loads(row["payload_json"])
        payload["reason"] = raw_reason
        with self.runner.store.connect() as connection:
            connection.execute(
                "update events set payload_json=? where event_id=?",
                (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), row["event_id"]),
            )
        with self.assertRaises(services.StoreActionError):
            self.record(job, report, key=pii_key, reason=raw_reason)
        self.assertEqual(len(self.events(job)), 2)

    def test_concurrent_same_key_retries_lock_contention_to_one_receipt(self) -> None:
        job = self.report()
        report = report_services.verify(job)
        key = uuid.uuid4()
        entered, release = Event(), Event()
        verify = report_services.verify

        def verify_while_holding_lock(current: Job) -> report_services.ReviewedReport:
            if not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(timeout=15))
            return verify(current)

        def record(_index: int) -> action_services.ActionReceipt | None:
            close_old_connections()
            try:
                try:
                    return self.record(job, report, key=key)
                except OSError:
                    return None  # The caller retries after the competing request releases its lock.
            finally:
                close_old_connections()

        with (
            patch("aicmo.store_app.report_services.verify", side_effect=verify_while_holding_lock),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(record, 0)
            try:
                self.assertTrue(entered.wait(timeout=15))
                second = pool.submit(record, 1)
                self.assertIsNone(second.result(timeout=15))
            finally:
                release.set()
            committed = first.result(timeout=15)
        self.assertIsNotNone(committed)
        self.assertEqual(self.record(job, report, key=key), committed)
        self.assertEqual(len(self.events(job)), 1)

    def test_authority_hash_source_and_warn_fail_closed(self) -> None:
        job = self.report()
        report = report_services.verify(job)
        other = User.objects.create_user("action-other")
        for boundary in ("inactive", "owner", "client"):
            User.objects.filter(pk=self.owner.pk).update(is_active=boundary != "inactive")
            Store.objects.filter(pk=self.store.pk).update(
                owner_id=other.pk if boundary == "owner" else self.owner.pk,
                client="moved-client" if boundary == "client" else "shop",
            )
            with (
                self.subTest(boundary=boundary),
                patch("aicmo.store_app.report_services.verify", side_effect=AssertionError),
                self.assertRaises(Http404),
            ):
                self.record(job, report)
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        Store.objects.filter(pk=self.store.pk).update(owner_id=self.owner.pk, client="shop")
        moved = Store.objects.create(owner=self.owner, name="다른 합성 가게", client="other-shop")
        Store.objects.filter(pk=self.store.pk).update(client="old-shop")
        Store.objects.filter(pk=moved.pk).update(client="shop")
        Job.objects.filter(pk=job.pk).update(store=moved)
        try:
            # Same actor, client text and inputs cannot authorize a changed store identity.
            with (
                patch("aicmo.store_app.report_services.verify", side_effect=AssertionError),
                self.assertRaises(Http404),
            ):
                self.record(job, report)
        finally:
            Job.objects.filter(pk=job.pk).update(store=self.store)
            Store.objects.filter(pk=moved.pk).update(client="other-shop")
            Store.objects.filter(pk=self.store.pk).update(client="shop")
        with self.assertRaises(services.StoreActionError):
            self.record(job, replace(report, sha256="0" * 64))
        with self.assertRaises(services.StoreActionError):
            self.record(
                job, replace(report, source=report.source.model_copy(update={"current": ()}))
            )
        source = self.root / f"artifacts/{job.run_id}/weekly-report.md"
        source.write_bytes(b"synthetic tampered report")
        try:
            with self.assertRaises((AicmoError, services.StoreActionError)):
                self.record(job, report)
        finally:
            source.write_bytes(report.raw)
        offline = self.report(channel="offline")
        with self.assertRaises(services.StoreActionError):
            self.record(offline, report_services.verify(offline), code="add_real_news")
        warning = self.report(verdict="WARN")
        Job.objects.filter(pk=warning.pk).update(state="success")
        warning.refresh_from_db()
        raw = (self.root / f"artifacts/{warning.run_id}/weekly-report.md").read_bytes()
        with self.assertRaises((AicmoError, services.StoreActionError)):
            action_services.record_action(
                warning,
                "review_records",
                "selected",
                "확인합니다.",
                uuid.uuid4(),
                hashlib.sha256(raw).hexdigest(),
                outcomes.OutcomeSnapshot.model_validate_json(
                    warning.inputs["outcomes_snapshot_json"]
                ).snapshot_sha256,
                actor=self.owner,
            )
        for rejected in (job, offline, warning):
            self.assertEqual(self.events(rejected), [])

    def test_reason_rejects_secrets_minimizes_pii_and_preserves_receipt_identifiers(self) -> None:
        job = self.report()
        report = report_services.verify(job)
        secret = "sk-" + "SYNTHETICACTIONONLYNOACCOUNT0123456789ABCDE"
        self.assertTrue(contains_raw_secret(secret))
        for reason in (secret, "가" * 501):
            with self.assertRaises(services.StoreActionError):
                action_services.clean_reason(reason)
            with self.assertRaises(services.StoreActionError) as caught:
                self.record(job, report, reason=reason)
            self.assertNotIn(reason, str(caught.exception))
        self.assertEqual(self.events(job), [])
        raw = "Customer name: Jane Doe\n연락처 010-1234-5678\n확인한 기록부터 살펴보겠습니다."
        reason = action_services.clean_reason(raw)
        self.assertNotIn("Jane Doe", reason)
        self.assertNotIn("010-1234-5678", reason)
        self.assertIn("확인한 기록부터", reason)
        key = uuid.UUID(hex="a" * 21 + "01012345678")
        receipt = self.record(job, report, key=key, reason=raw)
        self.assertEqual(receipt.reason, reason)
        self.assertEqual(receipt.recorded_by, "web-user:15881234")
        self.assertEqual(receipt.request_key, str(key))
        self.assertEqual(
            (receipt.report_sha256, receipt.snapshot_sha256),
            (report.sha256, report.source.snapshot_sha256),
        )
        self.assertEqual(
            action_services.ActionReceipt.model_validate_json(self.events(job)[0]["payload_json"]),
            receipt,
        )

    def test_event_commit_then_response_failure_replays_without_duplicate(self) -> None:
        job = self.report()
        report = report_services.verify(job)
        key = uuid.uuid4()
        connect = WorkflowStore.connect
        failed = False

        @contextmanager
        def lost_response(store: WorkflowStore) -> Iterator[sqlite3.Connection]:
            nonlocal failed
            with connect(store) as connection:
                yield connection
            if not store.read_only and not failed:
                with connect(store) as committed:
                    exists = committed.execute(
                        "select 1 from events where run_id=? and event_type='owner.action.v1' "
                        "and json_extract(payload_json,'$.request_key')=?",
                        (job.run_id, str(key)),
                    ).fetchone()
                if exists:
                    failed = True
                    reason = "synthetic response lost after commit"
                    raise OSError(reason)

        before = self.protected_state()
        with patch.object(WorkflowStore, "connect", lost_response), self.assertRaises(OSError):
            self.record(job, report, key=key)
        self.assertTrue(failed)
        self.assertEqual(len(self.events(job)), 1)
        receipt = self.record(job, report, key=key)
        self.assertEqual(
            action_services.ActionReceipt.model_validate_json(self.events(job)[0]["payload_json"]),
            receipt,
        )
        self.assertEqual(len(self.events(job)), 1)
        self.assertEqual(self.protected_state(), before)
