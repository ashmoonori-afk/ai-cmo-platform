from __future__ import annotations

from aicmo.evaluate import evaluate_asset, render_report

STRONG = (
    "# 작은 집을 위한 저그을음 콩 왁스 향초\n\n"
    "당신의 작은 원룸은 향초를 켜면 그을음과 인공 향으로 금방 답답해집니다. "
    "우리 향초는 저그을음 콩 왁스라, 일반 파라핀 양초와 달리 작은 공간에 맞춰 향을 조절하고 "
    "다른 향초보다 오래 탑니다. "
    "동네 마켓에서 200명이 넘는 고객이 재구매했고 평점 4.9를 받았습니다. "
    "지금 스마트스토어에서 첫 향초를 주문하세요."
)

WEAK = (
    "저희 회사는 오랜 기간 동안 여러 분야에서 다양한 제품과 서비스를 폭넓게 제공해 왔으며 "
    "앞으로도 지속적으로 더욱 다양한 영역으로 사업을 확장해 나갈 계획을 가지고 있습니다"
)


def test_strong_asset_scores_pass() -> None:
    result = evaluate_asset(STRONG)
    assert result.total >= 80
    assert result.band == "PASS"


def test_weak_asset_scores_low() -> None:
    result = evaluate_asset(WEAK)
    assert result.total < 40
    assert result.band in {"FAIL", "CRITICAL"}


def test_dimension_maxes_sum_to_100() -> None:
    result = evaluate_asset(STRONG)
    assert sum(dimension.max for dimension in result.dimensions) == 100


def test_cta_detection_raises_cta_dimension() -> None:
    filler = "제품에 대한 일반적인 설명 문장입니다. " * 6
    with_cta = evaluate_asset(f"# 제목\n\n당신을 위한 제품. 지금 바로 주문하세요. {filler}")
    without_cta = evaluate_asset(f"# 제목\n\n그냥 제품에 대한 소개. {filler}")

    cta_with = next(d for d in with_cta.dimensions if "CTA" in d.name).score
    cta_without = next(d for d in without_cta.dimensions if "CTA" in d.name).score
    assert cta_with > cta_without


def test_weak_asset_lists_improvements() -> None:
    result = evaluate_asset(WEAK)
    assert result.improvements
    joined = " ".join(result.improvements).lower()
    assert "cta" in joined or "proof" in joined or "differ" in joined


def test_render_report_contains_score_and_band() -> None:
    report = render_report(evaluate_asset(STRONG), title="moms-candles landing page")
    assert "moms-candles landing page" in report
    assert "PASS" in report
    assert "/100" in report
