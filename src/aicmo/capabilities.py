from __future__ import annotations

from pathlib import Path
from typing import NotRequired, TypedDict, cast

import yaml
from pydantic import TypeAdapter, ValidationError

from aicmo.errors import AicmoError

REGISTRY_PATH = Path("registry/capabilities.yaml")


class CapabilityAgent(TypedDict):
    name: str
    role: str
    model: str
    path: str


class CapabilityMapping(TypedDict):
    id: int
    triggers: list[str]
    playbook: str | None
    chain: NotRequired[list[str]]
    chain_note: NotRequired[str | None]
    agents: str
    model: str


class CapabilityGates(TypedDict):
    reviewer_required: bool
    exempt: list[str]
    verdicts: list[str]
    approval_gated: list[str]


class CapabilityRegistry(TypedDict):
    version: int
    description: str
    agents: list[CapabilityAgent]
    mappings: list[CapabilityMapping]
    modules: dict[str, str]
    unmapped_playbooks: dict[str, str]
    gates: CapabilityGates
    output_pattern: str
    engine_artifacts: str


_REGISTRY_ADAPTER = TypeAdapter(CapabilityRegistry)


def load_capabilities(repo_root: Path) -> CapabilityRegistry:
    """Load the machine-readable capability registry (registry/capabilities.yaml)."""
    path = repo_root / REGISTRY_PATH
    if not path.exists():
        msg = f"capability registry not found: {path}"
        raise AicmoError(msg)
    payload = cast("object", yaml.safe_load(path.read_text(encoding="utf-8")))
    try:
        return _REGISTRY_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        msg = f"capability registry is malformed: {path}: {exc.errors()[0]['msg']}"
        raise AicmoError(msg) from exc


def find_mapping(registry: CapabilityRegistry, query: str) -> list[CapabilityMapping]:
    """Match a natural-language query against mapping triggers (exact > substring)."""
    mappings = registry["mappings"]
    needle = query.strip().lower()
    exact = [m for m in mappings if any(t.lower() == needle for t in m.get("triggers", []))]
    if exact:
        return exact
    return [
        m
        for m in mappings
        if any(needle in t.lower() or t.lower() in needle for t in m.get("triggers", []))
    ]
