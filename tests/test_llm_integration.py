from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aicmo.adapters import AgentRequest, AgentResult, GenerationUsage
from aicmo.anthropic_adapter import AnthropicAdapter, resolve_model
from aicmo.cli import app
from aicmo.errors import AicmoError
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


@dataclass
class _FakeUsage:
    input_tokens: object = 120
    output_tokens: object = 35
    cache_creation_input_tokens: object = 10
    cache_read_input_tokens: object = 20


@dataclass
class CapturingAdapter:
    seen: list[AgentRequest] = field(default_factory=list)

    def generate(self, request: AgentRequest) -> AgentResult:
        self.seen.append(request)
        return AgentResult(text="a complete captured draft, long enough to clear the gate", ok=True)


@dataclass(frozen=True, slots=True)
class VerdictAdapter:
    verdict: str
    usage: GenerationUsage | None = None

    def generate(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(text=self.verdict, ok=True, usage=self.usage)


@dataclass(frozen=True, slots=True)
class UnavailableReviewAdapter:
    def generate(self, _request: AgentRequest) -> AgentResult:
        return AgentResult(text="", ok=False, detail="reviewer unavailable")


def make_request(model: str = "") -> AgentRequest:
    return AgentRequest(
        step_id="draft",
        run_id="r",
        workflow_id="w",
        role="copywriter",
        role_contract="ROLE_CONTRACT",
        prompt_source="PROMPT_SOURCE",
        inputs_json="{}",
        model=model,
    )


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
    type: str = "text"


@dataclass
class _FakeResponse:
    content: list[_FakeBlock]
    stop_reason: str | None = "end_turn"
    usage: object = None
    model: str = "claude-sonnet-4-6"


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


@dataclass
class _ResponseMessages:
    response: _FakeResponse

    def create(self, **_kwargs: object) -> _FakeResponse:
        return self.response


@dataclass
class _ResponseClient:
    messages: _ResponseMessages


@pytest.mark.parametrize(
    "stop",
    [
        "max_tokens",
        "model_context_window_exceeded",
        "tool_use",
        "pause_turn",
        "refusal",
        "stop_sequence",
        "unknown",
        None,
    ],
)
def test_incomplete_provider_response_cannot_be_a_deliverable(stop: str | None) -> None:
    response = _FakeResponse([_FakeBlock("Looks complete but was cut off.")], stop, _FakeUsage())
    adapter = AnthropicAdapter(client=_ResponseClient(_ResponseMessages(response)))
    result = adapter.generate(make_request())
    assert result.ok is False
    assert result.text == ""
    assert result.usage is not None
    assert result.usage.output_tokens == 35
    assert "stop_reason=" in result.detail


def test_provider_usage_keeps_unknown_separate_from_zero_and_skips_nontext() -> None:
    response = _FakeResponse(
        [_FakeBlock("not visible thinking", "thinking"), _FakeBlock("Visible copy")],
        usage=_FakeUsage(
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=-1,
            cache_read_input_tokens=True,
        ),
    )
    result = AnthropicAdapter(client=_ResponseClient(_ResponseMessages(response))).generate(
        make_request()
    )
    assert result.ok is True
    assert result.text == "Visible copy"
    assert result.usage is not None
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
    assert result.usage.cache_creation_input_tokens is None
    assert result.usage.cache_read_input_tokens is None


def test_empty_provider_response_preserves_reported_usage() -> None:
    response = _FakeResponse([], usage=_FakeUsage())
    result = AnthropicAdapter(client=_ResponseClient(_ResponseMessages(response))).generate(
        make_request()
    )
    assert result.ok is False
    assert result.usage is not None
    assert result.usage.output_tokens == 35


def test_truncated_generation_records_usage_but_writes_no_deliverable(tmp_path: Path) -> None:
    write_text(
        tmp_path / "workflows/usage.workflow.yaml",
        lines(
            "id: usage",
            "name: Usage",
            "steps:",
            "  - id: draft",
            "    type: agent",
            '    outputs: ["artifacts/${run_id}/draft.md"]',
        ),
    )
    response = _FakeResponse([_FakeBlock("Do not deliver this")], "max_tokens", _FakeUsage())
    runner = WorkflowRunner(
        tmp_path,
        WorkflowStore(tmp_path / "runs.sqlite3"),
        adapter=AnthropicAdapter(client=_ResponseClient(_ResponseMessages(response))),
    )
    assert runner.run("usage", "usage-case", {}).status == "failed"
    assert not (tmp_path / "artifacts/usage-case/draft.md").exists()
    with runner.store.connect() as connection:
        row = connection.execute(
            "select payload_json from events where event_type='agent.call_finished'",
        ).fetchone()
    payload = json.loads(row["payload_json"])
    assert payload["usage_status"] == "reported"
    assert payload["output_tokens"] == "35"
    assert payload["stop_reason"] == "max_tokens"
    assert payload["result"] == "error"
    assert payload["cost_status"] == "unavailable"
    shown = CliRunner().invoke(
        app,
        ["usage", "usage-case", "--repo", str(tmp_path), "--db", str(tmp_path / "runs.sqlite3")],
    )
    assert shown.exit_code == 0
    assert "35" in shown.output
    assert "invoice totals are unavailable" in " ".join(shown.output.split())


def test_observation_minimizes_custom_metadata_and_rejects_invalid_counts(tmp_path: Path) -> None:
    role = "Customer name Jane Doe"
    write_text(tmp_path / f"agents/{role}.md", "Write factual copy.")
    write_text(
        tmp_path / "workflows/metadata.workflow.yaml",
        lines(
            "id: metadata",
            "name: Metadata",
            "steps:",
            "  - id: draft",
            "    type: agent",
            f"    role: {role}",
            '    outputs: ["artifacts/${run_id}/draft.md"]',
        ),
    )
    usage = GenerationUsage(
        "Customer name: Jane Doe",
        "Customer name: Jane Doe",
        response_model="Customer name: Jane Doe",
        stop_reason="Customer name: Jane Doe",
        input_tokens=True,
        output_tokens=-1,
    )
    runner = WorkflowRunner(
        tmp_path,
        WorkflowStore(tmp_path / "runs.sqlite3"),
        adapter=VerdictAdapter("Factual copy for review.", usage),
    )
    runner.run("metadata", "metadata-case", {})
    with runner.store.connect() as connection:
        rows = connection.execute(
            "select payload_json from events where event_type like 'agent.call_%'"
        ).fetchall()
    assert len(rows) == 2
    assert "Jane Doe" not in str([row["payload_json"] for row in rows])
    payload = json.loads(rows[-1]["payload_json"])
    assert payload["usage_status"] == "unavailable"
    assert payload["input_tokens"] == payload["output_tokens"] == "unavailable"
    shown = CliRunner().invoke(
        app,
        ["usage", "metadata-case", "--repo", str(tmp_path), "--db", str(tmp_path / "runs.sqlite3")],
    )
    assert shown.exit_code == 0
    assert "Jane Doe" not in shown.output


def test_resolve_model_aliases() -> None:
    assert resolve_model("opus") == "claude-opus-4-8"
    assert resolve_model("sonnet") == "claude-sonnet-4-6"
    assert resolve_model("haiku") == "claude-haiku-4-5-20251001"
    assert resolve_model("fable") == "claude-fable-5"
    assert resolve_model("claude-opus-4-8") == "claude-opus-4-8"
    assert resolve_model("claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert resolve_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5-20251001"
    assert resolve_model("claude-fable-5") == "claude-fable-5"
    assert resolve_model("") == "claude-sonnet-4-6"
    assert resolve_model("   ") == "claude-sonnet-4-6"


def test_anthropic_adapter_client_construction_failure_returns_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode() -> None:
        message = "client construction exploded"
        raise RuntimeError(message)

    monkeypatch.setattr("aicmo.anthropic_adapter._make_client", explode)
    adapter = AnthropicAdapter()

    result = adapter.generate(make_request(model="sonnet"))

    assert result.ok is False
    assert result.detail.startswith("unavailable:")
    assert "client construction exploded" in result.detail


def test_anthropic_adapter_rejects_unknown_model_before_request() -> None:
    messages = _FakeMessages(text="SHOULD NOT BE REQUESTED")
    adapter = AnthropicAdapter(client=_FakeClient(messages=messages))

    with pytest.raises(AicmoError, match="unknown Anthropic model alias"):
        adapter.generate(make_request(model="claude-sonnet-4-6-typo"))

    assert messages.captured == {}


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
        review_adapter=VerdictAdapter(
            verdict=(
                '{"schema_version":"aicmo.reviewer-decision.v1",'
                '"verdict":"FAIL","reason":"machine-readable review"}'
            ),
        ),
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
        review_adapter=VerdictAdapter(
            verdict=(
                '{"schema_version":"aicmo.reviewer-decision.v1",'
                '"verdict":"PASS","reason":"machine-readable review"}'
            ),
        ),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_sempass",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "success"


def test_configured_reviewer_unavailable_fails_closed(repo_root: Path) -> None:
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
        review_adapter=UnavailableReviewAdapter(),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_review_down",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "failed"
    assert result.failed_step_id == "review"


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
