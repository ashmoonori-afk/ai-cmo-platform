from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.models import WorkflowStep
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


class CapturingAdapter:
    def __init__(self, result_text: str = "complete generated output") -> None:
        self.result_text = result_text
        self.seen: list[AgentRequest] = []

    def generate(self, request: AgentRequest) -> AgentResult:
        self.seen.append(request)
        return AgentResult(text=f"{self.result_text}: {request.step_id}", ok=True)


def _write_dependency_chain(repo_root: Path) -> None:
    write_text(
        repo_root / "workflows" / "dependency-chain.workflow.yaml",
        lines(
            "id: dependency-chain",
            "name: Dependency Chain",
            "steps:",
            "  - id: producer",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/producer.md",
            "  - id: middle",
            "    type: agent",
            "    depends_on: [producer]",
            "    outputs:",
            "      - artifacts/${run_id}/middle.md",
            "  - id: final",
            "    type: agent",
            "    depends_on: [middle]",
            "    outputs:",
            "      - artifacts/${run_id}/final.md",
            "  - id: unrelated",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/unrelated.md",
        ),
    )


def _attempts(store: WorkflowStore, run_id: str) -> dict[str, int]:
    return {str(row["step_id"]): int(row["attempt"]) for row in store.list_steps(run_id)}


def test_agent_request_includes_ordered_bounded_artifact_refs(tmp_path: Path) -> None:
    # Given: two ordered producer dependencies, one with two outputs and binary/oversize data.
    write_text(
        tmp_path / "workflows" / "artifact-refs.workflow.yaml",
        lines(
            "id: artifact-refs",
            "name: Artifact Refs",
            "inputs:",
            "  topic: required",
            "steps:",
            "  - id: producer_a",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/a.md",
            "  - id: producer_b",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/b-first.md",
            "      - artifacts/${run_id}/b-second.md",
            "  - id: consumer",
            "    type: agent",
            "    depends_on: [producer_b, producer_a]",
            "    outputs:",
            "      - artifacts/${run_id}/consumer.md",
        ),
    )
    adapter = CapturingAdapter(result_text="x" * 20_000)

    def replace_first_b_output_with_binary(
        step: WorkflowStep,
        outputs: tuple[str, ...],
    ) -> None:
        if step.id == "producer_b":
            (tmp_path / outputs[0]).write_bytes(b"\xff\xfe" + b"b" * 20_000)

    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
        adapter=adapter,
        phase_completed=replace_first_b_output_with_binary,
    )

    # When: the public runner executes the dependent agent.
    result = runner.run(
        workflow_id="artifact-refs",
        run_id="run_artifact_refs",
        inputs={"topic": "preserve me"},
    )

    # Then: refs are deterministic and bounded without replacing normal inputs.
    assert result.status == "success"
    request = next(item for item in adapter.seen if item.step_id == "consumer")
    assert json.loads(request.inputs_json)["topic"] == "preserve me"
    assert [(ref.producer_step_id, ref.path) for ref in request.artifact_refs] == [
        ("producer_b", "artifacts/run_artifact_refs/b-first.md"),
        ("producer_b", "artifacts/run_artifact_refs/b-second.md"),
        ("producer_a", "artifacts/run_artifact_refs/a.md"),
    ]
    assert all(ref.version == "v1" for ref in request.artifact_refs)
    assert all(
        not Path(ref.path).is_absolute() and ".." not in Path(ref.path).parts
        for ref in request.artifact_refs
    )
    assert all(
        ref.sha256 == hashlib.sha256((tmp_path / ref.path).read_bytes()).hexdigest()
        for ref in request.artifact_refs
    )
    assert sum(
        len(ref.content_excerpt.encode("utf-8")) for ref in request.artifact_refs
    ) <= 16 * 1024
    assert request.artifact_refs[0].truncated is True
    assert "\ufffd" in request.artifact_refs[0].content_excerpt


def test_resume_reopens_transitive_dependents_when_producer_hash_changes(
    repo_root: Path,
) -> None:
    # Given: a successful three-agent chain and one unrelated successful agent.
    _write_dependency_chain(repo_root)
    adapter = CapturingAdapter()
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
        adapter=adapter,
    )
    assert runner.run(workflow_id="dependency-chain", run_id="run_stale", inputs={}).status == (
        "success"
    )
    adapter.seen.clear()
    producer = repo_root / "artifacts" / "run_stale" / "producer.md"
    producer.write_text("operator changed producer output\n", encoding="utf-8")

    # When: the public runner resumes from misleading SUCCESS rows.
    resumed = runner.resume("run_stale")

    # Then: the chain reruns once and the unrelated success does not.
    assert resumed.status == "success"
    assert _attempts(runner.store, "run_stale") == {
        "producer": 2,
        "middle": 2,
        "final": 2,
        "unrelated": 1,
    }
    assert [request.step_id for request in adapter.seen] == ["producer", "middle", "final"]
    middle_request = next(request for request in adapter.seen if request.step_id == "middle")
    assert middle_request.artifact_refs[0].producer_step_id == "producer"
    assert middle_request.artifact_refs[0].sha256 == hashlib.sha256(
        producer.read_bytes()
    ).hexdigest()


def test_resume_uses_refs_sent_to_agent_not_post_execution_files(tmp_path: Path) -> None:
    # Given: the producer changes after its ref is sent but before the consumer succeeds.
    write_text(
        tmp_path / "workflows" / "ref-race.workflow.yaml",
        lines(
            "id: ref-race",
            "name: Ref Race",
            "steps:",
            "  - id: producer",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/producer.md",
            "  - id: consumer",
            "    type: agent",
            "    depends_on: [producer]",
            "    outputs:",
            "      - artifacts/${run_id}/consumer.md",
        ),
    )
    store = WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3")
    producer = tmp_path / "artifacts" / "run_ref_race" / "producer.md"

    class MutatingAdapter(CapturingAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.changed_sha = ""

        def generate(self, request: AgentRequest) -> AgentResult:
            result = super().generate(request)
            if request.step_id == "consumer" and not self.changed_sha:
                producer.write_text("changed during consumer execution\n", encoding="utf-8")
                self.changed_sha = hashlib.sha256(producer.read_bytes()).hexdigest()
                store.record_output_hashes(
                    "run_ref_race",
                    "producer",
                    {"artifacts/run_ref_race/producer.md": self.changed_sha},
                )
            return result

    adapter = MutatingAdapter()
    runner = WorkflowRunner(repo_root=tmp_path, store=store, adapter=adapter)
    assert runner.run(workflow_id="ref-race", run_id="run_ref_race", inputs={}).status == (
        "success"
    )
    first_request = next(request for request in adapter.seen if request.step_id == "consumer")
    assert first_request.artifact_refs[0].sha256 != adapter.changed_sha
    adapter.seen.clear()

    # When: the run resumes with the changed producer hash already accepted.
    resumed = runner.resume("run_ref_race")

    # Then: the consumer reruns because its persisted digest matches what it actually saw.
    assert resumed.status == "success"
    assert [request.step_id for request in adapter.seen] == ["consumer"]
    assert _attempts(store, "run_ref_race") == {"producer": 1, "consumer": 2}


def test_resume_never_reads_unsafe_dependency_artifact_ref(repo_root: Path) -> None:
    # Given: a successful chain whose producer output row is tampered to traverse outside.
    _write_dependency_chain(repo_root)
    adapter = CapturingAdapter()
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
        adapter=adapter,
    )
    assert runner.run(
        workflow_id="dependency-chain",
        run_id="run_unsafe_ref",
        inputs={},
    ).status == "success"
    outside = repo_root.parent / f"{repo_root.name}-outside-secret.txt"
    outside.write_text("must never enter an agent request", encoding="utf-8")
    with runner.store.connect() as connection:
        connection.execute(
            "update steps set outputs_json = ? where run_id = ? and step_id = ?",
            (json.dumps([f"../{outside.name}"]), "run_unsafe_ref", "producer"),
        )
    adapter.seen.clear()

    # When: resume reconciles the malformed stored path.
    resumed = runner.resume("run_unsafe_ref")

    # Then: regeneration stays inside the repo and refs never expose the secret.
    assert resumed.status == "success"
    assert [request.step_id for request in adapter.seen] == ["producer", "middle", "final"]
    middle_request = next(request for request in adapter.seen if request.step_id == "middle")
    assert [ref.path for ref in middle_request.artifact_refs] == [
        "artifacts/run_unsafe_ref/producer.md",
    ]
    assert all(".." not in Path(ref.path).parts for ref in middle_request.artifact_refs)
    assert all(
        "must never enter an agent request" not in ref.content_excerpt
        for request in adapter.seen
        for ref in request.artifact_refs
    )
    assert outside.read_text(encoding="utf-8") == "must never enter an agent request"
