from __future__ import annotations

import re
import sys
from pathlib import Path

from aicmo.errors import WorkflowExecutionError

SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
UNRESOLVED_VARIABLE = re.compile(r"\$\{[^}]+\}")


def _resolved_path(path: Path) -> Path:
    resolved = path.resolve()
    text = str(resolved)
    # Windows may retain this namespace during a concurrent create/replace.
    if sys.platform == "win32" and text.startswith("\\\\?\\"):
        if text[4:8].upper() == "UNC\\":
            return Path("\\\\" + text[8:])
        if re.match(r"[A-Za-z]:\\", text[4:]):
            return Path(text[4:])
    return resolved


def parse_safe_id(kind: str, raw: str) -> str:
    if SAFE_ID_PATTERN.fullmatch(raw) is None:
        raise WorkflowExecutionError(kind, f"unsafe {kind}: {raw}")
    return raw


def native_io_path(path: Path) -> Path:
    """Apply Windows long-path syntax only after logical containment has been checked."""
    if sys.platform != "win32":
        return path
    absolute = str(path.absolute())
    if absolute.startswith("\\\\?\\"):
        return path
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def resolve_inside_repo(repo_root: Path, path_template: str, context: dict[str, str]) -> Path:
    value = path_template
    for key, replacement in context.items():
        value = value.replace("${" + key + "}", replacement)
    if UNRESOLVED_VARIABLE.search(value) is not None:
        step_id = "path"
        raise WorkflowExecutionError(step_id, f"unresolved variable in path: {value}")
    candidate_path = Path(value)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        step_id = "path"
        raise WorkflowExecutionError(step_id, f"path escapes repo root: {value}")
    candidate = _resolved_path(repo_root / candidate_path)
    root = _resolved_path(repo_root)
    if not candidate.is_relative_to(root):
        step_id = "path"
        raise WorkflowExecutionError(step_id, f"path escapes repo root: {value}")
    return candidate
