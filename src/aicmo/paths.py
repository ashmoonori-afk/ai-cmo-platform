from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from aicmo.errors import WorkflowExecutionError

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True, slots=True)
class SafeId:
    value: str


def parse_safe_id(kind: str, raw: str) -> SafeId:
    if SAFE_ID_PATTERN.fullmatch(raw) is None:
        raise WorkflowExecutionError(kind, f"unsafe {kind}: {raw}")
    return SafeId(raw)


def resolve_inside_repo(repo_root: Path, path_template: str, context: dict[str, str]) -> Path:
    value = path_template
    for key, replacement in context.items():
        value = value.replace("${" + key + "}", replacement)
    candidate_path = Path(value)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        step_id = "path"
        raise WorkflowExecutionError(step_id, f"path escapes repo root: {value}")
    candidate = (repo_root / candidate_path).resolve()
    root = repo_root.resolve()
    if not candidate.is_relative_to(root):
        step_id = "path"
        raise WorkflowExecutionError(step_id, f"path escapes repo root: {value}")
    return candidate
