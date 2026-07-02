"""Guard the launch-pack linear chain and referential integrity of all workflow specs."""

from __future__ import annotations

from pathlib import Path

from aicmo.models import StepType
from aicmo.spec import SPEC_SUFFIXES, load_workflow_spec, parse_workflow_spec

REPO_ROOT = Path(__file__).resolve().parents[1]

LAUNCH_PACK_ORDER = (
    "load_context",
    "market_research",
    "competitor_scan",
    "launch_strategy",
    "channel_mix",
    "hooking_copy",
    "brand_kit",
    "homepage_copy",
    "homepage_html",
    "quality_gate",
    "owner_gate",
    "kb_queue",
    "report",
)


def test_launch_pack_spec_is_linear() -> None:
    spec = load_workflow_spec(REPO_ROOT, "launch-pack")
    assert spec.inputs == {"client": "required"}
    assert tuple(step.id for step in spec.execution_order()) == LAUNCH_PACK_ORDER


def test_launch_pack_owner_gate_requires_approval() -> None:
    spec = load_workflow_spec(REPO_ROOT, "launch-pack")
    steps = {step.id: step for step in spec.steps}
    assert steps["owner_gate"].requires_approval
    assert steps["quality_gate"].type is StepType.GATE
    assert not steps["quality_gate"].requires_approval


def _repo_specs() -> list[Path]:
    return [
        path
        for path in (REPO_ROOT / "workflows").iterdir()
        if path.name.endswith(SPEC_SUFFIXES)
    ]


def test_all_repo_workflow_specs_reference_existing_files() -> None:
    """Every role and prompt referenced by a checked-in spec must exist on disk."""
    specs = _repo_specs()
    assert specs, "no workflow specs found under workflows/"
    for spec_path in specs:
        spec = parse_workflow_spec(spec_path)
        for step in spec.steps:
            if step.role is not None:
                role_file = REPO_ROOT / "agents" / f"{step.role}.md"
                assert role_file.exists(), f"{spec_path.name}:{step.id} missing {role_file}"
            if step.prompt is not None:
                prompt_file = REPO_ROOT / step.prompt
                assert prompt_file.exists(), f"{spec_path.name}:{step.id} missing {prompt_file}"
