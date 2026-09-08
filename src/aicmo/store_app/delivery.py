# pyright: reportImportCycles=false
# The view loads publication context only after snapshot is defined; no runtime import cycle.
from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from aicmo.errors import AicmoError
from aicmo.photos import parse_photos
from aicmo.store_app import services
from aicmo.store_app.models import Job

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


@dataclass(frozen=True)
class DeliveryCard:
    key: str
    file_sha: str
    text: str
    title: str
    photo_filename: str = ""


@dataclass(frozen=True)
class DeliverySnapshot:
    bundle_sha: str
    cards: list[DeliveryCard]
    guide: str


def snapshot(job: Job) -> DeliverySnapshot:
    """Read the exact approved export bytes without making an export or charging usage."""
    bundle_sha, files = services.verified_files(job)
    cards: list[DeliveryCard] = []
    for filename, content in files.items():
        match = re.fullmatch(r"(news|reply)-([1-9][0-9]*)\.txt", filename)
        if match is None:
            continue
        kind, number = match.groups()
        photo = f"photos/news-{number}.png" if kind == "news" else ""
        cards.append(
            DeliveryCard(
                key=filename.removesuffix(".txt"),
                file_sha=hashlib.sha256(content).hexdigest(),
                text=content.decode("utf-8"),
                title=f"소식 {number}" if kind == "news" else f"리뷰 {number} 답글",
                photo_filename=photo if photo in files else "",
            )
        )
    return DeliverySnapshot(bundle_sha, cards, files["guide.md"].decode("utf-8"))


@login_required
@require_GET
@never_cache
def detail(request: HttpRequest, job_id: uuid.UUID) -> HttpResponse:
    from aicmo.store_app import publication  # noqa: PLC0415 — publication records verify snapshots

    job = services.owned_job(request.user, job_id)
    try:
        delivery = snapshot(job)
        rows = [
            {
                "card": card,
                "publication": publication.context(
                    job, delivery.bundle_sha, card.key, card.file_sha
                ),
            }
            for card in delivery.cards
        ]
        photos = parse_photos(job.inputs).photos
    except (AicmoError, OSError, ValueError, sqlite3.Error, services.StoreActionError):
        return render(
            request,
            "store_app/error.html",
            {
                "job": job,
                "notice": "승인된 결과를 확인할 수 없습니다. 최신 작업 상태를 확인해 주세요.",
            },
            status=409,
        )
    return render(
        request,
        "store_app/delivery.html",
        {"job": job, "delivery": delivery, "rows": rows, "photos": photos},
    )
