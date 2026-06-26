from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from aicmo.cli import app
from aicmo.errors import WorkflowExecutionError
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text


def test_run_requires_client_onboarding_before_workflow_start(tmp_path: Path) -> None:
    write_text(
        tmp_path / "workflows" / "needs-client.workflow.yaml",
        lines(
            "id: needs-client",
            "name: Needs Client",
            "inputs:",
            "  client: required",
            "steps:",
            "  - id: draft",
            "    type: agent",
            "    outputs:",
            "      - artifacts/${run_id}/draft.md",
        ),
    )
    runner = WorkflowRunner(
        repo_root=tmp_path,
        store=WorkflowStore(tmp_path / ".aicmo" / "runs.sqlite3"),
    )

    with pytest.raises(WorkflowExecutionError, match="client onboarding required"):
        runner.run(
            workflow_id="needs-client",
            run_id="run_missing_client",
            inputs={"client": "acme"},
        )


def test_cli_run_announces_phase_outputs_and_persists_feedback(repo_root: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "run",
            "blog-article",
            "--client",
            "sample-client-a",
            "--topic",
            "phase-proof",
            "--artifact-format",
            "markdown",
            "--feedback",
            "Useful output; keep source-backed bullets",
            "--phase-git",
            "dry-run",
            "--run-id",
            "ulw_phase_happy",
            "--repo",
            str(repo_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "phase load_context deliverables:" in result.output
    assert "artifacts/ulw_phase_happy/context.md" in result.output
    assert "phase-git dry-run:" in result.output
    feedback = repo_root / "knowledge-base" / "_engine-improvements" / "artifact-feedback.md"
    feedback_text = feedback.read_text(encoding="utf-8")
    assert "ulw_phase_happy" in feedback_text
    assert "Useful output; keep source-backed bullets" in feedback_text


def test_operating_agent_skill_and_design_prompting_docs_exist() -> None:
    research_skill = Path("skills/birkin/ultraresearch-swarm/SKILL.md")
    image_skill = Path("skills/birkin/codex-image-gen/SKILL.md")
    readme = Path("README.md")

    assert research_skill.exists()
    assert "$omo:ultraresearch" in research_skill.read_text(encoding="utf-8")
    image_text = image_skill.read_text(encoding="utf-8")
    assert "GPT-Image2-Skill" in image_text
    assert "evolink.ai/gpt-image-2-prompts" in image_text
    readme_text = readme.read_text(encoding="utf-8")
    assert "Agent Link Runbook" in readme_text
    assert "phase-git" in readme_text
