from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from aicmo.errors import WorkflowSpecError
from aicmo.models import WorkflowSpec
from aicmo.paths import parse_safe_id

SPEC_SUFFIXES = (".workflow.yaml", ".workflow.yml", ".workflow.json")


def load_workflow_spec(repo_root: Path, workflow_id: str) -> WorkflowSpec:
    safe_workflow = parse_safe_id("workflow_id", workflow_id).value
    workflows_dir = repo_root / "workflows"
    for suffix in SPEC_SUFFIXES:
        candidate = workflows_dir / f"{safe_workflow}{suffix}"
        if candidate.exists():
            spec = parse_workflow_spec(candidate)
            if spec.id != safe_workflow:
                raise WorkflowSpecError(candidate, "workflow id does not match file name")
            return spec
    missing_spec = workflows_dir / f"{safe_workflow}.workflow.yaml"
    raise WorkflowSpecError(missing_spec, "workflow spec not found")


def parse_workflow_spec(path: Path) -> WorkflowSpec:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
        spec = WorkflowSpec.model_validate(payload)
    except (OSError, json.JSONDecodeError, TypeError, ValidationError, yaml.YAMLError) as exc:
        raise WorkflowSpecError(path=path, reason=str(exc)) from exc
    return spec.model_copy(update={"source_path": path})
