"""Small web adapter for the existing manual outcome ledger."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import Http404
from pydantic import BaseModel, ConfigDict, Field

from aicmo import outcomes
from aicmo.store import WorkflowStore
from aicmo.store_app import services
from aicmo.store_app.models import Store

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

TOKEN_SALT = "aicmo.outcomes.confirm.v1"
TOKEN_MAX_AGE = 15 * 60
MAX_TOKEN_LENGTH = 2048
MAX_ENCODED_CSV = ((outcomes.MAX_CSV_BYTES + 2) // 3) * 4
type WebInputKind = Literal["web_csv", "web_manual"]
type Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Confirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    actor_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    client: str = Field(min_length=1, max_length=128)
    week_start: str = Field(pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
    channel: outcomes.Channel
    input_kind: WebInputKind
    source_sha256: Digest
    confirmation_sha256: Digest
    replace_required: bool


@dataclass(frozen=True)
class PreparedOutcome:
    preview: outcomes.OutcomePreview
    token: str
    raw_csv: str
    replace_required: bool


def read(store: Store, week_start: str, channel: outcomes.Channel) -> outcomes.OutcomeSnapshot:
    root = Path(settings.REPO_ROOT)
    return outcomes.read_weekly_outcomes(
        root,
        WorkflowStore(root / ".aicmo/runs.sqlite3", read_only=True),
        store.client,
        week_start,
        channel,
    )


def prepare(
    actor: AbstractBaseUser | AnonymousUser,
    store: Store,
    week_start: str,
    channel: outcomes.Channel,
    raw: bytes,
    input_kind: WebInputKind,
) -> PreparedOutcome:
    actor_id = actor.pk
    if type(actor_id) is not int or actor_id <= 0:
        raise Http404
    root = Path(settings.REPO_ROOT)
    preview = outcomes.preview_outcomes_bytes(
        root,
        WorkflowStore(root / ".aicmo/runs.sqlite3", read_only=True),
        store.client,
        week_start,
        channel,
        raw,
    )
    existing = {item.date: item for item in preview.existing}
    changed = any(
        row.date in existing
        and any(
            getattr(row, metric) != getattr(existing[row.date], metric)
            for metric in outcomes.METRICS
        )
        for row in preview.rows
    )
    envelope = Confirmation(
        actor_id=actor_id,
        store_id=store.pk,
        client=store.client,
        week_start=week_start,
        channel=channel,
        input_kind=input_kind,
        source_sha256=preview.source_sha256,
        confirmation_sha256=preview.confirmation_sha256,
        replace_required=changed,
    )
    return PreparedOutcome(
        preview,
        signing.dumps(envelope.model_dump(), salt=TOKEN_SALT),
        base64.b64encode(raw).decode("ascii"),
        changed,
    )


def decode(
    actor: AbstractBaseUser | AnonymousUser,
    store: Store,
    token: str,
    raw_csv: str,
) -> tuple[Confirmation, bytes]:
    if len(token) > MAX_TOKEN_LENGTH or len(raw_csv) > MAX_ENCODED_CSV:
        reason = "Invalid confirmation size"
        raise ValueError(reason)
    envelope = Confirmation.model_validate(
        signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
    )
    if (
        envelope.actor_id != actor.pk
        or envelope.store_id != store.pk
        or envelope.client != store.client
    ):
        raise Http404
    raw = base64.b64decode(raw_csv, validate=True)
    if (
        len(raw) > outcomes.MAX_CSV_BYTES
        or hashlib.sha256(raw).hexdigest() != envelope.source_sha256
    ):
        reason = "Confirmed source changed"
        raise ValueError(reason)
    return envelope, raw


def save(
    actor: AbstractBaseUser | AnonymousUser,
    store: Store,
    token: str,
    raw_csv: str,
    *,
    replace: bool,
) -> int:
    envelope, raw = decode(actor, store, token, raw_csv)
    if envelope.replace_required and not replace:
        reason = "Correction must be confirmed"
        raise ValueError(reason)
    root = Path(settings.REPO_ROOT)
    with transaction.atomic():
        current_actor = services.fresh_actor(actor)
        current = services.owned_store(current_actor, store.pk)
        if current.client != envelope.client:
            raise Http404
        return outcomes.import_outcomes_bytes(
            root,
            WorkflowStore(root / ".aicmo/runs.sqlite3"),
            current.client,
            envelope.week_start,
            envelope.channel,
            raw,
            envelope.confirmation_sha256,
            replace=replace,
            provenance=outcomes.OutcomeImportSource(
                kind=envelope.input_kind,
                recorded_by=f"web-user:{current_actor.pk}",
            ),
        )
