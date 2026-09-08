from __future__ import annotations

import sqlite3
import time
from argparse import ArgumentParser
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from aicmo.errors import AicmoError, RunNotFoundError
from aicmo.reporter import exclusive_file_lock
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from aicmo.store_app.models import Job
from aicmo.store_app.onboarding_publish import run_onboarding
from aicmo.store_app.services import StoreActionError, cancel, engine, execute

_SETUP_ERRORS = (AicmoError, OSError, ValueError, sqlite3.Error, StoreActionError)


def _setup_unavailable(job: Job) -> bool:
    job.refresh_from_db()
    root = Path(settings.REPO_ROOT)
    store = WorkflowStore(root / ".aicmo/runs.sqlite3", read_only=True)
    if job.cancel_requested:
        runner = WorkflowRunner(root, WorkflowStore(store.db_path))
        try:
            runner.store.initialize()
            cancel(job, runner)
        except _SETUP_ERRORS:
            Job.objects.filter(pk=job.pk, cancel_requested=True).update(
                notice="취소 상태를 확인하지 못했습니다. 운영자에게 문의해 주세요."
            )
            return False
        return True
    exists = store.db_path.exists()
    if exists:
        try:
            store.get_run(job.run_id)
        except RunNotFoundError:
            exists = False
        except _SETUP_ERRORS:
            pass  # An unreadable or running engine cannot safely be declared failed.
    if exists:
        Job.objects.filter(
            pk=job.pk, state__in=["queued", "running"], cancel_requested=False
        ).update(notice="작업 설정을 확인하지 못했습니다. 운영자에게 문의하거나 취소해 주세요.")
        return False
    Job.objects.filter(
        pk=job.pk, state__in=["queued", "running"], cancel_requested=False
    ).update(state="failed", notice="작업을 시작하지 못했습니다. 운영자에게 문의해 주세요.")
    return True


def run_one() -> bool:
    # ponytail: one job per repo; replace SQLite/file lock for measured multi-server demand.
    Path(settings.REPO_ROOT).joinpath(".aicmo").mkdir(exist_ok=True)
    with exclusive_file_lock(Path(settings.REPO_ROOT) / ".aicmo/web-worker.lock"):
        return _run_one()


def _run_one() -> bool:
    if run_onboarding():
        return True
    job = (
        Job.objects.filter(Q(state__in=["queued", "running"]) | Q(cancel_requested=True))
        .order_by("created_at")
        .first()
    )
    if job is None:
        return False
    if job.cancel_requested:
        root = Path(settings.REPO_ROOT)
        runner = WorkflowRunner(root, WorkflowStore(root / ".aicmo/runs.sqlite3"))
        runner.store.initialize()
        cancel(job, runner)
        return True
    try:
        runner = engine(job.workflow_id)
        runner.store.initialize()
    except _SETUP_ERRORS:
        return _setup_unavailable(job)
    threshold = (datetime.now(UTC) - timedelta(seconds=runner.lease_ttl_seconds)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    with runner.store.connect() as connection:
        alive = connection.execute(
            "select 1 from steps where run_id=? and status='running' "
            "and locked_by is not null and locked_at>?",
            (job.run_id, threshold),
        ).fetchone()
    if alive is not None and not job.cancel_requested:
        return False
    execute(job, runner)
    return True


class Command(BaseCommand):
    help = "Process persisted store jobs; one worker per repository."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--once", action="store_true")

    def handle(self, *args: object, **options: object) -> None:  # noqa: ARG002 — Django hook
        while True:
            worked = run_one()
            if options["once"]:
                return
            if not worked:
                time.sleep(1)
