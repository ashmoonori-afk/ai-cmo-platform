from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Final, Literal, Protocol

_MAX_DETAIL = 500
ARTIFACT_REF_CONTENT_BUDGET: Final = 16 * 1024
ARTIFACT_REF_TRUNCATION_MARKER: Final = "\n[artifact excerpt truncated]"

# Stable sentinel that marks a deterministic offline-stub artifact. The reviewer gate
# recognizes it and returns WARN (offline placeholder) instead of scanning the echoed
# role/prompt boilerplate for incomplete markers.
OFFLINE_STUB_MARKER = "Local deterministic adapter completed."


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    producer_step_id: str
    path: str
    sha256: str
    content_excerpt: str
    truncated: bool
    version: Literal["v1"] = "v1"


@dataclass(frozen=True, slots=True)
class AgentRequest:
    step_id: str
    run_id: str
    workflow_id: str
    role: str
    role_contract: str
    prompt_source: str
    inputs_json: str
    model: str = ""
    artifact_refs: tuple[ArtifactRef, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentResult:
    text: str
    ok: bool = True
    detail: str = ""


class StepAdapter(Protocol):
    def generate(self, request: AgentRequest, /) -> AgentResult: ...


def compose_prompt(request: AgentRequest) -> str:
    sections = [
        f"# Agent task: {request.step_id}",
        f"- role: {request.role}",
        f"- workflow: {request.workflow_id}",
        f"- run_id: {request.run_id}",
        "## Role contract",
        request.role_contract,
        "## Playbook / prompt",
        request.prompt_source,
        "## Inputs",
        request.inputs_json,
    ]
    if request.artifact_refs:
        sections.extend(
            [
                "## Upstream artifacts",
                json.dumps(
                    [
                        {
                            "version": ref.version,
                            "producer_step_id": ref.producer_step_id,
                            "path": ref.path,
                            "sha256": ref.sha256,
                            "content_excerpt": ref.content_excerpt,
                            "truncated": ref.truncated,
                        }
                        for ref in request.artifact_refs
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
            ],
        )
    sections.extend(
        [
            "## Instruction",
            "Produce the deliverable described by the role contract and playbook above, "
            "using the inputs. Return only the finished artifact content.",
        ],
    )
    return "\n\n".join(sections)


@dataclass(frozen=True, slots=True)
class LocalAdapter:
    """Deterministic offline adapter. The default executor; writes no live model output."""

    def generate(self, request: AgentRequest) -> AgentResult:
        body = "\n\n".join(
            [
                f"# Agent Step: {request.step_id}",
                f"- role: {request.role}",
                f"- workflow: {request.workflow_id}",
                f"- run_id: {request.run_id}",
                "## Inputs",
                request.inputs_json,
                "## Role Contract",
                request.role_contract,
                "## Prompt Source",
                request.prompt_source,
                "## Adapter Result",
                f"{OFFLINE_STUB_MARKER} Configure --executor-cmd "
                "(e.g. claude, codex, ollama, or any script) for live agent execution.",
            ],
        )
        return AgentResult(text=body, ok=True)


@dataclass(frozen=True, slots=True)
class CommandAdapter:
    """Live adapter that pipes the composed prompt to an operator-configured command.

    The command receives the prompt on stdin and must print the finished artifact to
    stdout. Examples: ("claude", "-p"), ("codex", "exec"), ("ollama", "run", "llama3").
    """

    command: tuple[str, ...]
    timeout_seconds: float = 120.0

    def generate(self, request: AgentRequest) -> AgentResult:
        if not self.command:
            return AgentResult(text="", ok=False, detail="no executor command configured")
        prompt = compose_prompt(request)
        try:
            completed = subprocess.run(  # noqa: S603 — argv list, never shell; command is operator-configured
                list(self.command),
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_seconds,
                check=False,
            )
        except OSError as exc:
            return AgentResult(text="", ok=False, detail=f"executor could not start: {exc}")
        except subprocess.TimeoutExpired:
            return AgentResult(
                text="",
                ok=False,
                detail=f"executor timed out after {self.timeout_seconds:g}s",
            )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()[:_MAX_DETAIL]
            return AgentResult(
                text="",
                ok=False,
                detail=f"executor exited {completed.returncode}: {stderr}",
            )
        output = (completed.stdout or "").strip()
        if not output:
            return AgentResult(text="", ok=False, detail="executor produced no output")
        return AgentResult(text=output, ok=True)
