from __future__ import annotations

import json
from pathlib import Path

import pytest

from aicmo.errors import WorkflowExecutionError
from aicmo.export import export_local_pack
from aicmo.local_pack import parse_brief
from aicmo.pack_edits import digest, inspect_base, pack_text
from aicmo.pack_rewrite import RewriteRequest, facts_sha, parse_rewrite
from aicmo.source_input import prepare_workflow_inputs
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _content,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


def test_new_facts_reach_existing_generator_and_reviewer(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    source = "web-" + "a" * 32
    inputs = _brief()
    assert runner.run("local-store-pack", source, inputs).status == "waiting_approval"
    base, pack = inspect_base(runner, source)
    runner.cancel(source)
    brief = parse_brief(inputs)
    brief.facts[0] = "새 메뉴 가격은 5,000원이며 월요일부터 적용합니다(출처: 사장님 확인)."
    rewrite = RewriteRequest(
        schema_version="aicmo.pack-rewrite.v1",
        source_run_id=source,
        base=base,
        revision=0,
        edited_sha=digest(pack_text(pack)),
        source_body=pack_text(pack),
        action="price",
        confirmed_by="web-user:1",
        facts_sha=facts_sha(brief.facts),
    )
    new_inputs = {
        **inputs,
        "brief_json": brief.model_dump_json(),
        "rewrite_json": rewrite.model_dump_json(),
    }
    assert runner.run("local-store-pack", "new-facts", new_inputs).status == "waiting_approval"
    assert isinstance(runner.adapter, PackAdapter)
    request = runner.adapter.requests[-1]
    actual = json.loads(request.inputs_json)
    assert parse_rewrite(actual["rewrite_json"]) == rewrite
    assert "action=price" in request.prompt_source
    assert "brief_json.facts" in request.prompt_source
    assert "source_body" in request.prompt_source
    assert parse_brief(actual).facts == brief.facts
    runner.approve("new-facts", "owner_gate", "synthetic-owner", "확인한 새 사실")
    assert runner.resume("new-facts").status == "success"
    assert export_local_pack(runner, "new-facts").exists()
    assert runner.store.get_run(source)["status"] == "cancelled"

    # The boundary rejects a mismatched owner fact hash before any generation.
    invalid = {**new_inputs, "brief_json": inputs["brief_json"]}
    with pytest.raises(WorkflowExecutionError, match="confirmed facts"):
        parse_brief(invalid)
    friendly = rewrite.model_copy(update={"action": "friendly"}).model_dump_json()
    with pytest.raises(WorkflowExecutionError, match="confirmed facts"):
        parse_brief({**new_inputs, "rewrite_json": friendly})

    # Machine identities with phone-shaped digits survive preparation unchanged.
    identity = "a" * 10 + "01012345678" + "b" * 43
    encoded = rewrite.model_copy(
        update={"base": base.model_copy(update={"snapshot_sha": identity})}
    ).model_dump_json()
    assert prepare_workflow_inputs({}, {"rewrite_json": encoded}).values["rewrite_json"] == encoded
    unsafe = pack.model_copy(update={"summary": "연락처 customer@example.com"})
    body = pack_text(unsafe)
    encoded = rewrite.model_copy(
        update={"source_body": body, "edited_sha": digest(body)}
    ).model_dump_json()
    with pytest.raises(WorkflowExecutionError, match="owner-confirmed"):
        parse_rewrite(encoded)


@pytest.mark.parametrize("inner", [False, True])
def test_duplicate_rewrite_keys_cannot_hide_private_source(inner: bool) -> None:
    body = _content(_brief())
    if inner:
        body = body.replace('"summary":', '"summary":"token=abcdef123456", "summary":', 1)
    request = {
        "schema_version": "aicmo.pack-rewrite.v1",
        "source_run_id": "web-" + "a" * 32,
        "base": {
            "spec_digest": "a" * 64,
            "spec_revision": 1,
            "draft_attempt": 1,
            "draft_sha": "a" * 64,
            "snapshot_sha": "a" * 64,
            "photo_sha": "a" * 64,
            "dependencies_sha": "a" * 64,
        },
        "revision": 0,
        "edited_sha": digest(body),
        "source_body": body,
        "action": "shorten",
        "confirmed_by": "web-user:1",
        "facts_sha": facts_sha(parse_brief(_brief()).facts),
    }
    raw = json.dumps(request, ensure_ascii=False)
    if not inner:
        raw = '{"source_body":"token=abcdef123456",' + raw[1:]
    with pytest.raises(WorkflowExecutionError, match="owner-confirmed"):
        prepare_workflow_inputs({}, {"rewrite_json": raw})
