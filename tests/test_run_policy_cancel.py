from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from queue import SimpleQueue
from threading import Event, Thread
from typing import Never

import pytest

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.anthropic_adapter import AnthropicAdapter
from aicmo.errors import RunConflictError, StepTransitionError
from aicmo.models import RunResult, RunStatus, StepStatus
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


@dataclass
class GoodAdapter:
    calls: list[str] = field(default_factory=list)

    def generate(self, request: AgentRequest) -> AgentResult:
        self.calls.append(request.step_id)
        return AgentResult(text="완료된 고객 산출물입니다. " * 8)


@dataclass
class FailingAdapter:
    calls: int = 0

    def generate(self, _request: AgentRequest) -> AgentResult:
        self.calls += 1
        return AgentResult(text="", ok=False, detail="provider unavailable")


@dataclass
class BlockingAdapter:
    started: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)
    calls: list[str] = field(default_factory=list)

    def generate(self, request: AgentRequest) -> AgentResult:
        self.calls.append(request.step_id)
        if request.step_id == "second":
            self.started.set()
            assert self.release.wait(timeout=10)
        return AgentResult(text="취소 전 완료된 고객 산출물입니다. " * 8)


@dataclass
class FailingMessages:
    calls: int = 0

    def create(self, **_kwargs: object) -> Never:
        self.calls += 1
        message = "provider unavailable"
        raise RuntimeError(message)


@dataclass(frozen=True, slots=True)
class FakeClient:
    messages: FailingMessages


@dataclass(frozen=True, slots=True)
class PassReviewer:
    def generate(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(
            text=(
                '{"schema_version":"aicmo.reviewer-decision.v1",'
                '"verdict":"PASS","reason":"policy checked"}'
            ),
        )


def _write_workflow(repo: Path, *, two_steps: bool = False) -> None:
    write_text(repo / "agents" / "reporter.md", "# Reporter\n\nWrite the final result.\n")
    second = (
        (
            "  - id: second",
            "    type: agent",
            "    role: reporter",
            "    depends_on: [first]",
            "    outputs:",
            "      - artifacts/${run_id}/second.md",
            "  - id: delivery_gate",
            "    type: gate",
            "    terminal_delivery: true",
            "    depends_on: [second]",
            "    outputs:",
            "      - artifacts/${run_id}/delivery-review.json",
        )
        if two_steps
        else ()
    )
    write_text(
        repo / "workflows" / "policy.workflow.yaml",
        lines(
            "id: policy",
            "name: Policy",
            "steps:",
            "  - id: first",
            "    type: agent",
            "    role: reporter",
            "    model: opus",
            "    outputs:",
            "      - artifacts/${run_id}/first.md",
            *second,
        ),
    )


def _runner(repo: Path, adapter: GoodAdapter | FailingAdapter | BlockingAdapter) -> WorkflowRunner:
    return WorkflowRunner(
        repo_root=repo,
        store=WorkflowStore(repo / ".aicmo" / "runs.sqlite3"),
        adapter=adapter,
        heartbeat_interval_seconds=0.05,
    )


def test_run_policy_blocks_silent_executor_change_and_allows_explicit_change(
    tmp_path: Path,
) -> None:
    _write_workflow(tmp_path)
    failed_adapter = FailingAdapter()
    failed_runner = _runner(tmp_path, failed_adapter)
    assert failed_runner.run("policy", "policy_change", {}).status == "failed"

    good_adapter = GoodAdapter()
    good_runner = _runner(tmp_path, good_adapter)
    with pytest.raises(RunConflictError, match="explicitly allow a policy change"):
        good_runner.resume("policy_change")
    assert good_adapter.calls == []

    result = good_runner.resume("policy_change", allow_policy_change=True)
    policy = json.loads(good_runner.store.get_execution_policy("policy_change") or "{}")
    assert result.status == "success"
    assert good_adapter.calls == ["first"]
    assert policy["models"] == {"first": "opus"}


def test_anthropic_model_and_limit_are_part_of_executor_and_reviewer_policy(
    tmp_path: Path,
) -> None:
    executor_root = tmp_path / "executor"
    _write_workflow(executor_root)
    messages = FailingMessages()
    first = WorkflowRunner(
        repo_root=executor_root,
        store=WorkflowStore(executor_root / ".aicmo" / "runs.sqlite3"),
        adapter=AnthropicAdapter("sonnet", 111, FakeClient(messages)),
    )
    assert first.run("policy", "anthropic_executor", {}).status == "failed"
    changed = WorkflowRunner(
        repo_root=executor_root,
        store=first.store,
        adapter=AnthropicAdapter("haiku", 222, FakeClient(messages)),
    )
    with pytest.raises(RunConflictError, match="policy changed"):
        changed.resume("anthropic_executor")
    policy = json.loads(first.store.get_execution_policy("anthropic_executor") or "{}")
    assert policy["executor"]["default_model"] == "claude-sonnet-4-6"
    assert policy["executor"]["max_tokens"] == "111"

    reviewer_root = tmp_path / "reviewer"
    _write_workflow(reviewer_root)
    first_review = WorkflowRunner(
        repo_root=reviewer_root,
        store=WorkflowStore(reviewer_root / ".aicmo" / "runs.sqlite3"),
        adapter=FailingAdapter(),
        review_adapter=AnthropicAdapter("sonnet", 111, FakeClient(messages)),
    )
    assert first_review.run("policy", "anthropic_reviewer", {}).status == "failed"
    changed_review = WorkflowRunner(
        repo_root=reviewer_root,
        store=first_review.store,
        adapter=FailingAdapter(),
        review_adapter=AnthropicAdapter("haiku", 222, FakeClient(messages)),
    )
    with pytest.raises(RunConflictError, match="policy changed"):
        changed_review.resume("anthropic_reviewer")


def test_run_id_is_an_idempotency_key_and_retry_attempts_are_bounded(tmp_path: Path) -> None:
    _write_workflow(tmp_path)
    good_adapter = GoodAdapter()
    good_runner = _runner(tmp_path / "idempotent", good_adapter)
    _write_workflow(tmp_path / "idempotent")

    assert good_runner.run("policy", "same_request", {}).status == "success"
    assert good_runner.run("policy", "same_request", {}).status == "success"
    assert good_adapter.calls == ["first"]

    retry_root = tmp_path / "retry"
    _write_workflow(retry_root)
    failing_adapter = FailingAdapter()
    failing_runner = _runner(retry_root, failing_adapter)
    assert failing_runner.run("policy", "retry_limit", {}).status == "failed"
    assert failing_runner.resume("retry_limit").status == "failed"
    assert failing_runner.resume("retry_limit").status == "failed"
    assert failing_runner.resume("retry_limit").status == "failed"
    assert failing_adapter.calls == 3
    with pytest.raises(StepTransitionError, match="attempt limit"):
        failing_runner.retry("retry_limit", "first")


def test_cancel_releases_live_lease_and_preserves_previous_success(tmp_path: Path) -> None:
    _write_workflow(tmp_path, two_steps=True)
    adapter = BlockingAdapter()
    runner = _runner(tmp_path, adapter)
    results: SimpleQueue[RunResult] = SimpleQueue()
    thread = Thread(target=lambda: results.put(runner.run("policy", "cancel_live", {})))
    thread.start()

    assert adapter.started.wait(timeout=10)
    runner.cancel("cancel_live")
    adapter.release.set()
    thread.join(timeout=10)

    assert not thread.is_alive()
    assert results.get().status == RunStatus.CANCELLED.value
    assert runner.store.get_step_status("cancel_live", "first") == StepStatus.SUCCESS
    assert runner.store.get_step_status("cancel_live", "second") == StepStatus.CANCELLED
    assert (tmp_path / "artifacts" / "cancel_live" / "first.md").exists()
    assert not (tmp_path / "artifacts" / "cancel_live" / "second.md").exists()
    assert not (tmp_path / "artifacts" / "cancel_live" / "delivery-review.json").exists()
    calls = list(adapter.calls)
    assert runner.resume("cancel_live").status == RunStatus.CANCELLED.value
    assert adapter.calls == calls


def test_cancel_loses_once_all_steps_and_delivery_manifest_are_complete(
    tmp_path: Path,
) -> None:
    _write_workflow(tmp_path, two_steps=True)
    entered_completion = Event()
    release_completion = Event()
    def pause_after_delivery(step: object, _outputs: tuple[str, ...]) -> None:
        if getattr(step, "terminal_delivery", False):
            entered_completion.set()
            assert release_completion.wait(timeout=10)

    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
        adapter=GoodAdapter(),
        review_adapter=PassReviewer(),
        phase_completed=pause_after_delivery,
    )
    results: SimpleQueue[RunResult] = SimpleQueue()
    thread = Thread(target=lambda: results.put(runner.run("policy", "delivery_race", {})))
    thread.start()

    assert entered_completion.wait(timeout=10)
    with pytest.raises(StepTransitionError, match="all steps finished"):
        runner.cancel("delivery_race")
    release_completion.set()
    thread.join(timeout=10)

    manifest = json.loads(
        (tmp_path / "artifacts" / "delivery_race" / "delivery-review.json").read_text("utf-8"),
    )
    assert results.get().status == RunStatus.SUCCESS.value
    assert runner.store.get_run("delivery_race")["status"] == RunStatus.SUCCESS.value
    assert manifest["deliverable"] is True
