from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from aicmo.adapters import (
    AgentRequest,
    AgentResult,
    CommandAdapter,
    LocalAdapter,
    compose_prompt,
)
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore


def make_request(**overrides: str) -> AgentRequest:
    base = {
        "step_id": "draft",
        "run_id": "run_x",
        "workflow_id": "blog-article",
        "role": "copywriter",
        "role_contract": "ROLE_CONTRACT_MARKER",
        "prompt_source": "PROMPT_SOURCE_MARKER",
        "inputs_json": '{"client": "acme"}',
    }
    base.update(overrides)
    return AgentRequest(**base)


@dataclass(frozen=True, slots=True)
class SentinelAdapter:
    text: str

    def generate(self, request: AgentRequest) -> AgentResult:
        return AgentResult(text=f"{self.text}::{request.step_id}", ok=True)


def test_local_adapter_returns_deterministic_body() -> None:
    result = LocalAdapter().generate(make_request())

    assert result.ok is True
    assert "ROLE_CONTRACT_MARKER" in result.text
    assert "PROMPT_SOURCE_MARKER" in result.text
    assert "run_x" in result.text


def test_compose_prompt_includes_role_and_prompt_and_inputs() -> None:
    prompt = compose_prompt(make_request())

    assert "ROLE_CONTRACT_MARKER" in prompt
    assert "PROMPT_SOURCE_MARKER" in prompt
    assert '"client": "acme"' in prompt


def test_command_adapter_captures_real_stdout() -> None:
    script = "import sys; sys.stdout.write('GEN::' + sys.stdin.read())"
    adapter = CommandAdapter(command=(sys.executable, "-c", script))

    result = adapter.generate(make_request())

    assert result.ok is True
    assert result.text.startswith("GEN::")
    assert "ROLE_CONTRACT_MARKER" in result.text


def test_command_adapter_nonzero_exit_is_failure() -> None:
    adapter = CommandAdapter(command=(sys.executable, "-c", "import sys; sys.exit(3)"))

    result = adapter.generate(make_request())

    assert result.ok is False
    assert "3" in result.detail


def test_command_adapter_missing_command_is_failure() -> None:
    adapter = CommandAdapter(command=("definitely-not-a-real-binary-xyz",))

    result = adapter.generate(make_request())

    assert result.ok is False
    assert result.detail


def test_command_adapter_empty_output_is_failure() -> None:
    adapter = CommandAdapter(command=(sys.executable, "-c", "pass"))

    result = adapter.generate(make_request())

    assert result.ok is False


def test_executor_uses_injected_adapter(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db_path),
        adapter=SentinelAdapter(text="SENTINEL_OUTPUT"),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_inject",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "success"
    draft = (repo_root / "artifacts" / "run_inject" / "draft.md").read_text("utf-8")
    assert "SENTINEL_OUTPUT" in draft


def test_runner_with_command_adapter_writes_real_command_output(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    script = "import sys; sys.stdout.write('CMD_GENERATED::' + str(len(sys.stdin.read())))"
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db_path),
        adapter=CommandAdapter(command=(sys.executable, "-c", script)),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_cmd",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "success"
    draft = (repo_root / "artifacts" / "run_cmd" / "draft.md").read_text("utf-8")
    assert "CMD_GENERATED::" in draft
    assert "Local deterministic adapter" not in draft


def test_command_adapter_failure_fails_the_run(repo_root: Path) -> None:
    db_path = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(db_path),
        adapter=CommandAdapter(command=(sys.executable, "-c", "import sys; sys.exit(2)")),
    )

    result = runner.run(
        workflow_id="blog-article",
        run_id="run_cmd_fail",
        inputs={"client": "sample-client-a", "topic": "x"},
    )

    assert result.status == "failed"
    assert result.failed_step_id == "keyword_research"
