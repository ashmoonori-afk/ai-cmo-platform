from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

import yaml
from pydantic import ValidationError

from aicmo.errors import WorkflowExecutionError, WorkflowSpecError
from aicmo.models import WorkflowSpec
from aicmo.paths import parse_safe_id, resolve_inside_repo

SPEC_SUFFIXES = (".workflow.yaml", ".workflow.yml")
RUN_SPEC_REVISION: Final = 1


def load_workflow_spec(repo_root: Path, workflow_id: str) -> WorkflowSpec:
    safe_workflow = parse_safe_id("workflow_id", workflow_id)
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
    try:
        text = path.read_text(encoding="utf-8")
        payload = yaml.safe_load(text)
        spec = WorkflowSpec.model_validate(payload)
    except (OSError, TypeError, UnicodeDecodeError, ValidationError, yaml.YAMLError) as exc:
        raise WorkflowSpecError(path=path, reason=str(exc)) from exc
    return spec.model_copy(update={"source_path": path})


def run_spec_digest(spec: WorkflowSpec, inputs: dict[str, str]) -> str:
    source_path = spec.source_path
    if source_path is None:
        raise WorkflowSpecError(Path("workflows") / spec.id, "workflow source path is unavailable")
    repo_root = source_path.parent.parent
    normalized_steps = tuple(
        step.model_copy(
            update={
                "paths": tuple(path.replace("\\", "/") for path in step.paths),
                "outputs": tuple(path.replace("\\", "/") for path in step.outputs),
                "role": None if step.role is None else step.role.replace("\\", "/"),
                "prompt": None if step.prompt is None else step.prompt.replace("\\", "/"),
            },
        )
        for step in spec.steps
    )
    normalized_spec = spec.model_copy(update={"steps": normalized_steps, "source_path": None})
    workflow_bytes = json.dumps(
        normalized_spec.model_dump(mode="json", exclude={"source_path"}),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    input_bytes = json.dumps(
        inputs,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    references: set[str] = set()
    for step in spec.steps:
        if step.role is not None:
            references.add(f"agents/{step.role}.md".replace("\\", "/"))
        if step.prompt is not None:
            references.add(step.prompt.replace("\\", "/"))

    digest = hashlib.sha256()
    parts = (b"aicmo-run-spec", RUN_SPEC_REVISION.to_bytes(4, "big"), workflow_bytes, input_bytes)
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    for reference in sorted(references):
        try:
            content = resolve_inside_repo(repo_root, reference, {}).read_bytes()
        except (OSError, WorkflowExecutionError) as exc:
            raise WorkflowSpecError(source_path, f"cannot fingerprint {reference}: {exc}") from exc
        for part in (reference.encode(), content):
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
    return digest.hexdigest()
