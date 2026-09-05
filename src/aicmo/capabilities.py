from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from aicmo.errors import AicmoError

REGISTRY_PATH = Path("registry/capabilities.yaml")


def load_capabilities(repo_root: Path) -> dict[str, Any]:
    """Load the machine-readable capability registry (registry/capabilities.yaml)."""
    path = repo_root / REGISTRY_PATH
    if not path.exists():
        msg = f"capability registry not found: {path}"
        raise AicmoError(msg)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "agents" not in data or "mappings" not in data:
        msg = f"capability registry is malformed: {path} (expected agents + mappings keys)"
        raise AicmoError(msg)
    return data


def find_mapping(registry: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Match a natural-language query against mapping triggers (exact > substring)."""
    mappings: list[dict[str, Any]] = registry.get("mappings", [])
    needle = query.strip().lower()
    exact = [m for m in mappings if any(t.lower() == needle for t in m.get("triggers", []))]
    if exact:
        return exact
    return [
        m
        for m in mappings
        if any(needle in t.lower() or t.lower() in needle for t in m.get("triggers", []))
    ]
