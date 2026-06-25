from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from aicmo.errors import AicmoError
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
    )


def test_scaffold_embeds_all_seven_answers(tmp_path: Path) -> None:
    answers = sample_answers()

    result = scaffold_client(tmp_path, answers)

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


def test_generated_files_have_no_placeholders_and_define_jargon(tmp_path: Path) -> None:
    scaffold_client(tmp_path, sample_answers())

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
    scaffold_client(tmp_path, sample_answers())

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
        scaffold_client(tmp_path, answers)


def test_existing_client_not_overwritten_without_force(tmp_path: Path) -> None:
    answers = sample_answers()
    scaffold_client(tmp_path, answers)

    with pytest.raises(AicmoError):
        scaffold_client(tmp_path, answers)

    forced = scaffold_client(tmp_path, answers, force=True)
    assert forced.created


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

    scaffold_client(tmp_path, answers)

    config_text = (tmp_path / "clients" / "moms-candles" / "config.md").read_text("utf-8")
    assert "{{cta}} 라는 글자가 그대로 남아야 한다" in config_text
    assert "스마트스토어에서 첫 향초 주문하기 라는 글자가" not in config_text
