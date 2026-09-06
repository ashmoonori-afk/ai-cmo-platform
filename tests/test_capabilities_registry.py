from __future__ import annotations

import re
from pathlib import Path

import pytest

from aicmo.capabilities import CapabilityRegistry, find_mapping, load_capabilities
from aicmo.errors import AicmoError
from aicmo.spec import parse_workflow_spec

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def registry() -> CapabilityRegistry:
    return load_capabilities(REPO)


def _disk_playbooks() -> set[str]:
    return {p.relative_to(REPO).as_posix() for p in (REPO / "playbooks").rglob("*.md")}


def _mapped_paths(registry: CapabilityRegistry) -> set[str]:
    paths: set[str] = set()
    for m in registry["mappings"]:
        if playbook := m.get("playbook"):
            paths.add(playbook)
        paths.update(m.get("chain", []))
    return paths


def test_registry_has_agents_and_mappings(registry: CapabilityRegistry) -> None:
    assert len(registry["agents"]) == 13
    assert len(registry["mappings"]) == 75


def test_every_registry_agent_file_exists_with_matching_frontmatter(
    registry: CapabilityRegistry,
) -> None:
    for agent in registry["agents"]:
        path = REPO / agent["path"]
        assert path.exists(), agent["path"]
        frontmatter = path.read_text(encoding="utf-8").split("---")[1]
        assert f"name: {agent['name']}" in frontmatter
        assert f"model: {agent['model']}" in frontmatter


def test_every_agent_file_on_disk_is_registered(registry: CapabilityRegistry) -> None:
    registered = {a["path"] for a in registry["agents"]}
    on_disk = {p.relative_to(REPO).as_posix() for p in (REPO / "agents").glob("*.md")}
    assert on_disk == registered


def test_mapping_ids_are_unique_and_sequential(registry: CapabilityRegistry) -> None:
    ids = [m["id"] for m in registry["mappings"]]
    assert ids == list(range(1, len(ids) + 1))


def test_every_mapping_path_exists(registry: CapabilityRegistry) -> None:
    for path in _mapped_paths(registry):
        assert (REPO / path).exists(), path


def test_every_playbook_on_disk_is_mapped_or_documented(registry: CapabilityRegistry) -> None:
    mapped = _mapped_paths(registry)
    unmapped = registry.get("unmapped_playbooks", {})
    for playbook in _disk_playbooks():
        if playbook in mapped:
            continue
        documented = any(
            playbook == key or (key.endswith("/") and playbook.startswith(key)) for key in unmapped
        )
        assert documented, f"{playbook} is neither mapped nor documented in unmapped_playbooks"


def test_modules_cover_every_playbook_directory(registry: CapabilityRegistry) -> None:
    dirs = {p.split("/")[1] for p in _disk_playbooks()}
    assert dirs <= set(registry["modules"])


def test_workflow_roles_resolve_to_registry_agents(registry: CapabilityRegistry) -> None:
    agents = {a["name"] for a in registry["agents"]}
    for spec_path in (REPO / "workflows").glob("*.workflow.yaml"):
        spec = parse_workflow_spec(spec_path)
        for step in spec.steps:
            if step.role:
                assert step.role in agents, f"{spec_path.name}:{step.id} role {step.role}"


def test_docs_point_at_registry() -> None:
    agents_md = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    claude_md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    assert "registry/capabilities.yaml" in agents_md
    assert "registry/capabilities.yaml" in claude_md
    assert "AGENTS.md" in claude_md


def test_agents_md_counts_match_registry(registry: CapabilityRegistry) -> None:
    agents_md = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    for agent in registry["agents"]:
        assert agent["name"] in agents_md


def test_find_mapping_exact_beats_substring(registry: CapabilityRegistry) -> None:
    matches = find_mapping(registry, "레딧")
    assert matches
    assert matches[0]["playbook"] == "playbooks/11-community/reddit-engagement.md"


def test_find_mapping_substring_fallback(registry: CapabilityRegistry) -> None:
    matches = find_mapping(registry, "데일리 루프 돌려줘")
    assert any(m.get("playbook") == "playbooks/00-chains/daily-cmo-loop.md" for m in matches)


def test_new_okara_gap_mappings_present(registry: CapabilityRegistry) -> None:
    expected = {
        "playbooks/11-community/reddit-engagement.md",
        "playbooks/11-community/hackernews-launch.md",
        "playbooks/05-seo/geo-visibility-monitor.md",
        "playbooks/05-seo/backlink-outreach.md",
        "playbooks/05-seo/technical-seo-fix.md",
        "playbooks/03-content/x-twitter-daily.md",
        "playbooks/03-content/linkedin-founder-voice.md",
        "playbooks/08-design/ugc-video-brief.md",
        "playbooks/04-sales/influencer-campaign.md",
        "playbooks/00-chains/daily-cmo-loop.md",
    }
    assert expected <= _mapped_paths(registry)


def test_registry_yaml_is_valid_and_versioned(registry: CapabilityRegistry) -> None:
    assert registry["version"] == 1
    assert registry["gates"]["reviewer_required"] is True
    assert re.match(r"outputs/\{client\}/\{module\}/", registry["output_pattern"])


def test_registry_rejects_malformed_yaml(tmp_path: Path) -> None:
    path = tmp_path / "registry" / "capabilities.yaml"
    path.parent.mkdir()
    path.write_text("agents: []\n", encoding="utf-8")

    with pytest.raises(AicmoError, match="malformed"):
        load_capabilities(tmp_path)
