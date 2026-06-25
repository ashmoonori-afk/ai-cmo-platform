from __future__ import annotations

import re
from dataclasses import dataclass

from aicmo.adapters import OFFLINE_STUB_MARKER
from aicmo.models import GateDecision

_INCOMPLETE_MARKERS = ("TODO", "TBD", "FIXME", "입력 필요", "작성 필요", "[작성")
_UNFILLED_TOKEN = re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")
_STATUS_TOKEN = re.compile(r"'([A-Z]+)'")
_THIN_LENGTH = 80
_DEFAULT_ALLOWED = frozenset({"PASS", "WARN"})


@dataclass(frozen=True, slots=True)
class GateOutcome:
    status: GateDecision
    reasons: tuple[str, ...]


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
