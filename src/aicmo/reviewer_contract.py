from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

from aicmo.adapters import AgentRequest, AgentResult, StepAdapter
from aicmo.gate import (
    REVIEW_DECISION_SCHEMA_VERSION,
    MalformedReviewerDecisionError,
    parse_reviewer_decision,
)
from aicmo.models import GateDecision

REVIEW_CONTRACT: Final = (
    "Judge the artifact against the quality gate: clarity, completeness, accuracy, brand "
    "fit, and safety. Return exactly one JSON object and no other text: "
    '{"schema_version":"aicmo.reviewer-decision.v1","verdict":"PASS|WARN|FAIL",'
    '"reason":"one line, 1-500 characters"}.'
)
_REVIEW_REPAIR_CONTRACT: Final = (
    "Reformat the supplied malformed reviewer response into the exact reviewer-decision "
    "JSON schema. Preserve its decision; do not re-review the artifact, infer a missing "
    "decision, or add prose."
)
REVIEW_INPUT_LIMIT: Final = 8000
_REVIEW_REPAIR_INPUT_LIMIT: Final = 2000
REVIEW_CLIENT_CRITERIA_LIMIT: Final = 6000
REVIEW_CLIENT_CRITERIA: Final = ("config.md", "brand-guidelines.md")
type ReviewerResolutionOutcome = Literal[
    "unavailable",
    "repair_unavailable",
    "malformed",
    "repaired",
    "parsed",
]


@dataclass(frozen=True, slots=True)
class ReviewerResolution:
    decision: GateDecision
    reason: str
    outcome: ReviewerResolutionOutcome
    attempts: Literal[1, 2]
    initial_response: str
    effective_response: str


def resolve_reviewer_output(
    adapter: StepAdapter,
    request: AgentRequest,
    initial: AgentResult,
    *,
    generate: Callable[[AgentRequest], AgentResult] | None = None,
) -> ReviewerResolution:
    if not initial.ok:
        return ReviewerResolution(
            GateDecision.FAIL,
            "semantic reviewer was unavailable",
            "unavailable",
            1,
            initial.text,
            initial.text,
        )
    try:
        parsed = parse_reviewer_decision(initial.text)
    except MalformedReviewerDecisionError:
        repaired = (generate or adapter.generate)(
            AgentRequest(
                step_id=request.step_id,
                run_id=request.run_id,
                workflow_id=request.workflow_id,
                role="reviewer-format-repair",
                role_contract=_REVIEW_REPAIR_CONTRACT,
                prompt_source=initial.text[:_REVIEW_REPAIR_INPUT_LIMIT],
                inputs_json=json.dumps(
                    {"schema_version": REVIEW_DECISION_SCHEMA_VERSION},
                    separators=(",", ":"),
                ),
                model=request.model,
            ),
        )
        if not repaired.ok:
            return ReviewerResolution(
                GateDecision.FAIL,
                "reviewer output was malformed and repair was unavailable",
                "repair_unavailable",
                2,
                initial.text,
                repaired.text,
            )
        try:
            parsed = parse_reviewer_decision(repaired.text)
        except MalformedReviewerDecisionError:
            return ReviewerResolution(
                GateDecision.FAIL,
                "reviewer output remained malformed after repair",
                "malformed",
                2,
                initial.text,
                repaired.text,
            )
        return ReviewerResolution(
            GateDecision(parsed.verdict.value),
            parsed.reason,
            "repaired",
            2,
            initial.text,
            repaired.text,
        )
    return ReviewerResolution(
        GateDecision(parsed.verdict.value),
        parsed.reason,
        "parsed",
        1,
        initial.text,
        initial.text,
    )
