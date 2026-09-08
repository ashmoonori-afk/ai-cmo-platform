from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from aicmo.adapters import AgentRequest, AgentResult, GenerationUsage
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text

_REVIEW_SCHEMA = "aicmo.reviewer-decision.v1"


def _decision(
    verdict: Literal["PASS", "WARN", "FAIL"],
    reason: str = "machine-readable review",
) -> str:
    return json.dumps(
        {"schema_version": _REVIEW_SCHEMA, "verdict": verdict, "reason": reason},
    )


@dataclass(frozen=True, slots=True)
class CompleteAdapter:
    def generate(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(text="complete reviewed artifact " * 5, ok=True)


class SequencedReviewAdapter:
    seen: list[AgentRequest]
    _results: Iterator[AgentResult]

    def __init__(self, results: list[AgentResult]) -> None:
        self.seen = []
        self._results = iter(results)

    def generate(self, request: AgentRequest) -> AgentResult:
        self.seen.append(request)
        return next(self._results)


def test_review_and_repair_have_separate_usage_and_minimized_input(tmp_path: Path) -> None:
    usage = GenerationUsage("anthropic", "claude-sonnet-4-6", input_tokens=120, output_tokens=35)
    adapter = SequencedReviewAdapter(
        [
            AgentResult("PASS Customer name: Jane Doe", usage=usage),
            AgentResult(_decision("PASS"), usage=usage),
        ]
    )
    runner, store = _runner(tmp_path, adapter)
    assert runner.run("review-fixture", "usage-case", {"client": "acme"}).status == "success"
    assert "Jane Doe" not in adapter.seen[1].prompt_source
    with store.connect() as connection:
        rows = connection.execute(
            "select payload_json from events where event_type='agent.call_finished' "
            "and step_id='review' order by event_id",
        ).fetchall()
    payloads = [json.loads(row["payload_json"]) for row in rows]
    assert len(payloads) == 2
    assert payloads[0]["call_id"] != payloads[1]["call_id"]
    assert [p["role"] for p in payloads] == ["reviewer", "reviewer-format-repair"]
    assert all(p["usage_status"] == "reported" for p in payloads)
    assert all(p["input_tokens"] == "120" for p in payloads)
    assert all(p["cost_status"] == "unavailable" for p in payloads)
    assert all(int(p["elapsed_ms"]) >= 0 for p in payloads)
    assert all(p["attempt"] == "1" for p in payloads)
    assert "Jane Doe" not in json.dumps(payloads)


def _runner(
    tmp_path: Path,
    review_adapter: SequencedReviewAdapter,
) -> tuple[WorkflowRunner, WorkflowStore]:
    write_text(tmp_path / "clients" / "acme" / "config.md", "# Acme\n")
    write_text(
        tmp_path / "clients" / "acme" / "brand-guidelines.md",
        "# Brand\n\nEvidence-led.\n",
    )
    write_text(tmp_path / "agents" / "reviewer.md", "# Reviewer\n")
    write_text(tmp_path / "prompts" / "shared" / "gate-check.md", "# Gate Check\n")
    write_text(
        tmp_path / "workflows" / "review-fixture.workflow.yaml",
        lines(
            "id: review-fixture",
            "name: Review Fixture",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: draft",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/draft.md",
            "  - id: review",
            "    type: gate",
            "    role: reviewer",
            "    prompt: prompts/shared/gate-check.md",
            "    depends_on: [draft]",
            "    outputs:",
            "      - artifacts/${run_id}/review.json",
        ),
    )
    store = WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3")
    return (
        WorkflowRunner(
            repo_root=tmp_path,
            store=store,
            adapter=CompleteAdapter(),
            review_adapter=review_adapter,
        ),
        store,
    )


@pytest.mark.parametrize(
    "malformed",
    [
        "NOT PASS",
        "PASSIVE",
        "",
        json.dumps({"schema_version": _REVIEW_SCHEMA, "reason": "missing verdict"}),
        f"prefix {_decision('PASS')}",
        f"{_decision('PASS')}\n{_decision('FAIL')}",
        pytest.param(
            '{"schema_version":"aicmo.reviewer-decision.v1","verdict":"WARN",'
            '"verdict":"PASS","reason":"duplicate verdict"}',
            id="duplicate-verdict",
        ),
        pytest.param(
            '{"schema_version":"unexpected","schema_version":'
            '"aicmo.reviewer-decision.v1","verdict":"PASS",'
            '"reason":"duplicate schema version"}',
            id="duplicate-schema-version",
        ),
        pytest.param(
            _decision("PASS", reason="first line\nsecond line"),
            id="multiline-reason",
        ),
        pytest.param(
            _decision("PASS", reason="first line\u0085second line"),
            id="unicode-next-line",
        ),
        pytest.param(
            _decision("PASS", reason="first line\u2028second line"),
            id="unicode-line-separator",
        ),
        pytest.param(
            _decision("PASS", reason="first line\u2029second line"),
            id="unicode-paragraph-separator",
        ),
    ],
)
def test_semantic_review_fails_closed_after_one_malformed_repair(
    tmp_path: Path,
    malformed: str,
) -> None:
    review_adapter = SequencedReviewAdapter(
        [AgentResult(text=malformed), AgentResult(text=malformed)],
    )
    runner, _store = _runner(tmp_path, review_adapter)

    result = runner.run(
        workflow_id="review-fixture",
        run_id="run_malformed",
        inputs={"client": "acme"},
    )

    assert result.status == "failed"
    assert result.failed_step_id == "review"
    assert len(review_adapter.seen) == 2


def test_semantic_review_repairs_structure_once_and_records_provenance(
    tmp_path: Path,
) -> None:
    review_adapter = SequencedReviewAdapter(
        [AgentResult(text="PASS"), AgentResult(text=_decision("PASS"))],
    )
    runner, store = _runner(tmp_path, review_adapter)

    result = runner.run(
        workflow_id="review-fixture",
        run_id="run_repaired",
        inputs={"client": "acme"},
    )

    assert result.status == "success"
    assert len(review_adapter.seen) == 2
    assert review_adapter.seen[1].role == "reviewer-format-repair"
    assert len(review_adapter.seen[1].prompt_source) <= 2000
    with store.connect() as connection:
        event = connection.execute(
            "select payload_json from events where run_id = ? and event_type = ?",
            ("run_repaired", "gate.reviewer"),
        ).fetchone()
    assert event is not None
    payload = json.loads(str(event["payload_json"]))
    assert payload["schema_version"] == _REVIEW_SCHEMA
    assert payload["adapter"] == "SequencedReviewAdapter"
    assert payload["attempts"] == "2"
    assert payload["outcome"] == "repaired"
    assert payload["effective_decision"] == "PASS"
    assert len(payload["input_sha256"]) == 64
    assert len(payload["initial_response_sha256"]) == 64
    assert len(payload["effective_response_sha256"]) == 64


def test_semantic_review_records_distinct_initial_and_shared_effective_hashes(
    tmp_path: Path,
) -> None:
    repaired = _decision("PASS")
    first_adapter = SequencedReviewAdapter(
        [AgentResult(text="PASS"), AgentResult(text=repaired)],
    )
    first_runner, store = _runner(tmp_path, first_adapter)
    second_adapter = SequencedReviewAdapter(
        [AgentResult(text="PASS with confidence"), AgentResult(text=repaired)],
    )
    second_runner, _second_store = _runner(tmp_path, second_adapter)

    first = first_runner.run(
        workflow_id="review-fixture",
        run_id="run_first_original",
        inputs={"client": "acme"},
    )
    second = second_runner.run(
        workflow_id="review-fixture",
        run_id="run_second_original",
        inputs={"client": "acme"},
    )

    assert first.status == "success"
    assert second.status == "success"
    assert len(first_adapter.seen) == 2
    assert len(second_adapter.seen) == 2
    with store.connect() as connection:
        rows = connection.execute(
            "select run_id, payload_json from events "
            "where event_type = ? and run_id in (?, ?) order by run_id",
            ("gate.reviewer", "run_first_original", "run_second_original"),
        ).fetchall()
    assert len(rows) == 2
    first_payload = json.loads(str(rows[0]["payload_json"]))
    second_payload = json.loads(str(rows[1]["payload_json"]))
    assert first_payload["attempts"] == second_payload["attempts"] == "2"
    assert first_payload["outcome"] == second_payload["outcome"] == "repaired"
    assert first_payload["initial_response_sha256"] != second_payload["initial_response_sha256"]
    assert first_payload["effective_response_sha256"] == second_payload["effective_response_sha256"]


def test_semantic_review_does_not_repair_a_valid_fail(tmp_path: Path) -> None:
    review_adapter = SequencedReviewAdapter(
        [AgentResult(text=_decision("FAIL")), AgentResult(text=_decision("PASS"))],
    )
    runner, _store = _runner(tmp_path, review_adapter)

    result = runner.run(
        workflow_id="review-fixture",
        run_id="run_valid_fail",
        inputs={"client": "acme"},
    )

    assert result.status == "failed"
    assert len(review_adapter.seen) == 1


def test_semantic_review_request_carries_policy_artifacts_and_client_criteria(
    tmp_path: Path,
) -> None:
    review_adapter = SequencedReviewAdapter([AgentResult(text=_decision("PASS"))])
    runner, _store = _runner(tmp_path, review_adapter)

    result = runner.run(
        workflow_id="review-fixture",
        run_id="run_review_contract",
        inputs={"client": "acme"},
    )

    assert result.status == "success"
    request = review_adapter.seen[0]
    inputs = json.loads(request.inputs_json)
    assert inputs["policy_version"] == _REVIEW_SCHEMA
    assert inputs["policy_sources"] == ["agents/reviewer.md", "prompts/shared/gate-check.md"]
    assert inputs["client"] == "acme"
    assert {item["path"] for item in inputs["client_criteria"]} == {
        "clients/acme/config.md",
        "clients/acme/brand-guidelines.md",
    }
    assert tuple(ref.producer_step_id for ref in request.artifact_refs) == ("draft",)
