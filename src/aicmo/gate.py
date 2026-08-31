from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from aicmo.adapters import OFFLINE_STUB_MARKER
from aicmo.models import GateDecision

_INCOMPLETE_MARKERS = ("TODO", "TBD", "FIXME", "입력 필요", "작성 필요", "[작성")
_UNFILLED_TOKEN = re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")
_STATUS_TOKEN = re.compile(r"'([A-Z]+)'")
_THIN_LENGTH = 80
_DEFAULT_ALLOWED = frozenset({"PASS", "WARN"})
REVIEW_DECISION_SCHEMA_VERSION: Final = "aicmo.reviewer-decision.v1"
_REASON_SINGLE_LINE_ERROR: Final = "reason_not_single_line"
type _JsonValue = str | int | float | bool | None | list[_JsonValue] | dict[str, _JsonValue]


@dataclass(frozen=True, slots=True)
class GateOutcome:
    status: GateDecision
    reasons: tuple[str, ...]


class ReviewerVerdict(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class ReviewerDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["aicmo.reviewer-decision.v1"]
    verdict: ReviewerVerdict
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason", mode="before")
    @classmethod
    def require_single_line_reason(cls, reason: str) -> str:
        if len(f"_{reason}_".splitlines()) != 1:
            raise PydanticCustomError(
                _REASON_SINGLE_LINE_ERROR,
                "reason must be a single line",
            )
        return reason


class MalformedReviewerDecisionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _DuplicateReviewerKeyError(ValueError):
    key: str

    def __str__(self) -> str:
        return f"duplicate reviewer JSON key: {self.key}"


def _reject_duplicate_keys(
    pairs: list[tuple[str, _JsonValue]],
) -> dict[str, _JsonValue]:
    decoded: dict[str, _JsonValue] = {}
    for key, value in pairs:
        if key in decoded:
            raise _DuplicateReviewerKeyError(key)
        decoded[key] = value
    return decoded


def evaluate_artifacts(texts: list[str]) -> GateOutcome:
    """Deterministic completeness/safety gate over the gated artifacts.

    FAIL on empty content, an incomplete marker (TODO/TBD/...), or an unfilled
    template token. WARN on unusually thin content. PASS otherwise.
    """
    combined = "".join(texts).strip()
    if not combined:
        return GateOutcome(GateDecision.FAIL, ("artifact is empty",))
    if any(OFFLINE_STUB_MARKER in text for text in texts):
        return GateOutcome(GateDecision.WARN, ("offline stub output — not a live deliverable",))
    reasons: list[str] = []
    for text in texts:
        reasons.extend(
            f"incomplete marker present: {marker}"
            for marker in _INCOMPLETE_MARKERS
            if marker in text
        )
        if _UNFILLED_TOKEN.search(text):
            reasons.append("unfilled placeholder token present")
    if reasons:
        return GateOutcome(GateDecision.FAIL, tuple(dict.fromkeys(reasons)))
    if len(combined) < _THIN_LENGTH:
        return GateOutcome(GateDecision.WARN, ("content is unusually thin",))
    return GateOutcome(GateDecision.PASS, ())


def allowed_statuses(pass_if: str | None) -> frozenset[str]:
    """Statuses that let the gate continue. Defaults to PASS/WARN when unparseable."""
    if not pass_if:
        return _DEFAULT_ALLOWED
    found = frozenset(_STATUS_TOKEN.findall(pass_if))
    return found or _DEFAULT_ALLOWED


_SEVERITY = {
    GateDecision.PASS: 0,
    GateDecision.WARN: 1,
    GateDecision.WAITING_APPROVAL: 2,
    GateDecision.ESCALATE: 3,
    GateDecision.FAIL: 3,
}


def parse_reviewer_decision(text: str) -> ReviewerDecision:
    try:
        json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        return ReviewerDecision.model_validate_json(text)
    except (json.JSONDecodeError, _DuplicateReviewerKeyError, ValidationError) as exc:
        raise MalformedReviewerDecisionError from exc


def stricter(left: GateDecision, right: GateDecision) -> GateDecision:
    """Return the harsher of two gate decisions (FAIL/ESCALATE beat WARN beat PASS)."""
    return left if _SEVERITY[left] >= _SEVERITY[right] else right
