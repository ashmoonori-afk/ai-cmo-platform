"""Explicit owner-confirmed rewrite inputs; the existing worker owns generation and quota."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aicmo.errors import WorkflowExecutionError
from aicmo.local_pack import INPUT_STEP, MAX_PACK_BYTES, LocalPack, unique_json_pairs
from aicmo.models import EditBase, Hash
from aicmo.redaction import contains_raw_secret, minimize_customer_pii


class RewriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["aicmo.pack-rewrite.v1"]
    source_run_id: str = Field(pattern=r"^web-[a-f0-9]{32}$")
    base: EditBase
    revision: int = Field(ge=0)
    edited_sha: Hash
    source_body: str
    action: Literal["shorten", "friendly", "price"]
    confirmed_by: str = Field(pattern=r"^web-user:[1-9][0-9]*$")
    facts_sha: Hash


def facts_sha(facts: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(facts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def parse_rewrite(raw: str) -> RewriteRequest:
    try:
        if len(raw.encode("utf-8")) > 64 * 1024 or contains_raw_secret(raw):
            raise ValueError  # noqa: TRY301 — one sanitized validation error boundary
        json.loads(raw, object_pairs_hook=unique_json_pairs)
        request = RewriteRequest.model_validate_json(raw)
        if (
            len(request.source_body.encode("utf-8")) > MAX_PACK_BYTES
            or hashlib.sha256(request.source_body.encode("utf-8")).hexdigest() != request.edited_sha
        ):
            raise ValueError  # noqa: TRY301 — one sanitized validation error boundary
        json.loads(request.source_body, object_pairs_hook=unique_json_pairs)
        # Only prose is checked; phone-shaped SHA/run IDs must remain intact.
        pack = LocalPack.model_validate_json(request.source_body)
        prose = pack.model_dump_json()
        if contains_raw_secret(prose) or minimize_customer_pii(prose) != prose:
            raise ValueError  # noqa: TRY301 — one sanitized validation error boundary
    except (ValueError, RecursionError):
        raise WorkflowExecutionError(INPUT_STEP, "invalid owner-confirmed rewrite input") from None
    return request
