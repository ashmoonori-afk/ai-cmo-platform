from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from aicmo.errors import AicmoError, OnboardingError
from aicmo.onboarding import OnboardingAnswers, load_answers, scaffold_client

REPO_ROOT = Path(__file__).resolve().parents[1]

PLACEHOLDER = re.compile(r"\{\{?[A-Za-z_][A-Za-z0-9_]*\}?\}")


def sample_answers() -> OnboardingAnswers:
    return OnboardingAnswers(
        client="moms-candles",
        company_name="엄마의 양초",
        offer="작은 집을 위한 손수 부은 콩 왁스 향초",
        audience="원룸·작은 아파트에 사는, 그을음 없이 은은한 향을 원하는 사람",
        problem="싼 향초는 향이 인공적이고 작은 방을 그을음으로 채운다",
        differentiator="저그을음 콩 왁스와 작은 공간에 맞춘 향 배합",
        channel="인스타그램과 네이버 스마트스토어",
        proof="동네 마켓에서 200개를 팔았고 재구매 고객이 많다",
        cta="스마트스토어에서 첫 향초 주문하기",
        website="https://example.com/moms-candles",
        market_type="b2c",
        onboarding_date="2026-06-25",
        neighborhood="망원동",
        business_type="향초 소매",
        price="18,000원",
        business_hours="화~일 11:00~20:00",
        objective="첫 구매 20건",
        weekly_capacity="주 3시간",
        fact_status="confirmed",
        campaign_start="2026-07-01",
        campaign_end="2026-07-31",
    )


def test_scaffold_embeds_all_seven_answers(tmp_path: Path) -> None:
    answers = sample_answers()

    result = scaffold_client(tmp_path, answers, pdf=False)

    config_text = (tmp_path / "clients" / "moms-candles" / "config.md").read_text("utf-8")
    for value in (
        answers.company_name,
        answers.offer,
        answers.audience,
        answers.problem,
        answers.differentiator,
        answers.channel,
        answers.proof,
        answers.cta,
    ):
        assert value in config_text, f"config.md is missing the answer: {value}"
    assert (tmp_path / "clients" / "moms-candles" / "config.md") in result.created
    assert "aicmo.smb-profile.v1" in config_text
    assert answers.neighborhood in config_text
    assert answers.price in config_text
    assert (tmp_path / "clients" / "moms-candles" / "copy-patterns.md").exists()
    assert (tmp_path / "clients" / "moms-candles" / "pricing-rules.md").exists()


def test_generated_files_have_no_placeholders_and_define_jargon(tmp_path: Path) -> None:
    scaffold_client(tmp_path, sample_answers(), pdf=False)

    client_dir = tmp_path / "clients" / "moms-candles"
    config_text = (client_dir / "config.md").read_text("utf-8")
    brand_text = (client_dir / "brand-guidelines.md").read_text("utf-8")

    for name, text in (("config.md", config_text), ("brand-guidelines.md", brand_text)):
        leftover = PLACEHOLDER.search(text)
        assert leftover is None, f"{name} still has placeholder token: {leftover!r}"
        assert "(자동수집)" not in text, f"{name} still has blank auto-collect marker"
        assert "__%" not in text, f"{name} still has blank percentage marker"

    assert "ICP (Ideal Customer Profile" in config_text
    assert "CTA (Call" in config_text
    assert "UVP (Unique" in config_text


def test_kb_files_initialized(tmp_path: Path) -> None:
    scaffold_client(tmp_path, sample_answers(), pdf=False)

    kb_dir = tmp_path / "knowledge-base" / "moms-candles"
    for name in ("insights.md", "winning-copy.md", "lessons-learned.md"):
        assert (kb_dir / name).read_text("utf-8").strip(), f"KB file {name} is empty"


def test_load_answers_round_trip(tmp_path: Path) -> None:
    payload = {
        "client": "moms-candles",
        "company_name": "엄마의 양초",
        "offer": "작은 집을 위한 콩 왁스 향초",
        "audience": "작은 집에 사는 사람",
        "problem": "싼 향초는 그을음이 난다",
        "differentiator": "저그을음 콩 왁스",
        "channel": "인스타그램",
        "proof": "200개 판매",
        "cta": "첫 향초 주문하기",
    }
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    answers = load_answers(answers_path)

    assert answers.client == "moms-candles"
    assert answers.offer == payload["offer"]
    assert answers.market_type == "both"


def test_new_store_can_start_without_proof(tmp_path: Path) -> None:
    payload = asdict(sample_answers())
    payload.pop("proof")
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    answers = load_answers(answers_path)
    scaffold_client(tmp_path, answers, pdf=False)

    assert answers.proof == "후기없음"
    config = (tmp_path / "clients" / answers.client / "config.md").read_text("utf-8")
    assert "후기없음" in config


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"offer": ""}, "missing required answers: offer"),
        ({"price": "-1000원"}, "price cannot be negative"),
        ({"price": "가격:(-1000원)"}, "price cannot be negative"),
        ({"price": "\N{MINUS SIGN}1000원"}, "price cannot be negative"),
        ({"price": "-\N{WON SIGN}1000"}, "price cannot be negative"),
        ({"price": "KRW -1000"}, "price cannot be negative"),
        ({"price": "price -1000"}, "price cannot be negative"),
        (
            {"campaign_start": "2026-08-01", "campaign_end": "2026-07-01"},
            "campaign_start cannot be after campaign_end",
        ),
        ({"campaign_start": "2026-07-01T23:00:00"}, "must be an ISO date"),
        ({"channel": "임의채널"}, "channel must name a supported channel"),
        ({"channel": "instagrammer"}, "channel must name a supported channel"),
        ({"channel": "인스타그램, 텔레그램"}, "channel must name a supported channel"),
        ({"channel": "후기없음"}, "channel must name a supported channel"),
    ],
)
def test_profile_validation_rejects_invalid_input(
    tmp_path: Path,
    changes: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(OnboardingError, match=message):
        scaffold_client(tmp_path, replace(sample_answers(), **changes), pdf=False)


def test_unknown_and_not_applicable_profile_values_are_allowed(tmp_path: Path) -> None:
    answers = replace(
        sample_answers(),
        channel="모름",
        proof="후기없음",
        price="모름",
        business_hours="해당없음",
        fact_status="unknown",
        campaign_start="",
        campaign_end="",
    )

    scaffold_client(tmp_path, answers, pdf=False)

    config = (tmp_path / "clients" / answers.client / "config.md").read_text("utf-8")
    assert "후기없음" in config
    assert "해당없음 ~ 해당없음" in config


@pytest.mark.parametrize("price", ["10,000원-20,000원", "10,000원 - 20,000원"])
def test_positive_price_ranges_are_allowed(tmp_path: Path, price: str) -> None:
    scaffold_client(tmp_path, replace(sample_answers(), price=price), pdf=False)


@pytest.mark.parametrize("channel", ["네이버 블로그", "카카오톡", "네이버 플레이스"])
def test_domestic_channel_aliases_are_allowed(tmp_path: Path, channel: str) -> None:
    scaffold_client(tmp_path, replace(sample_answers(), channel=channel), pdf=False)


@pytest.mark.parametrize(
    "content",
    ["{", '"scalar"', "[]"],
    ids=["malformed", "scalar", "array"],
)
def test_load_answers_rejects_malformed_or_non_object_json(
    tmp_path: Path,
    content: str,
) -> None:
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(content, encoding="utf-8")

    with pytest.raises(
        OnboardingError,
        match="answers file must be a JSON object with string or null values",
    ):
        load_answers(answers_path)


@pytest.mark.parametrize(
    "value",
    [42, True, [], {}],
    ids=["number", "boolean", "array", "object"],
)
def test_load_answers_rejects_non_string_values(
    tmp_path: Path,
    value: int | bool | list[str] | dict[str, str],
) -> None:
    payload = asdict(sample_answers())
    payload["offer"] = value
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(
        OnboardingError,
        match="answers file must be a JSON object with string or null values",
    ):
        load_answers(answers_path)


def test_unsafe_slug_is_rejected(tmp_path: Path) -> None:
    answers = OnboardingAnswers(
        client="../evil",
        company_name="x",
        offer="x",
        audience="x",
        problem="x",
        differentiator="x",
        channel="x",
        proof="x",
        cta="x",
    )
    with pytest.raises(AicmoError):
        scaffold_client(tmp_path, answers, pdf=False)


def test_existing_client_not_overwritten_without_force(tmp_path: Path) -> None:
    answers = sample_answers()
    scaffold_client(tmp_path, answers, pdf=False)

    with pytest.raises(AicmoError):
        scaffold_client(tmp_path, answers, pdf=False)

    forced = scaffold_client(tmp_path, answers, force=True, pdf=False)
    assert forced.created


def test_force_migrates_legacy_config_and_keeps_recoverable_backup_during_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = sample_answers()
    client_dir = tmp_path / "clients" / answers.client
    client_dir.mkdir(parents=True)
    legacy = client_dir / "config.md"
    legacy.write_text("# 기존 고객 설정\n\n운영 중인 원문\n", encoding="utf-8")
    observed_backup = False
    original_replace = Path.replace

    def observe_backup(source: Path, target: Path) -> Path:
        nonlocal observed_backup
        if source.name == ".config.md.onboarding.tmp":
            backup = target.with_name(".config.md.onboarding.bak")
            observed_backup = backup.read_text("utf-8") == legacy.read_text("utf-8")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", observe_backup)

    scaffold_client(tmp_path, answers, force=True, pdf=False)

    assert observed_backup
    assert "aicmo.smb-profile.v1" in legacy.read_text("utf-8")


def test_force_update_preserves_existing_knowledge_base_bytes(tmp_path: Path) -> None:
    answers = sample_answers()
    scaffold_client(tmp_path, answers, pdf=False)
    kb_dir = tmp_path / "knowledge-base" / answers.client
    paths = [kb_dir / name for name in ("insights.md", "winning-copy.md", "lessons-learned.md")]
    for index, path in enumerate(paths):
        path.write_bytes(b"\xef\xbb\xbf" + f"owner knowledge {index}\r\n".encode())
    before = {path: path.read_bytes() for path in paths}

    updated = replace(answers, company_name="엄마의 새 향초")
    scaffold_client(tmp_path, updated, force=True, pdf=False)

    assert {path: path.read_bytes() for path in paths} == before
    config = (tmp_path / "clients" / answers.client / "config.md").read_text("utf-8")
    assert "엄마의 새 향초" in config


def test_force_update_rolls_back_all_profile_files_on_mid_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = sample_answers()
    scaffold_client(tmp_path, answers, pdf=False)
    client_dir = tmp_path / "clients" / answers.client
    paths = [
        client_dir / name
        for name in ("config.md", "brand-guidelines.md", "primer-report.html")
    ]
    before = {path: path.read_bytes() for path in paths}
    original_replace = Path.replace
    replacements = 0

    def fail_second_profile_replace(source: Path, target: Path) -> Path:
        nonlocal replacements
        if source.name.endswith(".onboarding.tmp"):
            replacements += 1
            if replacements == 2:
                message = "injected mid-update failure"
                raise OSError(message)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second_profile_replace)

    with pytest.raises(OnboardingError, match="rolled back"):
        scaffold_client(tmp_path, replace(answers, offer="변경된 상품"), force=True, pdf=False)

    assert {path: path.read_bytes() for path in paths} == before
    assert not list(client_dir.glob(".*.onboarding.*"))


def test_playbook_and_template_break_circular_dependency() -> None:
    playbook_path = REPO_ROOT / "playbooks" / "07-operations" / "client-onboarding.md"
    playbook = playbook_path.read_text("utf-8")
    template = (REPO_ROOT / "clients" / "_template" / "config.md").read_text("utf-8")

    assert "7가지 평문 질문" in playbook
    assert "먼저 생성" in playbook
    assert "config.md" in playbook
    for n in range(1, 8):
        assert f"{n})" in playbook, f"playbook is missing plain question {n})"

    assert "ICP (Ideal Customer Profile" in template
    assert "CTA (Call" in template


def test_json_null_becomes_blank_not_literal_none(tmp_path: Path) -> None:
    payload = {
        "client": "moms-candles",
        "company_name": "엄마의 양초",
        "offer": "콩 왁스 향초",
        "audience": "작은 집에 사는 사람",
        "problem": "싼 향초는 그을음이 난다",
        "differentiator": "저그을음 콩 왁스",
        "channel": "인스타그램",
        "proof": "200개 판매",
        "cta": "첫 향초 주문하기",
        "website": None,
    }
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    answers = load_answers(answers_path)

    assert answers.website == ""
    assert "None" not in answers.website


def test_literal_token_in_answer_is_not_re_expanded(tmp_path: Path) -> None:
    answers = replace(sample_answers(), offer="{{cta}} 라는 글자가 그대로 남아야 한다")

    scaffold_client(tmp_path, answers, pdf=False)

    config_text = (tmp_path / "clients" / "moms-candles" / "config.md").read_text("utf-8")
    assert "{{cta}} 라는 글자가 그대로 남아야 한다" in config_text
    assert "스마트스토어에서 첫 향초 주문하기 라는 글자가" not in config_text
