from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from aicmo.onboarding import OnboardingAnswers
from aicmo.primer import PRIMER_SECTIONS, render_primer_html


@pytest.fixture
def answers() -> OnboardingAnswers:
    return OnboardingAnswers(
        client="acme-client",
        company_name="<b>초보 회사</b>",
        offer="한 달 마케팅 & 코칭",
        audience="첫 광고를 준비하는 사장님",
        problem="어디서 시작할지 모름",
        differentiator='쉬운 "실습" 중심',
        channel="지역 검색 & 소개",
        proof="고객 인터뷰 12건",
        cta="무료 진단 신청",
        website="https://example.test/?a=1&b=2",
        market_type="b2b < both",
        onboarding_date="2026-02-03",
    )


def test_primer_section_registry_is_ordered_and_immutable() -> None:
    assert isinstance(PRIMER_SECTIONS, tuple)
    assert [(section.id, section.title) for section in PRIMER_SECTIONS] == [
        ("overview", "우리 가게 한눈에"),
        ("swot", "SWOT 분석"),
        ("stp", "STP (누구에게 팔 것인가)"),
        ("aarrr", "AARRR 퍼널 진단"),
        ("mix4p", "4P 마케팅 믹스"),
        ("next90", "첫 90일 KPI와 다음 단계"),
    ]
    with pytest.raises(FrozenInstanceError):
        PRIMER_SECTIONS[0].title = "변경"  # pyright: ignore[reportAttributeAccessIssue]


def test_render_primer_is_self_contained_and_has_six_sections(
    answers: OnboardingAnswers,
) -> None:
    rendered = render_primer_html(answers, date="2026-08-31")

    assert rendered.startswith("<!DOCTYPE html>")
    assert '<html lang="ko">' in rendered
    assert '<meta charset="utf-8">' in rendered
    assert "<style>" in rendered
    assert "@page" in rendered
    assert "size: A4" in rendered
    assert ".primer-section { padding: 14px 0; break-inside: auto; }" in rendered
    assert "#aarrr, #next90 { break-before: page; }" in rendered
    assert "#mix4p { break-inside: avoid; }" in rendered
    assert "table, .cards, .applied, .roadmap li { break-inside: avoid; }" in rendered
    assert "h2, h3 { break-after: avoid; }" in rendered
    assert ".aarrr th:last-child, .aarrr td:last-child" in rendered
    assert ".aarrr { table-layout: fixed; }" in rendered
    assert "font-size: 0.85em; white-space: nowrap;" in rendered
    assert "code.path { white-space: nowrap; font-size: 9pt; }" in rendered
    assert '<table class="aarrr">' in rendered
    assert '<code class="path">clients/acme-client/pricing-rules.md</code>' in rendered
    assert "<script" not in rendered.lower()
    assert "<link" not in rendered.lower()
    assert "src=" not in rendered.lower()
    assert rendered.count('class="primer-section"') == 6
    for section in PRIMER_SECTIONS:
        assert f'id="{section.id}"' in rendered
        assert section.title in rendered


def test_render_primer_escapes_and_represents_every_answer(
    answers: OnboardingAnswers,
) -> None:
    rendered = render_primer_html(answers, date="2026-08-31")
    escaped_values = [
        "acme-client",
        "&lt;b&gt;초보 회사&lt;/b&gt;",
        "한 달 마케팅 &amp; 코칭",
        "첫 광고를 준비하는 사장님",
        "어디서 시작할지 모름",
        "쉬운 &quot;실습&quot; 중심",
        "지역 검색 &amp; 소개",
        "고객 인터뷰 12건",
        "무료 진단 신청",
        "https://example.test/?a=1&amp;b=2",
        "b2b &lt; both",
        "2026-02-03",
    ]

    for value in escaped_values:
        assert value in rendered
    assert "<b>초보 회사</b>" not in rendered
    assert "한 달 마케팅 & 코칭" not in rendered
    assert "clients/acme-client/pricing-rules.md" in rendered


def test_render_primer_contains_applied_framework_sentinels(
    answers: OnboardingAnswers,
) -> None:
    rendered = render_primer_html(answers, date="2026-08-31")

    assert all(label in rendered for label in ("대상 고객:", "핵심 차별점:", "제공 가치:"))
    assert all(label in rendered for label in ("Strength", "Weakness", "Opportunity", "Threat"))
    assert rendered.count("페르소나 빈칸") == 3
    assert all(
        stage in rendered
        for stage in ("Acquisition", "Activation", "Retention", "Referral", "Revenue")
    )
    assert rendered.count("이번 달 확인할 것") == 5
    assert all(label in rendered for label in ("Product", "Price", "Place", "Promotion"))
    assert all(period in rendered for period in ("0-30일", "31-60일", "61-90일"))
    assert "launch-pack" in rendered
    assert "playbooks/09-local/" in rendered


def test_explicit_date_is_used_instead_of_current_date(answers: OnboardingAnswers) -> None:
    rendered = render_primer_html(answers, date="2040-12-25")

    assert "2040-12-25" in rendered


def test_blank_date_uses_current_utc_date(
    answers: OnboardingAnswers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: object | None = None) -> FixedDateTime:
            assert tz is UTC
            return cls(2035, 4, 5, 23, 59, tzinfo=UTC)

    monkeypatch.setattr("aicmo.primer.datetime", FixedDateTime)

    assert "2035-04-05" in render_primer_html(answers)
