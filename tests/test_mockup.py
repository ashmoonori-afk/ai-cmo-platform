from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from aicmo.mockup import LandingBrief, brief_from_answers, render_landing_mockup, render_png
from aicmo.onboarding import OnboardingAnswers

BRIEF = LandingBrief(
    company="엄마의 양초",
    offer="작은 집을 위한 저그을음 콩 왁스 향초",
    audience="원룸에 사는, 은은한 향을 원하는 사람",
    problem="싼 향초는 향이 인공적이고 그을음이 난다",
    differentiator="저그을음 콩 왁스, 작은 공간용 향 배합",
    proof="동네 마켓에서 200명 재구매, 평점 4.9",
    cta="스마트스토어에서 첫 향초 주문하기",
)


def test_mockup_is_valid_html_document() -> None:
    html = render_landing_mockup(BRIEF)
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html
    assert "viewport" in html
    assert "tailwindcss" in html


def test_mockup_contains_every_brief_field() -> None:
    html = render_landing_mockup(BRIEF)
    for field in (
        BRIEF.company,
        BRIEF.offer,
        BRIEF.problem,
        BRIEF.differentiator,
        BRIEF.proof,
        BRIEF.cta,
    ):
        assert field in html, f"mockup is missing brief field: {field}"


def test_mockup_escapes_user_content() -> None:
    brief = replace(BRIEF, offer="<script>alert(1)</script>")
    html = render_landing_mockup(brief)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_brief_from_answers_reuses_onboarding_format() -> None:
    answers = OnboardingAnswers(
        client="x",
        company_name="Acme",
        offer="An offer",
        audience="An audience",
        problem="A problem",
        differentiator="A differentiator",
        channel="A channel",
        proof="Some proof",
        cta="Do the thing",
    )
    brief = brief_from_answers(answers)
    assert brief.company == "Acme"
    assert brief.offer == "An offer"
    assert brief.cta == "Do the thing"


def test_render_png_returns_status_without_crashing(tmp_path: Path) -> None:
    html_path = tmp_path / "mockup.html"
    html_path.write_text(render_landing_mockup(BRIEF), encoding="utf-8")

    status = render_png(html_path, tmp_path / "mockup.png")

    assert isinstance(status, str)
    assert status == "generated" or "playwright" in status.lower()
