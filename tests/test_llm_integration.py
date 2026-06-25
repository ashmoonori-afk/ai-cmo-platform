from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.anthropic_adapter import AnthropicAdapter, resolve_model
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text

if TYPE_CHECKING:
    import pytest


@dataclass
class CapturingAdapter:
    seen: list[AgentRequest] = field(default_factory=list)

    def generate(self, request: AgentRequest) -> AgentResult:
        self.seen.append(request)
        return AgentResult(text="a complete captured draft, long enough to clear the gate", ok=True)


@dataclass(frozen=True, slots=True)
class VerdictAdapter:
    verdict: str

    def generate(self, request: AgentRequest) -> AgentResult:  # noqa: ARG002
        return AgentResult(text=self.verdict, ok=True)


def make_request(**overrides: str) -> AgentRequest:
    base = {
        "step_id": "draft",
        "run_id": "r",
        "workflow_id": "w",
        "role": "copywriter",
        "role_contract": "ROLE_CONTRACT",
        "prompt_source": "PROMPT_SOURCE",
        "inputs_json": "{}",
        "model": "",
    }
    base.update(overrides)
    return AgentRequest(**base)


# ---- G001: per-step model selection ----


def test_step_model_threads_to_adapter(tmp_path: Path) -> None:
    write_text(
        tmp_path / "workflows" / "model-thread.workflow.yaml",
        lines(
            "id: model-thread",
            "name: Model Thread",
            "steps:",
            "  - id: gen",
            "    type: agent",
            "    model: opus",
            "    outputs:",
            "      - artifacts/${run_id}/gen.md",
        ),
    )
    adapter = CapturingAdapter()
    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
        adapter=adapter,
    )

    result = runner.run(workflow_id="model-thread", run_id="run_model", inputs={})

    assert result.status == "success"
    assert adapter.seen[0].model == "opus"


# ---- G002: AnthropicAdapter ----


@dataclass
class _FakeBlock:
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeBlock]


@dataclass
class _FakeMessages:
    text: str
    captured: dict[str, object] = field(default_factory=dict)

    def create(self, **kwargs: object) -> _FakeResponse:
        self.captured = kwargs
        return _FakeResponse(content=[_FakeBlock(self.text)])


@dataclass
class _FakeClient:
    messages: _FakeMessages


def test_resolve_model_aliases() -> None:
    assert resolve_model("opus") == "claude-opus-4-8"
    assert resolve_model("haiku") == "claude-haiku-4-5-20251001"
    assert resolve_model("claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert resolve_model("") == "claude-sonnet-4-6"


def test_anthropic_adapter_with_fake_client() -> None:
    messages = _FakeMessages(text="GENERATED COPY")
    adapter = AnthropicAdapter(client=_FakeClient(messages=messages))

    result = adapter.generate(make_request(model="opus"))

    assert result.ok is True
    assert result.text == "GENERATED COPY"
    assert messages.captured["model"] == "claude-opus-4-8"
    sent = str(messages.captured["messages"])
    assert "ROLE_CONTRACT" in sent
    assert "PROMPT_SOURCE" in sent


def test_anthropic_adapter_unavailable_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = AnthropicAdapter()

    result = adapter.generate(make_request())

    assert result.ok is False
    assert "unavailable" in result.detail.lower()


# ---- G003: semantic reviewer behind the gate ----


def test_semantic_review_fail_fails_the_run(repo_root: Path) -> None:
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
        review_adapter=VerdictAdapter(verdict="FAIL: the draft is too thin"),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_semfail",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "failed"
    assert result.failed_step_id == "review"


def test_semantic_review_pass_passes_the_run(repo_root: Path) -> None:
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
        review_adapter=VerdictAdapter(verdict="PASS — clear and complete"),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_sempass",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "success"


def test_no_review_adapter_is_deterministic(repo_root: Path) -> None:
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_nodet",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "success"
