from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.cli import app
from aicmo.errors import WorkflowExecutionError
from aicmo.export import export_local_pack, verified_pack
from aicmo.local_pack import NO_PHOTO, PROVIDED_PHOTO, parse_brief, render_pack, validate_pack
from aicmo.photos import parse_photos
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore
from tests.conftest import write_text
from tests.test_delivery_manifest import PassReviewer

REPO = Path(__file__).resolve().parents[1]
PASS_REVIEWER = PassReviewer()


def _brief(*, minutes: int = 30, photos: bool = True, reviews: int = 5) -> dict[str, str]:
    return {
        "client": "shop",
        "brief_json": json.dumps(
            {
                "owner_minutes": minutes,
                "photo_available": photos,
                "facts": [
                    "동네 가게는 이번 주에도 평소 영업시간에 운영합니다.",
                    "방문 전 메뉴와 예약 가능 시간을 확인하실 수 있습니다.",
                ],
                "reviews": [
                    f"리뷰 {n}: 조용하게 기다릴 수 있어서 좋았습니다." for n in range(reviews)
                ],
            },
            ensure_ascii=False,
        ),
    }


def _content(inputs: dict[str, str]) -> str:
    brief = parse_brief(inputs)
    photos = {photo.news_index for photo in parse_photos(inputs).photos}
    return json.dumps(
        {
            "schema_version": "aicmo.local-pack.v1",
            "summary": "이번 주 가게 소식과 리뷰 답글입니다.",
            "channel": "naver",
            "sources": brief.facts,
            "news": [
                {
                    "title": "이번 주 가게 안내",
                    "body": brief.facts[n],
                    "cta": "방문 전 안내를 확인해 주세요.",
                    "period": "상시 안내",
                    "source_index": n,
                    "photo_instruction": PROVIDED_PHOTO if n in photos else NO_PHOTO,
                    "visual_asset_status": "provided" if n in photos else "unavailable",
                    "status": "draft",
                }
                for n in range(brief.news_count)
            ],
            "replies": [
                {
                    "review_index": n,
                    "body": "방문 경험을 남겨 주셔서 감사합니다.",
                    "status": "draft",
                }
                for n in range(brief.reply_count)
            ],
            "weekly_actions": [
                {"when": "이번 주 영업 전", "action": "소식 확인 후 직접 게시", "minutes": 2},
                {"when": "이번 주 마감 후", "action": "답글과 수기 성과 확인", "minutes": 2},
            ],
            "next_steps": [
                "사장님은 오늘 문안을 확인합니다.",
                "사장님은 게시 후 결과를 기록합니다.",
            ],
        },
        ensure_ascii=False,
    )


@dataclass
class PackAdapter:
    requests: list[AgentRequest] = field(default_factory=list)
    override: str | None = None

    def generate(self, request: AgentRequest) -> AgentResult:
        self.requests.append(request)
        return AgentResult(
            self.override
            if self.override is not None
            else _content(json.loads(request.inputs_json))
        )


def _runner(root: Path, *, reviewer: PassReviewer | None = PASS_REVIEWER) -> WorkflowRunner:
    for relative in (
        "workflows/local-store-pack.workflow.yaml",
        "playbooks/09-local/local-store-pack.md",
        "agents/copywriter.md",
        "agents/reporter.md",
        "agents/reviewer.md",
        "prompts/shared/gate-check.md",
        "prompts/shared/deliverable-standard.md",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    for name in ("config", "brand-guidelines", "pricing-rules", "copy-patterns"):
        write_text(
            root / f"clients/shop/{name}.md", "# 동네 가게\n\n사실에 맞게 차분하게 안내합니다."
        )
    return WorkflowRunner(
        root,
        WorkflowStore(root / ".aicmo/runs.sqlite3"),
        adapter=PackAdapter(),
        review_adapter=reviewer,
    )


def _approve(runner: WorkflowRunner) -> None:
    runner.approve("case", "owner_gate", "synthetic-owner", "합성 검증")
    assert runner.resume("case").status == "success"


@pytest.mark.parametrize(
    ("minutes", "photos", "reviews", "news_count", "reply_count"),
    [
        (30, True, 5, 1, 5),
        (30, False, 0, 1, 0),
        (5, True, 5, 1, 2),
    ],
)
def test_owner_review_export_journey(
    tmp_path: Path,
    minutes: int,
    photos: bool,
    reviews: int,
    news_count: int,
    reply_count: int,
) -> None:
    runner = _runner(tmp_path)
    inputs = _brief(minutes=minutes, photos=photos, reviews=reviews)
    assert runner.run("local-store-pack", "case", inputs).status == "waiting_approval"
    with pytest.raises(WorkflowExecutionError, match="successful"):
        export_local_pack(runner, "case")
    _approve(runner)
    bundle, approved_files = verified_pack(runner, "case")
    assert not (tmp_path / "artifacts/case/exports").exists()
    path = export_local_pack(runner, "case")
    assert path == export_local_pack(runner, "case")
    with ZipFile(path) as archive:
        assert {name: archive.read(name) for name in archive.namelist()} == approved_files
        names = archive.namelist()
        assert len([n for n in names if n.startswith("news-")]) == news_count
        assert len([n for n in names if n.startswith("reply-")]) == reply_count
        assert not any(n.endswith((".png", ".html", ".pdf")) for n in names)
        guide = archive.read("guide.md").decode("utf-8")
        assert "한 장 요약" in guide
        assert "다음 단계" in guide
        assert "직접" in guide
        assert "리뷰 0:" not in guide
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["bundle_sha256"] == bundle
        assert manifest["external_publish_status"] == "not_published"
        assert manifest["visual_asset_status"] == "unavailable"
    cli = CliRunner().invoke(app, ["export-local-pack", "case", "--repo", str(tmp_path)])
    assert cli.exit_code == 0, cli.output
    assert path.name in cli.output


@pytest.mark.parametrize("damage", ["edited", "missing", "manifest", "cancelled", "spec"])
def test_export_rejects_stale_or_changed_run(tmp_path: Path, damage: str) -> None:
    runner = _runner(tmp_path)
    runner.run("local-store-pack", "case", _brief())
    _approve(runner)
    draft = tmp_path / "artifacts/case/local-pack.json"
    if damage == "edited":
        draft.write_text(
            draft.read_text("utf-8").replace("이번 주 가게 안내", "바뀐 가게 안내"), "utf-8"
        )
    elif damage == "missing":
        draft.unlink()
    elif damage == "manifest":
        (tmp_path / "artifacts/case/delivery-review.json").write_text(
            '{"deliverable":true}', "utf-8"
        )
    elif damage == "cancelled":
        with runner.store.connect() as connection:
            connection.execute("update runs set status='cancelled' where run_id='case'")
    else:
        prompt = tmp_path / "playbooks/09-local/local-store-pack.md"
        prompt.write_text(prompt.read_text("utf-8") + "\n추가 기준", "utf-8")
    with pytest.raises(WorkflowExecutionError):
        export_local_pack(runner, "case")
    assert not (tmp_path / "artifacts/case/exports").exists()


@pytest.mark.parametrize("reviewer", [None, PassReviewer("WARN")])
def test_export_requires_reviewer_pass(tmp_path: Path, reviewer: PassReviewer | None) -> None:
    runner = _runner(tmp_path, reviewer=reviewer)
    runner.run("local-store-pack", "case", _brief())
    _approve(runner)
    with pytest.raises(WorkflowExecutionError, match="reviewer PASS"):
        export_local_pack(runner, "case")


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not json",
        '{"owner_minutes":true}',
        '{"owner_minutes":30,"facts":["hi"],"channel":"reddit"}',
        '{"owner_minutes":0,"facts":["hi"]}',
    ],
)
def test_invalid_brief_fails_before_run_or_adapter(tmp_path: Path, bad: str) -> None:
    runner = _runner(tmp_path)
    with pytest.raises(WorkflowExecutionError, match="brief"):
        runner.run("local-store-pack", "case", {"client": "shop", "brief_json": bad})
    assert isinstance(runner.adapter, PackAdapter)
    assert not runner.adapter.requests
    assert not (tmp_path / "artifacts/case").exists()


@pytest.mark.parametrize(
    "damage",
    ["empty", "image", "photo_claim", "source", "reply", "capacity", "html"],
)
def test_bad_pack_contract_is_rejected(tmp_path: Path, damage: str) -> None:
    inputs = _brief()
    content = json.loads(_content(inputs))
    if damage == "empty":
        content["news"][0]["body"] = " "
    elif damage == "image":
        content["news"][0]["visual_asset_status"] = "generated"
    elif damage == "photo_claim":
        content["news"][0]["photo_instruction"] = "AI 사진 생성이 완료됐습니다. 파일을 사용하세요."
    elif damage == "source":
        content["sources"][0] = "새로 만든 사실"
    elif damage == "reply":
        content["replies"][0]["review_index"] = 4
    elif damage == "capacity":
        content["weekly_actions"][0]["minutes"] = 240
    runner = _runner(tmp_path)
    assert isinstance(runner.adapter, PackAdapter)
    runner.adapter.override = "<html>not JSON</html>" if damage == "html" else json.dumps(content)
    result = runner.run("local-store-pack", "case", inputs)
    assert result.status == "failed"
    assert result.failed_step_id == "drafts"
    assert not (tmp_path / "artifacts/case/local-pack.json").exists()


def test_owner_edits_get_final_review_and_later_edit_requires_new_approval(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    runner.run("local-store-pack", "case", _brief())
    draft = tmp_path / "artifacts/case/local-pack.json"
    draft.write_text(
        draft.read_text("utf-8").replace("이번 주 가게 안내", "이번 주 예약 안내"), "utf-8"
    )
    runner.approve("case", "owner_gate", "synthetic-owner", "수정 확인", accept_edits=True)
    assert runner.resume("case").status == "success"
    with ZipFile(export_local_pack(runner, "case")) as archive:
        assert "이번 주 예약 안내" in archive.read("news-1.txt").decode("utf-8")
    draft.write_text(draft.read_text("utf-8") + " ", "utf-8")
    with pytest.raises(WorkflowExecutionError):
        export_local_pack(runner, "case")
    assert runner.resume("case").status == "waiting_approval"
    assert runner.store.approval_for("case", "owner_gate") is None


def test_contract_requires_all_supplied_review_indexes() -> None:
    inputs = _brief()
    content = json.loads(_content(inputs))
    content["replies"] = []
    with pytest.raises(WorkflowExecutionError):
        validate_pack(json.dumps(content), inputs)


def test_duplicate_brief_and_output_fields_are_rejected() -> None:
    inputs = _brief()
    inputs["brief_json"] = inputs["brief_json"].replace(
        '"owner_minutes": 30',
        '"owner_minutes": 10, "owner_minutes": 30',
    )
    with pytest.raises(WorkflowExecutionError):
        parse_brief(inputs)
    inputs = _brief()
    text = _content(inputs).replace('"channel": "naver"', '"channel":"x", "channel":"naver"')
    with pytest.raises(WorkflowExecutionError):
        validate_pack(text, inputs)


def test_markdown_guide_treats_generated_markup_as_text() -> None:
    inputs = _brief()
    pack = validate_pack(_content(inputs), inputs)
    pack.news[0].title = "<script>alert(1)</script> [open](javascript:alert(1))"
    files = render_pack(pack)
    assert "<script>" not in files["guide.md"]
    assert "[open](javascript:" not in files["guide.md"]
    assert r"\[open\]" in files["guide.md"]
    assert "<script>" in files["news-1.txt"]  # Plain text retains exact copy; never HTML.


def test_demo_and_corrupted_export_are_not_delivered(tmp_path: Path) -> None:
    prepared = _runner(tmp_path / "demo")
    runner = WorkflowRunner(prepared.repo_root, prepared.store, review_adapter=PASS_REVIEWER)
    runner.run("local-store-pack", "case", _brief())
    _approve(runner)
    with pytest.raises(WorkflowExecutionError, match="demo"):
        export_local_pack(runner, "case")
    runner = _runner(tmp_path / "live-fixture")
    runner.run("local-store-pack", "case", _brief())
    _approve(runner)
    path = export_local_pack(runner, "case")
    path.write_bytes(b"not a zip")
    with pytest.raises(WorkflowExecutionError, match="existing export differs"):
        export_local_pack(runner, "case")
    assert path.read_bytes() == b"not a zip"


def test_truncated_context_never_reaches_generator(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    write_text(tmp_path / "clients/shop/config.md", "가게 정보 " * 6000)
    result = runner.run("local-store-pack", "case", _brief())
    assert result.status == "failed"
    assert isinstance(runner.adapter, PackAdapter)
    assert runner.adapter.requests == []


def test_cli_brief_file_preserves_unicode_and_rejects_conflicting_sources(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    brief = tmp_path / "우리 가게.json"
    brief.write_text(_brief()["brief_json"], "utf-8-sig")
    args = [
        "run",
        "local-store-pack",
        "--repo",
        str(tmp_path),
        "--client",
        "shop",
        "--run-id",
        "cli-case",
        "--brief-file",
        str(brief),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 75, result.output
    assert "동네 가게" in runner.store.get_inputs("cli-case")["brief_json"]
    result = CliRunner().invoke(app, [*args, "--input", "brief_json={}"])
    assert result.exit_code == 2
    assert "not both" in result.output


@pytest.mark.parametrize("invisible", ["\u200b", "\u200c\ufeff", "\u0301", "\u2060", "\x1b[0m"])
def test_invisible_brief_and_pack_content_cannot_be_delivered(
    tmp_path: Path, invisible: str
) -> None:
    inputs = _brief()
    brief = json.loads(inputs["brief_json"])
    brief["facts"] = [invisible]
    with pytest.raises(WorkflowExecutionError):
        parse_brief({"brief_json": json.dumps(brief)})
    payload = json.loads(_content(inputs))
    payload["news"][0]["body"] = invisible
    runner = _runner(tmp_path)
    assert isinstance(runner.adapter, PackAdapter)
    runner.adapter.override = json.dumps(payload)
    assert runner.run("local-store-pack", "case", inputs).status == "failed"
    with pytest.raises(WorkflowExecutionError):
        export_local_pack(runner, "case")
    assert not (tmp_path / "artifacts/case/exports").exists()


def test_visible_korean_with_windows_line_endings_is_preserved() -> None:
    inputs = _brief()
    payload = json.loads(_content(inputs))
    payload["news"][0]["body"] = "가게 안내입니다.\r\n방문 전 확인해 주세요."
    pack = validate_pack(json.dumps(payload), inputs)
    assert "\r\n" in render_pack(pack)["news-1.txt"]
