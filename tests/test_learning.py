from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.errors import WorkflowExecutionError
from aicmo.learning import feedback_report, learn_feedback, learning_context, parse_feedback
from aicmo.outcomes import import_outcomes, preview_outcomes
from aicmo.runner import WorkflowRunner
from aicmo.source_input import source_checked_date
from aicmo.store import WorkflowStore
from tests.conftest import write_text
from tests.test_delivery_manifest import PassReviewer
from tests.test_local_pack import PackAdapter

REPO = Path(__file__).resolve().parents[1]
INSIGHT = "안내 문안의 CTA는 한 문장으로 짧게 씁니다."


class LearningPackAdapter(PackAdapter):
    def generate(self, request: AgentRequest) -> AgentResult:
        result = super().generate(request)
        if any(INSIGHT in ref.content_excerpt for ref in request.artifact_refs):
            content = json.loads(result.text)
            content["news"][0]["cta"] = "안내를 확인해 주세요."
            return AgentResult(json.dumps(content, ensure_ascii=False))
        return result


@pytest.fixture
def runner(tmp_path: Path) -> WorkflowRunner:
    for folder in ("workflows", "playbooks", "agents", "prompts"):
        shutil.copytree(REPO / folder, tmp_path / folder)
    for name in ("config", "brand-guidelines", "pricing-rules", "copy-patterns"):
        write_text(
            tmp_path / f"clients/shop/{name}.md", "# 합성 가게\n차분하고 정확하게 안내합니다."
        )
    return WorkflowRunner(
        tmp_path,
        WorkflowStore(tmp_path / ".aicmo/runs.sqlite3"),
        LearningPackAdapter(),
        PassReviewer(),
    )


def make_pack(
    runner: WorkflowRunner, run_id: str = "source", *, edit: bool = True
) -> dict[str, str]:
    inputs = {
        "client": "shop",
        "brief_json": json.dumps(
            {"owner_minutes": 20, "facts": ["이번 주에도 평소 영업시간대로 운영합니다."]}
        ),
    }
    assert runner.run("local-store-pack", run_id, inputs).status == "waiting_approval"
    if edit:
        path = runner.repo_root / f"artifacts/{run_id}/local-pack.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["news"][0]["cta"] = "안내를 확인해 주세요."
        write_text(path, json.dumps(payload, ensure_ascii=False))
    runner.approve(run_id, "owner_gate", "owner", "합성 문안 확인", accept_edits=edit)
    assert runner.resume(run_id).status == "success"
    return inputs


def feedback_inputs(**changes: object) -> dict[str, str]:
    feedback = {
        "schema_version": "aicmo.pack-feedback.v1",
        "source_run_id": "source",
        "item": "news-1.txt",
        "observed_on": source_checked_date().isoformat(),
        "adoption": "used",
        "reason": "사장님은 짧은 안내를 선호해 CTA를 줄였습니다.",
        "insight": INSIGHT,
        **changes,
    }
    return {"client": "shop", "feedback_json": json.dumps(feedback, ensure_ascii=False)}


def approve_feedback(runner: WorkflowRunner, run_id: str = "feedback", **changes: object) -> None:
    assert (
        runner.run("local-pack-feedback", run_id, feedback_inputs(**changes)).status
        == "waiting_approval"
    )
    runner.approve(run_id, "owner_gate", "owner", "보고한 사실과 반영 제안 확인")
    assert runner.resume(run_id).status == "success"


def test_approved_edit_feedback_changes_next_generation_context(runner: WorkflowRunner) -> None:
    pack_inputs = make_pack(runner)
    inputs = feedback_inputs()
    report = json.loads(feedback_report(runner, inputs))
    assert report["edited"] is True
    assert report["original"] != report["approved"]
    assert "user_reported" in report["evidence_status"]
    assert json.loads(learning_context(runner, "shop"))["insights"] == []
    assert runner.run("local-pack-feedback", "feedback", inputs).status == "waiting_approval"
    with pytest.raises(WorkflowExecutionError):
        learn_feedback(runner, "feedback")
    runner.approve("feedback", "owner_gate", "owner", "합성 검증")
    assert runner.resume("feedback").status == "success"
    path = learn_feedback(runner, "feedback")
    before = path.read_bytes()
    assert learn_feedback(runner, "feedback").read_bytes() == before
    assert runner.run("local-store-pack", "next", pack_inputs).status == "waiting_approval"
    adapter = runner.adapter
    assert isinstance(adapter, PackAdapter)
    request = adapter.requests[-1]
    assert any(INSIGHT in ref.content_excerpt for ref in request.artifact_refs)
    produced = json.loads(
        (runner.repo_root / "artifacts/next/local-pack.json").read_text(encoding="utf-8")
    )
    assert produced["news"][0]["cta"] == "안내를 확인해 주세요."
    assert (
        json.loads(
            (runner.repo_root / "artifacts/next/learning-context.json").read_text(encoding="utf-8")
        )["insights"][0]["insight"]
        == INSIGHT
    )
    assert json.loads(learning_context(runner, "other"))["insights"] == []


def test_source_snapshot_and_approved_files_are_verified(runner: WorkflowRunner) -> None:
    make_pack(runner)
    with runner.store.connect() as connection:
        row = connection.execute(
            "select * from approval_snapshots where run_id='source' "
            "and source_path like '%local-pack.json'"
        ).fetchone()
    assert row is not None
    snapshot = runner.repo_root / str(row["snapshot_path"])
    before = snapshot.read_bytes()
    snapshot.write_bytes(b"tampered")
    with pytest.raises(WorkflowExecutionError, match="snapshot changed"):
        feedback_report(runner, feedback_inputs())
    snapshot.write_bytes(before)
    with runner.store.connect() as connection:
        connection.execute("delete from approval_snapshots where run_id='source'")
    with pytest.raises(WorkflowExecutionError, match="original is unavailable"):
        feedback_report(runner, feedback_inputs())


def test_unreviewed_or_modified_feedback_cannot_be_learned(runner: WorkflowRunner) -> None:
    make_pack(runner)
    approve_feedback(runner)
    path = runner.repo_root / "artifacts/feedback/feedback.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(WorkflowExecutionError):
        learn_feedback(runner, "feedback")
    assert not (runner.repo_root / "knowledge-base/shop/approved-feedback.md").exists()


def test_kb_tamper_and_failed_append_do_not_feed_generation(
    runner: WorkflowRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_pack(runner)
    approve_feedback(runner)
    with monkeypatch.context() as patch:
        patch.setattr(
            "aicmo.learning.append_record", Mock(side_effect=PermissionError("synthetic"))
        )
        with pytest.raises(PermissionError):
            learn_feedback(runner, "feedback")
    assert json.loads(learning_context(runner, "shop"))["insights"] == []
    path = learn_feedback(runner, "feedback")
    path.write_text(
        path.read_text(encoding="utf-8").replace(INSIGHT, "변조된 문장"), encoding="utf-8"
    )
    assert json.loads(learning_context(runner, "shop"))["insights"] == []
    with pytest.raises(WorkflowExecutionError, match="KB block differs"):
        learn_feedback(runner, "feedback")


def test_feedback_is_minimized_before_run_storage(runner: WorkflowRunner) -> None:
    make_pack(runner)
    inputs = feedback_inputs(
        reason="Customer name: Jane Doe\nBearer sk-test-private-secret-0123456789"
    )
    assert runner.run("local-pack-feedback", "safe", inputs).status == "waiting_approval"
    saved = runner.store.get_inputs("safe")["feedback_json"]
    assert "Jane Doe" not in saved
    assert "sk-test-private-secret-0123456789" not in saved
    for raw in ('{"insight":"a","insight":"b"}', '{"reason":"Customer name: Jane Doe"}'):
        with pytest.raises(WorkflowExecutionError):
            parse_feedback(raw)


def test_append_before_commit_failure_replays_without_duplicate(
    runner: WorkflowRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_pack(runner)
    approve_feedback(runner)
    with monkeypatch.context() as patch:
        patch.setattr(
            "aicmo.learning.record_block", Mock(side_effect=RuntimeError("synthetic crash"))
        )
        with pytest.raises(RuntimeError, match="synthetic crash"):
            learn_feedback(runner, "feedback")
    assert json.loads(learning_context(runner, "shop"))["insights"] == []
    approve_feedback(runner, "replayed")
    path = learn_feedback(runner, "replayed")
    assert path.read_text(encoding="utf-8").count("<!-- learned:") == 1
    assert len(json.loads(learning_context(runner, "shop"))["insights"]) == 1


def test_concurrent_learning_activates_one_record(runner: WorkflowRunner) -> None:
    make_pack(runner)
    approve_feedback(runner)
    script = (
        "from pathlib import Path; import sys; from aicmo.runner import WorkflowRunner; "
        "from aicmo.store import WorkflowStore; from aicmo.learning import learn_feedback; "
        "p=Path(sys.argv[1]); learn_feedback(WorkflowRunner(p, "
        "WorkflowStore(p/'.aicmo/runs.sqlite3')), 'feedback')"
    )
    with (
        subprocess.Popen(  # noqa: S603 — fixed synthetic script, no shell
            [sys.executable, "-c", script, str(runner.repo_root)], stderr=subprocess.PIPE
        ) as first,
        subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", script, str(runner.repo_root)], stderr=subprocess.PIPE
        ) as second,
    ):
        for process in (first, second):
            _, error = process.communicate(timeout=30)
            assert process.returncode == 0, error.decode() if error else ""
    with runner.store.connect() as connection:
        assert connection.execute("select count(*) from learned_feedback").fetchone()[0] == 1
    assert len(json.loads(learning_context(runner, "shop"))["insights"]) == 1


def test_repeated_evidence_uses_new_verified_run(runner: WorkflowRunner) -> None:
    make_pack(runner)
    approve_feedback(runner, "first")
    path = learn_feedback(runner, "first")
    before = path.read_bytes()
    approve_feedback(runner, "second")
    assert learn_feedback(runner, "second").read_bytes() == before
    write_text(runner.repo_root / "artifacts/first/feedback.json", "{}")
    context = json.loads(learning_context(runner, "shop"))
    assert context["insights"][0]["feedback_run_id"] == "second"
    with runner.store.connect() as connection:
        assert connection.execute("select count(*) from learned_feedback").fetchone()[0] == 1


def test_new_correction_supersedes_earlier_preference_for_same_item(runner: WorkflowRunner) -> None:
    make_pack(runner)
    approve_feedback(runner, "first")
    path = learn_feedback(runner, "first")
    original = path.read_bytes()
    revised = "이번 문안은 예약 안내를 포함한 두 문장으로 씁니다."
    approve_feedback(runner, "corrected", insight=revised)
    learn_feedback(runner, "corrected")
    learn_feedback(runner, "first")
    context = json.loads(learning_context(runner, "shop"))
    assert len(context["insights"]) == 1
    assert context["insights"][0]["insight"] == revised
    assert path.read_bytes().startswith(original)
    assert path.read_text(encoding="utf-8").count("<!-- learned:") == 2
    assert context["superseded_records"] == 1
    write_text(runner.repo_root / "artifacts/corrected/feedback.json", "{}")
    fallback = json.loads(learning_context(runner, "shop"))
    assert fallback["insights"][0]["insight"] == INSIGHT
    assert fallback["omitted_invalid_records"] == 1


@pytest.mark.parametrize(
    "mutation",
    ["source", "feedback_spec", "wrong_client", "missing_item", "kb_deleted", "legacy_queue"],
)
def test_learning_boundaries(runner: WorkflowRunner, mutation: str) -> None:
    make_pack(runner)
    if mutation == "wrong_client":
        with pytest.raises(WorkflowExecutionError, match="another client"):
            feedback_report(runner, {**feedback_inputs(), "client": "other"})
        return
    if mutation == "missing_item":
        with pytest.raises(WorkflowExecutionError, match="item is absent"):
            feedback_report(runner, feedback_inputs(item="reply-5.txt"))
        return
    if mutation == "legacy_queue":
        runner.store.record_kb_update("source", "drafts", "shop", "legacy", INSIGHT)
        write_text(runner.repo_root / "knowledge-base/shop/insights.md", INSIGHT)
        assert json.loads(learning_context(runner, "shop"))["insights"] == []
        return
    approve_feedback(runner)
    path = learn_feedback(runner, "feedback")
    if mutation == "source":
        write_text(runner.repo_root / "artifacts/source/local-pack.json", "{}")
    elif mutation == "feedback_spec":
        policy = runner.repo_root / "playbooks/07-operations/local-pack-feedback.md"
        write_text(policy, policy.read_text(encoding="utf-8") + "\n새 검토 기준\n")
    else:
        path.unlink()
    assert json.loads(learning_context(runner, "shop"))["insights"] == []


@pytest.mark.parametrize("verdict", [None, "WARN", "FAIL"])
def test_feedback_requires_semantic_pass(runner: WorkflowRunner, verdict: str | None) -> None:
    make_pack(runner)
    changed = replace(runner, review_adapter=PassReviewer(verdict) if verdict else None)
    assert (
        changed.run("local-pack-feedback", "blocked", feedback_inputs()).status
        == "waiting_approval"
    )
    changed.approve("blocked", "owner_gate", "owner", "합성 사실 확인")
    changed.resume("blocked")
    with pytest.raises(WorkflowExecutionError):
        learn_feedback(changed, "blocked")


def test_optional_weekly_report_is_reviewed_same_week_evidence(runner: WorkflowRunner) -> None:
    make_pack(runner)
    today = source_checked_date()
    week = (today - timedelta(days=today.weekday())).isoformat()
    csv = runner.repo_root / "outcomes.csv"
    write_text(
        csv,
        f"date,channel,posts,inquiries,reservations,coupon_redemptions\n{today},naver,1,0,0,0\n",
    )
    preview = preview_outcomes(runner.repo_root, runner.store, "shop", week, "naver", csv)
    import_outcomes(
        runner.repo_root, runner.store, "shop", week, "naver", csv, preview.confirmation_sha256
    )
    assert (
        runner.run("weekly-report", "week", {"client": "shop", "week_start": week}).status
        == "success"
    )
    report = json.loads(feedback_report(runner, feedback_inputs(weekly_report_run_id="week")))
    assert "| 게시 | 1 | 1/7" in report["outcomes"]["report"]
    assert "causal impact not verified" in report["evidence_status"]
    with pytest.raises(WorkflowExecutionError, match="observation precedes"):
        feedback_report(
            runner,
            feedback_inputs(
                weekly_report_run_id="week", observed_on=(today - timedelta(days=7)).isoformat()
            ),
        )
    approve_feedback(runner, weekly_report_run_id="week")
    learn_feedback(runner, "feedback")
    write_text(runner.repo_root / "artifacts/week/weekly-report.md", "Changed report")
    assert json.loads(learning_context(runner, "shop"))["insights"] == []


def test_observation_date_uses_source_creation_day_in_kst(runner: WorkflowRunner) -> None:
    make_pack(runner)
    today = source_checked_date()
    yesterday = today - timedelta(days=1)
    with runner.store.connect() as connection:
        connection.execute(
            "update runs set created_at=? where run_id='source'", (f"{yesterday} 18:00:00",)
        )
    assert feedback_report(runner, feedback_inputs(observed_on=today.isoformat()))
    with pytest.raises(WorkflowExecutionError, match="observation precedes"):
        feedback_report(runner, feedback_inputs(observed_on=yesterday.isoformat()))
