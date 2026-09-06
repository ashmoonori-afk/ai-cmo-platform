from __future__ import annotations

import time
from argparse import ArgumentParser
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from aicmo.reporter import exclusive_file_lock
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from aicmo.store_app.models import Job
from aicmo.store_app.services import cancel, engine, execute


def run_one() -> bool:
    # ponytail: one job per repo; replace SQLite/file lock for measured multi-server demand.
    Path(settings.REPO_ROOT).joinpath(".aicmo").mkdir(exist_ok=True)
    with exclusive_file_lock(Path(settings.REPO_ROOT) / ".aicmo/web-worker.lock"):
        return _run_one()


def _run_one() -> bool:
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
    runner = engine()
    runner.store.initialize()
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
