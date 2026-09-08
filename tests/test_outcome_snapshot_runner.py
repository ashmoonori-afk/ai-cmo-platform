from __future__ import annotations

import hashlib
import json
import shutil
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from aicmo.errors import WorkflowExecutionError
from aicmo.export import verified_delivery
from aicmo.learning import learn_feedback, learning_context
from aicmo.outcomes import (
    DailyOutcome,
    OutcomeImportSource,
    daily_outcome_csv,
    import_outcomes_bytes,
    parse_outcomes_snapshot,
    preview_outcomes_bytes,
    read_weekly_outcomes,
)
from aicmo.runner import WorkflowRunner
from aicmo.source_input import prepare_workflow_inputs, source_checked_date
from aicmo.spec import load_workflow_spec, run_spec_digest
from tests.test_learning import approve_feedback, make_pack
from tests.test_local_pack import _runner  # pyright: ignore[reportPrivateUsage]

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT_INPUT = "outcomes_snapshot_json"


@pytest.fixture
def runner(tmp_path: Path) -> WorkflowRunner:
    result = _runner(tmp_path)
    for relative in (
        "workflows/weekly-report.workflow.yaml",
        "workflows/local-pack-feedback.workflow.yaml",
        "playbooks/06-analytics/weekly-report.md",
        "playbooks/07-operations/local-pack-feedback.md",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    return result


def seed(runner: WorkflowRunner, posts: int) -> str:
    today = source_checked_date()
    week = (today - timedelta(days=today.weekday())).isoformat()
    raw = daily_outcome_csv(DailyOutcome(date=today.isoformat(), channel="naver", posts=posts))
    preview = preview_outcomes_bytes(runner.repo_root, runner.store, "shop", week, "naver", raw)
    import_outcomes_bytes(
        runner.repo_root,
        runner.store,
        "shop",
        week,
        "naver",
        raw,
        preview.confirmation_sha256,
        replace=True,
        provenance=OutcomeImportSource(kind="web_manual", recorded_by="web-user:1"),
    )
    return week


def test_old_report_learning_and_failed_resume_survive_optional_snapshot(
    runner: WorkflowRunner,
) -> None:
    path = runner.repo_root / "workflows/weekly-report.workflow.yaml"
    upgraded = path.read_text("utf-8")
    assert f"  {SNAPSHOT_INPUT}: optional\n" in upgraded
    path.write_text(upgraded.replace(f"  {SNAPSHOT_INPUT}: optional\n", ""), encoding="utf-8")
    make_pack(runner)
    week = seed(runner, 1)
    inputs = {"client": "shop", "week_start": week}
    assert runner.run("weekly-report", "legacy-report", inputs).status == "success"
    _, before_files = verified_delivery(runner, "legacy-report", "weekly-report")
    approve_feedback(runner, weekly_report_run_id="legacy-report")
    learned = learn_feedback(runner, "feedback")
    before_learning = learned.read_bytes()
    with patch(
        "aicmo.step_executor.weekly_outcomes_report",
        side_effect=WorkflowExecutionError("report", "synthetic interruption before metrics"),
    ):
        assert runner.run("weekly-report", "legacy-resume", inputs).status == "failed"
    path.write_text(upgraded, encoding="utf-8")
    assert verified_delivery(runner, "legacy-report", "weekly-report")[1] == before_files
    assert learn_feedback(runner, "feedback").read_bytes() == before_learning
    assert len(json.loads(learning_context(runner, "shop"))["insights"]) == 1
    seed(runner, 4)
    assert runner.resume("legacy-resume").status == "success"
    _, resumed = verified_delivery(runner, "legacy-resume", "weekly-report")
    assert "| 게시 | 4 | 1/7" in resumed["artifacts/legacy-resume/weekly-report.md"].decode()
    assert verified_delivery(runner, "legacy-report", "weekly-report")[1] == before_files


def test_new_report_uses_frozen_snapshot_after_ledger_correction(runner: WorkflowRunner) -> None:
    week = seed(runner, 2)
    snapshot = read_weekly_outcomes(runner.repo_root, runner.store, "shop", week, "naver")
    source = snapshot.model_dump_json()
    seed(runner, 8)
    inputs = {"client": "shop", "week_start": week, SNAPSHOT_INPUT: source}
    assert runner.run("weekly-report", "frozen-report", inputs).status == "success"
    assert runner.store.get_inputs("frozen-report")[SNAPSHOT_INPUT] == source
    _, files = verified_delivery(runner, "frozen-report", "weekly-report")
    report = files["artifacts/frozen-report/weekly-report.md"]
    assert "| 게시 | 2 | 1/7" in report.decode()
    assert snapshot.snapshot_sha256 in report.decode()
    assert (
        read_weekly_outcomes(runner.repo_root, runner.store, "shop", week, "naver")
        .totals["posts"]
        .current
        == 8
    )
    assert runner.resume("frozen-report").status == "success"
    assert verified_delivery(runner, "frozen-report", "weekly-report")[1] == files
    changed = read_weekly_outcomes(runner.repo_root, runner.store, "shop", week, "naver")
    with runner.store.connect() as connection:
        connection.execute(
            "update runs set inputs_json=? where run_id=?",
            (json.dumps({**inputs, SNAPSHOT_INPUT: changed.model_dump_json()}), "frozen-report"),
        )
    with pytest.raises(WorkflowExecutionError, match="specification or privacy"):
        verified_delivery(runner, "frozen-report", "weekly-report")


def test_legacy_digest_exception_is_only_one_absent_optional_declaration(
    runner: WorkflowRunner,
) -> None:
    week = seed(runner, 1)
    spec = load_workflow_spec(runner.repo_root, "weekly-report")
    inputs = {"client": "shop", "week_start": week}
    old = spec.model_copy(
        update={"inputs": {k: v for k, v in spec.inputs.items() if k != SNAPSHOT_INPUT}}
    )
    digest = run_spec_digest(old, inputs)
    assert run_spec_digest(spec, inputs) == digest
    required = spec.model_copy(update={"inputs": {**spec.inputs, SNAPSHOT_INPUT: "required"}})
    other = spec.model_copy(update={"inputs": {**spec.inputs, "another_input": "optional"}})
    assert run_spec_digest(required, inputs) != digest
    assert run_spec_digest(other, inputs) != digest
    assert run_spec_digest(spec.model_copy(update={"name": "Changed report"}), inputs) != digest
    assert run_spec_digest(spec, {**inputs, SNAPSHOT_INPUT: ""}) != digest
    prompt = runner.repo_root / "playbooks/06-analytics/weekly-report.md"
    prompt.write_text(
        prompt.read_text("utf-8") + "\nChanged synthetic instruction.\n", encoding="utf-8"
    )
    assert run_spec_digest(spec, inputs) != digest


@pytest.mark.parametrize("raw", ["", "null", "[]", "{}", "[" * 1100 + "]" * 1100])
def test_present_invalid_snapshot_never_falls_back_to_live_ledger(
    runner: WorkflowRunner, raw: str
) -> None:
    week = seed(runner, 3)
    before = hashlib.sha256(runner.store.db_path.read_bytes()).hexdigest()
    with pytest.raises(WorkflowExecutionError, match="outcome snapshot"):
        runner.run(
            "weekly-report",
            "bad-snapshot",
            {"client": "shop", "week_start": week, SNAPSHOT_INPUT: raw},
        )
    assert hashlib.sha256(runner.store.db_path.read_bytes()).hexdigest() == before


def test_snapshot_parser_rejects_duplicate_keys_and_preserves_structured_hashes(
    runner: WorkflowRunner,
) -> None:
    week = seed(runner, 1)
    snapshot = read_weekly_outcomes(runner.repo_root, runner.store, "shop", week, "naver")
    raw = snapshot.model_dump_json()
    phone_shaped = "01012345678" + "a" * 53
    raw = raw.replace(snapshot.current[0].source_sha256, phone_shaped)
    spec = load_workflow_spec(runner.repo_root, "weekly-report")
    assert (
        prepare_workflow_inputs(
            spec.inputs, {"client": "shop", "week_start": week, SNAPSHOT_INPUT: raw}
        ).values[SNAPSHOT_INPUT]
        == raw
    )
    assert parse_outcomes_snapshot(raw).current[0].source_sha256 == phone_shaped
    for duplicate in (
        raw.replace('"client":"shop"', '"client":"other","client":"shop"'),
        raw.replace('"posts":1', '"posts":2,"posts":1'),
    ):
        assert duplicate != raw
        with pytest.raises(WorkflowExecutionError, match="invalid outcome snapshot"):
            parse_outcomes_snapshot(duplicate)
