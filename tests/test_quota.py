from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from sqlite3 import Connection
from threading import Barrier
from typing import Never, cast

import pytest
from typer.testing import CliRunner

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.cli import app
from aicmo.errors import StepTransitionError
from aicmo.models import StepStatus
from aicmo.quota import QuotaError, configure_quota, credit_quota, current_period, quota_status
from aicmo.runner import WorkflowRunner
from aicmo.spec import load_workflow_spec
from tests.test_delivery_manifest import PassReviewer
from tests.test_local_pack import (
    PackAdapter,
    _brief,  # pyright: ignore[reportPrivateUsage]
    _runner,  # pyright: ignore[reportPrivateUsage]
)


def _state(runner: WorkflowRunner, run_id: str = "case") -> dict[str, str]:
    with runner.store.connect() as connection:
        return dict(
            connection.execute("select * from product_usage where run_id=?", (run_id,)).fetchone()
        )


def _configured(root: Path, *, packs: int = 1, drafts: int = 3) -> WorkflowRunner:
    runner = _runner(root)
    configure_quota(runner.store, "shop", current_period(), packs, drafts)
    return runner


def _finish(runner: WorkflowRunner, run_id: str = "case") -> None:
    runner.approve(run_id, "owner_gate", "synthetic-owner", "test")
    assert runner.resume(run_id).status == "success"


def test_reserve_consume_replay_credit_and_recovery(tmp_path: Path) -> None:
    runner = _configured(tmp_path)
    assert runner.run("local-store-pack", "case", _brief()).status == "waiting_approval"
    assert _state(runner)["state"] == "reserved"
    assert runner.resume("case").status == "waiting_approval"
    assert quota_status(runner.store, "shop", current_period())["draft_used"] == 1
    _finish(runner)
    assert _state(runner)["state"] == "consumed"
    assert len(_state(runner)["delivery_sha256"]) == 64
    assert runner.resume("case").status == "success"
    assert runner.run("local-store-pack", "blocked", _brief()).status == "failed"
    assert runner.store.get_run("blocked")["status"] == "failed"
    assert runner.store.get_step_attempt("blocked", "load_context") == 0
    assert credit_quota(runner.store, "case", "지원 정책에 따른 상품 단위 반환")
    assert not credit_quota(runner.store, "case", "동일 재시도")
    (tmp_path / "artifacts/case/local-pack.json").unlink()
    with pytest.raises(QuotaError, match="credited"):
        runner.resume("case")
    assert runner.store.get_step_status("case", "drafts") == StepStatus.SUCCESS
    assert runner.resume("blocked").status == "waiting_approval"


def test_failure_retry_cancel_and_draft_cap(tmp_path: Path) -> None:
    class Failing(PackAdapter):
        def generate(self, request: AgentRequest) -> AgentResult:
            self.requests.append(request)
            return AgentResult("", ok=False, detail="synthetic timeout")

    adapter = Failing()
    runner = replace(_configured(tmp_path, drafts=1), adapter=adapter)
    assert runner.run("local-store-pack", "case", _brief()).status == "failed"
    assert _state(runner)["state"] == "released"
    assert runner.store.get_step_attempt("case", "drafts") == 1
    assert runner.resume("case").status == "failed"
    assert runner.store.get_step_attempt("case", "drafts") == 1
    assert len(adapter.requests) == 1
    configure_quota(runner.store, "shop", current_period(), 1, 2)
    assert runner.resume("case").status == "failed"
    assert len(adapter.requests) == 2
    runner.cancel("case")
    assert _state(runner)["state"] == "released"
    assert quota_status(runner.store, "shop", current_period())["draft_used"] == 2


@pytest.mark.parametrize("reviewer", [None, PassReviewer(verdict="WARN")])
def test_non_deliverable_success_releases_product(
    tmp_path: Path, reviewer: PassReviewer | None
) -> None:
    runner = replace(_configured(tmp_path), review_adapter=reviewer)
    assert runner.run("local-store-pack", "case", _brief()).status == "waiting_approval"
    _finish(runner)
    assert _state(runner)["state"] == "released"
    assert _state(runner)["delivery_sha256"] is None


def test_terminal_retry_reacquires_before_review(tmp_path: Path) -> None:
    reviewer = PassReviewer(verdict="FAIL")
    runner = replace(_configured(tmp_path), review_adapter=reviewer)
    assert runner.run("local-store-pack", "case", _brief()).status == "waiting_approval"
    runner.approve("case", "owner_gate", "synthetic-owner", "test")
    assert runner.resume("case").status == "failed"
    assert _state(runner)["state"] == "released"
    other = replace(runner, runner_token="other")  # noqa: S106 — synthetic lease identity
    assert other.run("local-store-pack", "other", _brief()).status == "waiting_approval"
    attempts = runner.store.get_step_attempt("case", "delivery_gate")
    assert runner.resume("case").status == "failed"
    assert runner.store.get_step_attempt("case", "delivery_gate") == attempts
    other.cancel("other")
    runner = replace(runner, review_adapter=PassReviewer())
    assert runner.resume("case").status == "success"
    assert _state(runner)["state"] == "consumed"


def test_month_boundary_and_unmetered_policy_are_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("aicmo.quota.current_period", lambda: "2026-09")
    runner = _runner(tmp_path)
    assert runner.run("local-store-pack", "local", _brief()).status == "waiting_approval"
    configure_quota(runner.store, "shop", "2026-09", 2, 4)
    _finish(runner, "local")
    assert _state(runner, "local")["state"] == "unmetered"
    assert runner.run("local-store-pack", "case", _brief()).status == "waiting_approval"
    assert runner.run("local-store-pack", "released", _brief()).status == "waiting_approval"
    runner.reject("released", "owner_gate", "synthetic-owner", "declined")
    monkeypatch.setattr("aicmo.quota.current_period", lambda: "2026-10")
    _finish(runner)
    assert _state(runner)["period"] == "2026-09"
    assert runner.run("local-store-pack", "october", _brief()).status == "failed"
    configure_quota(runner.store, "shop", "2026-10", 1, 3)
    assert runner.resume("october").status == "waiting_approval"
    # A released September run cannot reserve October or reuse September capacity.
    assert runner.resume("released").status == "failed"
    assert _state(runner, "released")["state"] == "released"


def test_atomic_competition_and_stale_claim(tmp_path: Path) -> None:
    runner = _configured(tmp_path)
    spec = load_workflow_spec(tmp_path, "local-store-pack")
    step = next(step for step in spec.steps if step.id == "drafts")
    for run_id in ("first", "second"):
        runner.store.ensure_run(spec, run_id, _brief())
    barrier = Barrier(2)

    def claim(run_id: str) -> bool:
        barrier.wait()
        try:
            return runner.store.mark_step_running(run_id, step, run_id)
        except QuotaError:
            return False

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(claim, ("first", "second")))
    assert sum(results) == 1
    winner = ("first", "second")[results.index(True)]
    assert not runner.store.mark_step_running(winner, step, "loser")
    with runner.store.connect() as connection:
        connection.execute("update steps set locked_at='2000-01-01' where run_id=?", (winner,))
    assert runner.store.mark_step_running(winner, step, "recovered")
    assert quota_status(runner.store, "shop", current_period())["draft_used"] == 2
    assert _state(runner, winner)["state"] == "reserved"


def test_consumed_regeneration_is_not_refunded(tmp_path: Path) -> None:
    runner = _configured(tmp_path)
    assert runner.run("local-store-pack", "case", _brief()).status == "waiting_approval"
    _finish(runner)
    (tmp_path / "artifacts/case/local-pack.json").unlink()
    assert runner.resume("case").status == "waiting_approval"
    assert _state(runner)["state"] == "consumed"
    runner.cancel("case")
    assert _state(runner)["state"] == "consumed"
    with pytest.raises(QuotaError, match="successful"):
        credit_quota(runner.store, "case", "cannot credit an unfinished regeneration")


def test_quota_validation_and_atomic_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _configured(tmp_path)
    for month, packs, drafts in [("2026-9", 1, 3), (current_period(), True, 1)]:
        with pytest.raises(QuotaError):
            configure_quota(runner.store, "shop", month, packs, drafts)
    assert runner.run("local-store-pack", "case", _brief()).status == "waiting_approval"
    with pytest.raises(QuotaError, match="below"):
        configure_quota(runner.store, "shop", current_period(), 0, 0)
    runner.approve("case", "owner_gate", "synthetic-owner", "test")
    original = type(runner.store).mark_run_success

    def fail_settlement(connection: Connection, run_id: str, _digest: str | None = None) -> Never:
        connection.execute("update product_usage set state='consumed' where run_id=?", (run_id,))
        reason = "synthetic transaction failure"
        raise RuntimeError(reason)

    monkeypatch.setattr("aicmo.step_state.settle_quota", fail_settlement)
    with pytest.raises(RuntimeError, match="transaction failure"):
        runner.resume("case")
    assert runner.store.get_run("case")["status"] != "success"
    assert _state(runner)["state"] == "reserved"
    with pytest.raises(StepTransitionError, match="all steps finished"):
        runner.cancel("case")
    monkeypatch.undo()
    assert original(runner.store, "case", "not-the-review", "wrong-hash") is False
    assert _state(runner)["state"] == "reserved"
    assert runner.resume("case").status == "success"
    assert _state(runner)["state"] == "consumed"


@pytest.mark.parametrize("same_run", [False, True])
def test_real_processes_share_one_allowance(tmp_path: Path, same_run: bool) -> None:
    runner = _configured(tmp_path)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps(_brief()), encoding="utf-8")
    script = """
import json, sys, time
from pathlib import Path
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.test_local_pack import PackAdapter
from tests.test_delivery_manifest import PassReviewer
class SlowPack(PackAdapter):
    def generate(self, request):
        time.sleep(0.25)
        return super().generate(request)
root = Path(sys.argv[1])
runner = WorkflowRunner(root, WorkflowStore(root/'.aicmo/runs.sqlite3'),
                        adapter=SlowPack(), review_adapter=PassReviewer())
inputs = json.loads((root/'inputs.json').read_text())
print(runner.run('local-store-pack', sys.argv[2], inputs).status)
"""
    with (
        subprocess.Popen(  # noqa: S603 — fixed synthetic script, no shell
            [sys.executable, "-c", script, str(tmp_path), "first"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as first,
        subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", script, str(tmp_path), "first" if same_run else "second"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as second,
    ):
        results = [process.communicate(timeout=45) for process in (first, second)]
        assert first.returncode == second.returncode == 0, results
        assert any(b"waiting_approval" in output for output, _ in results)
    status = quota_status(runner.store, "shop", current_period())
    assert status["draft_used"] == 1
    assert cast("dict[str, int]", status["packs"])["reserved"] == 1


def test_operator_cli_and_no_retroactive_charge(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    assert runner.run("local-store-pack", "case", _brief()).status == "waiting_approval"
    # Simulate a pre-quota-version run, which has attempts but no mode receipt.
    with runner.store.connect() as connection:
        connection.execute("delete from product_usage where run_id='case'")
    cli = CliRunner()
    result = cli.invoke(
        app,
        [
            "quota-set",
            "shop",
            "--period",
            current_period(),
            "--packs",
            "1",
            "--draft-attempts",
            "3",
            "--repo",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["mode"] == "managed"
    _finish(runner)
    assert _state(runner)["state"] == "unmetered"
    assert runner.run("local-store-pack", "paid", _brief()).status == "waiting_approval"
    _finish(runner, "paid")
    result = cli.invoke(
        app, ["quota-credit", "paid", "--reason", "synthetic credit", "--repo", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "no money refunded" in result.output
    result = cli.invoke(app, ["quota", "shop", "--repo", str(tmp_path)])
    assert json.loads(result.output)["packs"]["credited"] == 1
    result = cli.invoke(app, ["status", "paid", "--repo", str(tmp_path)])
    assert "Product: credited" in result.output
