"""Guard the launch-pack linear chain and referential integrity of all workflow specs."""

from __future__ import annotations

from pathlib import Path

import pytest

from aicmo.models import StepType, WorkflowSpec
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
    "delivery_gate",
)


def test_launch_pack_spec_is_linear() -> None:
    spec = load_workflow_spec(REPO_ROOT, "launch-pack")
    assert spec.inputs == {"client": "required"}
    assert tuple(step.id for step in spec.execution_order()) == LAUNCH_PACK_ORDER


CONTENT_ENGINE_ORDER = (
    "load_context",
    "verify_source",
    "source_report",
    "posts_generate",
    "image_pack",
    "quality_gate",
    "owner_gate",
    "reflection",
    "kb_queue",
    "publish_pack",
    "delivery_gate",
)


def test_content_engine_spec_is_linear() -> None:
    spec = load_workflow_spec(REPO_ROOT, "content-engine")
    assert spec.inputs == {
        "client": "required",
        "source_url": "required",
        "source_text": "required",
        "source_checked_at": "required",
        "channels": "optional",
    }
    assert tuple(step.id for step in spec.execution_order()) == CONTENT_ENGINE_ORDER
    steps = {step.id: step for step in spec.steps}
    assert steps["owner_gate"].requires_approval


def test_launch_pack_owner_gate_requires_approval() -> None:
    spec = load_workflow_spec(REPO_ROOT, "launch-pack")
    steps = {step.id: step for step in spec.steps}
    assert steps["owner_gate"].requires_approval
    assert steps["quality_gate"].type is StepType.GATE
    assert not steps["quality_gate"].requires_approval


def _repo_specs() -> list[Path]:
    return [
        path for path in (REPO_ROOT / "workflows").iterdir() if path.name.endswith(SPEC_SUFFIXES)
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


_DELIVERY_PRODUCERS = {
    "approval-demo": ("report",),
    "blog-article": ("report", "draft"),
    "content-engine": ("publish_pack", "source_report", "posts_generate", "image_pack"),
    "daily-cmo-loop": ("daily_feed", "digest", "seo_scan", "community_scan", "channel_drafts"),
    "launch-pack": (
        "report",
        "launch_strategy",
        "channel_mix",
        "hooking_copy",
        "brand_kit",
        "homepage_copy",
        "homepage_html",
    ),
}

_HANDOFF_INPUTS = {
    "approval-demo": ("owner_gate",),
    "blog-article": ("draft", "review"),
    "content-engine": (
        "source_report",
        "posts_generate",
        "image_pack",
        "quality_gate",
        "owner_gate",
        "reflection",
        "kb_queue",
    ),
    "launch-pack": (
        "launch_strategy",
        "channel_mix",
        "hooking_copy",
        "brand_kit",
        "homepage_copy",
        "homepage_html",
        "quality_gate",
        "owner_gate",
        "kb_queue",
    ),
    "daily-cmo-loop": (
        "digest",
        "seo_scan",
        "community_scan",
        "channel_drafts",
        "quality_gate",
        "owner_gate",
        "kb_queue",
    ),
}


def test_all_repo_workflows_have_one_explicit_terminal_delivery_gate() -> None:
    specs = [parse_workflow_spec(path) for path in _repo_specs()]
    assert {spec.id for spec in specs} == set(_DELIVERY_PRODUCERS)
    for spec in specs:
        terminal = [step for step in spec.steps if step.terminal_delivery]
        assert len(terminal) == 1, spec.id
        gate = terminal[0]
        assert gate.type is StepType.GATE
        assert gate.depends_on == _DELIVERY_PRODUCERS[spec.id]
        assert gate == spec.execution_order()[-1]
        assert all(gate.id not in step.depends_on for step in spec.steps)
        handoff = next(step for step in spec.steps if step.id == gate.depends_on[0])
        assert handoff.depends_on == _HANDOFF_INPUTS[spec.id]


def test_terminal_delivery_marker_requires_an_automatic_gate() -> None:
    with pytest.raises(ValueError, match="terminal delivery step must be an automatic gate"):
        WorkflowSpec.model_validate(
            {
                "id": "invalid-delivery",
                "name": "Invalid Delivery",
                "steps": [
                    {
                        "id": "deliverable",
                        "type": "agent",
                        "terminal_delivery": True,
                    },
                ],
            },
        )

    with pytest.raises(ValueError, match="terminal delivery step must be an automatic gate"):
        WorkflowSpec.model_validate(
            {
                "id": "manual-delivery",
                "name": "Manual Delivery",
                "steps": [
                    {"id": "artifact", "type": "agent"},
                    {
                        "id": "delivery_gate",
                        "type": "gate",
                        "depends_on": ["artifact"],
                        "requires_approval": True,
                        "terminal_delivery": True,
                    },
                ],
            },
        )


def test_terminal_delivery_gate_requires_declared_producers() -> None:
    with pytest.raises(ValueError, match="terminal delivery gate requires artifact producers"):
        WorkflowSpec.model_validate(
            {
                "id": "missing-producers",
                "name": "Missing Producers",
                "steps": [
                    {
                        "id": "delivery_gate",
                        "type": "gate",
                        "terminal_delivery": True,
                    },
                ],
            },
        )


def test_terminal_delivery_gate_must_be_a_leaf() -> None:
    with pytest.raises(ValueError, match="terminal delivery gate must be a leaf"):
        WorkflowSpec.model_validate(
            {
                "id": "nonterminal-delivery",
                "name": "Nonterminal Delivery",
                "steps": [
                    {"id": "artifact", "type": "agent"},
                    {
                        "id": "delivery_gate",
                        "type": "gate",
                        "depends_on": ["artifact"],
                        "terminal_delivery": True,
                    },
                    {"id": "later", "type": "agent", "depends_on": ["delivery_gate"]},
                ],
            },
        )


def test_terminal_delivery_gate_must_be_unique_and_final() -> None:
    with pytest.raises(ValueError, match="final step"):
        WorkflowSpec.model_validate(
            {
                "id": "later-independent-step",
                "name": "Later Independent Step",
                "steps": [
                    {"id": "artifact", "type": "agent"},
                    {
                        "id": "delivery_gate",
                        "type": "gate",
                        "depends_on": ["artifact"],
                        "terminal_delivery": True,
                    },
                    {"id": "later", "type": "agent"},
                ],
            },
        )
    with pytest.raises(ValueError, match="only one terminal delivery gate"):
        WorkflowSpec.model_validate(
            {
                "id": "two-delivery-gates",
                "name": "Two Delivery Gates",
                "steps": [
                    {"id": "artifact", "type": "agent"},
                    {
                        "id": "first_delivery",
                        "type": "gate",
                        "depends_on": ["artifact"],
                        "terminal_delivery": True,
                    },
                    {
                        "id": "second_delivery",
                        "type": "gate",
                        "depends_on": ["artifact"],
                        "terminal_delivery": True,
                    },
                ],
            },
        )
