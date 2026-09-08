from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ContentAdapter:
    content: str

    def generate(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(text=self.content)


@dataclass(frozen=True, slots=True)
class PassReviewer:
    verdict: str = "PASS"
    reason: str = "reviewed against policy"

    def generate(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(
            text=(
                '{"schema_version":"aicmo.reviewer-decision.v1",'
                f'"verdict":"{self.verdict}","reason":"{self.reason}"}}'
            ),
        )


def _runner(
    tmp_path: Path,
    content: str,
    *,
    reviewed: bool = True,
    review_verdict: str = "PASS",
    review_reason: str = "reviewed against policy",
) -> WorkflowRunner:
    write_text(
        tmp_path / "workflows" / "delivery.workflow.yaml",
        lines(
            "id: delivery",
            "name: Delivery",
            "steps:",
            "  - id: create",
            "    type: agent",
            '    outputs: ["artifacts/${run_id}/result.md"]',
            "  - id: delivery_gate",
            "    type: gate",
            "    terminal_delivery: true",
            "    depends_on: [create]",
            '    pass_if: "status in [\'PASS\',\'WARN\']"',
            '    outputs: ["artifacts/${run_id}/delivery-review.json"]',
        ),
    )
    return WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
        adapter=ContentAdapter(content),
        review_adapter=(
            PassReviewer(review_verdict, review_reason) if reviewed else None
        ),
    )


def _run_and_manifest(
    tmp_path: Path,
    content: str,
    *,
    reviewed: bool = True,
) -> tuple[str, dict[str, JsonValue]]:
    result = _runner(tmp_path, content, reviewed=reviewed).run("delivery", "run_1", {})
    manifest = cast(
        "dict[str, JsonValue]",
        json.loads(
            (tmp_path / "artifacts" / "run_1" / "delivery-review.json").read_text(
                "utf-8",
            ),
        ),
    )
    return result.status, manifest


def test_delivery_manifest_separates_run_success_from_sale_readiness(tmp_path: Path) -> None:
    clean = "검수 기준과 고객 요구를 충족한 완성 산출물입니다. " * 8

    status, manifest = _run_and_manifest(tmp_path / "reviewed", clean)
    assert status == "success"
    assert manifest["schema_version"] == "aicmo.delivery-manifest.v1"
    assert manifest["delivery_status"] == "deliverable"
    assert manifest["deliverable"] is True
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    artifact = cast("dict[str, JsonValue]", artifacts[0])
    assert isinstance(artifact, dict)
    assert artifact["version"] == "v1"
    assert isinstance(artifact["sha256"], str)
    assert len(artifact["sha256"]) == 64

    status, manifest = _run_and_manifest(tmp_path / "unreviewed", clean, reviewed=False)
    assert status == "success"
    assert manifest["delivery_status"] == "blocked"
    assert manifest["deliverable"] is False
    reasons = cast("list[JsonValue]", manifest["reasons"])
    assert isinstance(reasons, list)
    assert "semantic reviewer was not configured" in reasons

    status, manifest = _run_and_manifest(tmp_path / "unknown", clean + " [미확인]")
    assert status == "success"
    assert manifest["status"] == "WARN"
    assert manifest["deliverable"] is False

    sourced_price = clean + "월 30만 원입니다 (출처: clients/shop/pricing-rules.md)."
    status, manifest = _run_and_manifest(tmp_path / "sourced-price", sourced_price)
    assert status == "success"
    assert manifest["deliverable"] is True


def test_offline_stub_is_explicit_demo_output(tmp_path: Path) -> None:
    prepared = _runner(tmp_path, "unused")
    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=prepared.store,
        review_adapter=PassReviewer(),
    )

    result = runner.run("delivery", "run_demo", {})
    manifest = json.loads(
        (tmp_path / "artifacts" / "run_demo" / "delivery-review.json").read_text("utf-8"),
    )

    assert result.status == "success"
    assert manifest["delivery_status"] == "demo"
    assert manifest["deliverable"] is False


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("월 300,000원으로 제공하는 상품입니다. " * 5, "price claim has no source"),
        ("월 30만원으로 제공하는 상품입니다. " * 5, "price claim has no source"),
        (
            "월 30만 원입니다. 자세한 내용은 https://example.com을 보세요. " * 4,
            "price claim has no source",
        ),
        ("이 상품은 고객의 매출 보장을 약속합니다. " * 5, "unsafe marketing claim"),
        ("이 서비스는 검색 1위를 보장한다고 약속합니다. " * 5, "unsafe marketing claim"),
        ("필수 가격은 {{price}}이며 계약 전에 확정합니다. " * 5, "unfilled placeholder"),
    ],
)
def test_delivery_gate_fails_closed_for_required_claims(
    tmp_path: Path,
    content: str,
    reason: str,
) -> None:
    status, manifest = _run_and_manifest(tmp_path, content)

    assert status == "failed"
    assert manifest["status"] == "FAIL"
    assert manifest["deliverable"] is False
    reasons = cast("list[JsonValue]", manifest["reasons"])
    assert isinstance(reasons, list)
    assert any(reason in item for item in reasons if isinstance(item, str))


def test_delivery_manifest_blocks_truncated_review(tmp_path: Path) -> None:
    status, manifest = _run_and_manifest(tmp_path, "충분히 긴 산출물입니다. " * 1000)

    assert status == "success"
    assert manifest["delivery_status"] == "blocked"
    assert manifest["deliverable"] is False
    review_input = cast("dict[str, JsonValue]", manifest["review_input"])
    assert isinstance(review_input, dict)
    assert review_input["truncated"] is True


@pytest.mark.parametrize("verdict", ["WARN", "FAIL"])
def test_delivery_manifest_preserves_reviewer_reason(tmp_path: Path, verdict: str) -> None:
    reason = "고객 가격이 config와 불일치합니다"
    runner = _runner(
        tmp_path,
        "검토가 필요한 충분히 긴 고객 산출물입니다. " * 8,
        review_verdict=verdict,
        review_reason=reason,
    )

    runner.run("delivery", "reason_case", {})
    manifest = json.loads(
        (tmp_path / "artifacts" / "reason_case" / "delivery-review.json").read_text("utf-8"),
    )

    assert manifest["deliverable"] is False
    assert manifest["semantic_review"] == {
        "status": verdict,
        "reason": reason,
        "outcome": "parsed",
    }
    assert reason in manifest["reasons"]
