# pyright: reportImportCycles=false

from __future__ import annotations

import html
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aicmo.onboarding import OnboardingAnswers


@dataclass(frozen=True, slots=True)
class PrimerSection:
    id: str
    title: str
    build: Callable[[OnboardingAnswers, str], str]


def _e(value: str) -> str:
    return html.escape(value)


def _blank(prompt: str) -> str:
    return f'<p class="guide">{prompt}</p><div class="blank" aria-label="작성 칸"></div>'


def _overview(answers: OnboardingAnswers, date: str) -> str:
    rows = (
        ("회사명", answers.company_name),
        ("제공 상품·서비스", answers.offer),
        ("핵심 고객", answers.audience),
        ("고객 문제", answers.problem),
        ("차별점", answers.differentiator),
        ("주요 채널", answers.channel),
        ("근거", answers.proof),
        ("고객 행동(CTA)", answers.cta),
        ("웹사이트", answers.website),
        ("시장 유형", answers.market_type),
        ("클라이언트 ID", answers.client),
        ("온보딩 날짜", answers.onboarding_date),
        ("프라이머 작성일", date),
    )
    table = "".join(f"<tr><th>{label}</th><td>{_e(value)}</td></tr>" for label, value in rows)
    positioning = (
        f"대상 고객: {_e(answers.audience)} / "
        f"핵심 차별점: {_e(answers.differentiator)} / 제공 가치: {_e(answers.offer)}"
    )
    return f"""
<p>마케팅의 출발점은 누구에게 어떤 가치를 주는지 한 문장으로 정리하는 것입니다.</p>
<table class="summary"><tbody>{table}</tbody></table>
<div class="applied"><strong>자동 포지셔닝 문장</strong><p>{positioning}</p></div>"""


def _swot(answers: OnboardingAnswers, _date: str) -> str:
    return f"""
<p>SWOT은 내부의 강점·약점과 외부의 기회·위협을 나눠 보는 도구입니다.
확인된 사실과 아직 확인할 질문을 구분하세요.</p>
<table class="matrix"><tbody>
<tr><th>Strength (강점)</th><td>차별점: {_e(answers.differentiator)}<br>
근거: {_e(answers.proof)}</td>
<th>Weakness (약점)</th><td>
{_blank("성과를 방해하는 내부 부족 요소는 무엇인가요?")}</td></tr>
<tr><th>Opportunity (기회)</th><td>
{_blank("고객·시장 변화 중 활용할 수 있는 것은 무엇인가요?")}</td>
<th>Threat (위협)</th><td>
{_blank("경쟁·환경 변화 중 대비할 것은 무엇인가요?")}</td></tr>
</tbody></table>"""


def _stp(answers: OnboardingAnswers, _date: str) -> str:
    personas = "".join(
        f'<article class="card"><h3>페르소나 빈칸 {number}</h3>'
        f'{_blank("상황 / 가장 큰 문제 / 구매 기준 / 자주 쓰는 채널")}</article>'
        for number in range(1, 4)
    )
    return f"""
<p><strong>Segmentation → Targeting → Positioning</strong>:
시장을 비슷한 집단으로 나누고, 우선 고객을 고른 뒤, 선택 이유를 명확히 만듭니다.</p>
<div class="applied"><strong>현재 타깃</strong><p>{_e(answers.audience)}</p>
<p>이 고객이 해결하려는 문제: {_e(answers.problem)}</p></div>
<div class="cards">{personas}</div>"""


def _aarrr(answers: OnboardingAnswers, _date: str) -> str:
    stages = (
        ("Acquisition", "유입", f"{_e(answers.channel)}에서 방문 수와 유입 경로를 기록합니다."),
        ("Activation", "첫 가치 경험", "문의·체험 등 첫 의미 있는 행동 수를 기록합니다."),
        ("Retention", "재방문", "다시 방문하거나 서비스를 계속 이용한 고객을 확인합니다."),
        ("Referral", "추천", "소개·후기처럼 다른 고객을 데려온 행동을 확인합니다."),
        ("Revenue", "매출", "구매 수와 구매 전환 과정을 확인합니다."),
    )
    rows = "".join(
        f"<tr><th>{stage}<br><small>{meaning}</small></th><td>{application}</td>"
        f'<td><label><input type="checkbox"> 이번 달 확인할 것</label></td></tr>'
        for stage, meaning, application in stages
    )
    return f"""
<p>AARRR은 고객이 우리를 알고 매출로 이어지는 흐름을 다섯 단계로 관찰하는
퍼널입니다. 각 단계의 숫자를 먼저 기록하세요.</p>
<table class="aarrr"><thead><tr><th>단계</th><th>적용 방법</th><th>체크리스트</th></tr></thead>
<tbody>{rows}</tbody></table>"""


def _mix4p(answers: OnboardingAnswers, _date: str) -> str:
    pricing_path = f"clients/{_e(answers.client)}/pricing-rules.md"
    return f"""
<p>4P는 고객에게 무엇을, 얼마에, 어디서, 어떻게 알릴지 일관되게 맞추는 도구입니다.</p>
<table class="matrix"><tbody>
<tr><th>Product</th><td><strong>현재 상품·서비스</strong><br>{_e(answers.offer)}</td>
<th>Price</th><td>{_blank("가격 근거, 원가, 고객이 느끼는 가치, 할인 원칙은 무엇인가요?")}
<p class="note">가격 원칙은 <code class="path">{pricing_path}</code>에서
확인·작성하세요.</p></td></tr>
<tr><th>Place</th><td><strong>채널</strong>: {_e(answers.channel)}<br>
<strong>웹사이트</strong>: {_e(answers.website)}</td>
<th>Promotion</th><td>{_blank("어떤 메시지를 어떤 형식과 일정으로 알릴까요?")}</td></tr>
</tbody></table>"""


def _next90(answers: OnboardingAnswers, _date: str) -> str:
    return f"""
<p>처음 90일은 큰 성과를 약속하기보다 기준선을 만들고, 작은 실험으로 배운 뒤,
확인된 방식을 확대하는 기간입니다.</p>
<ol class="roadmap">
<li><strong>0-30일 · 기준선 만들기</strong>
<p>방문 수와 리드 수를 같은 기준으로 매주 기록합니다.</p>
{_blank("방문 수 기준선 / 리드 수 기준선")}</li>
<li><strong>31-60일 · 한 채널 실험</strong>
<p>{_e(answers.channel)} 한 곳에서 메시지나 제안 하나만 바꿔 비교합니다.</p>
{_blank("리드 전환율 목표(리드 수 ÷ 방문 수)")}</li>
<li><strong>61-90일 · 이긴 방법 확대</strong>
<p>앞선 실험에서 더 나은 방식을 반복하되 같은 지표로 확인합니다.</p>
{_blank("구매 전환율 목표 / 반복 구매율 목표")}</li>
</ol>
<div class="applied"><strong>바로 할 행동</strong>
<p>고객이 실행할 핵심 행동: {_e(answers.cta)}. 실행 경로를 만들고 결과를 기록하세요.</p>
</div>
<p class="note">실행 자료: <code>launch-pack</code> · 지역 마케팅 참고:
<code>playbooks/09-local/</code></p>"""


PRIMER_SECTIONS: tuple[PrimerSection, ...] = (
    PrimerSection("overview", "우리 가게 한눈에", _overview),
    PrimerSection("swot", "SWOT 분석", _swot),
    PrimerSection("stp", "STP (누구에게 팔 것인가)", _stp),
    PrimerSection("aarrr", "AARRR 퍼널 진단", _aarrr),
    PrimerSection("mix4p", "4P 마케팅 믹스", _mix4p),
    PrimerSection("next90", "첫 90일 KPI와 다음 단계", _next90),
)


def render_primer_html(answers: OnboardingAnswers, *, date: str = "") -> str:
    render_date = date.strip() or datetime.now(UTC).date().isoformat()
    sections = "".join(
        f'<section class="primer-section" id="{section.id}">'
        f"<h2>{index}. {section.title}</h2>{section.build(answers, render_date)}</section>"
        for index, section in enumerate(PRIMER_SECTIONS, start=1)
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(answers.company_name)} 마케팅 프라이머</title>
<style>
:root {{
  color-scheme: light; --ink: #172033; --muted: #596579;
  --line: #cbd3df; --accent: #174ea6;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0 auto; max-width: 900px; padding: 36px; color: var(--ink);
  background: #fff; font: 15px/1.6 Arial, sans-serif;
}}
h1 {{ margin-bottom: 4px; font-size: 2rem; }}
h2 {{ margin-top: 0; color: var(--accent); }} h3 {{ margin-top: 0; }}
header {{ padding-bottom: 20px; border-bottom: 3px solid var(--accent); }}
.primer-section {{
  padding: 28px 0; border-bottom: 1px solid var(--line); break-inside: avoid;
}}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{
  padding: 10px; border: 1px solid var(--line); text-align: left; vertical-align: top;
}}
th {{ background: #eef3fa; }} .summary th {{ width: 28%; }} .matrix th {{ width: 16%; }}
.applied {{
  margin: 16px 0; padding: 12px 16px; border-left: 4px solid var(--accent);
  background: #f4f7fb;
}}
.cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
.card {{ padding: 12px; border: 1px solid var(--line); }}
.guide {{ margin-bottom: 4px; color: var(--muted); }}
.blank {{ min-height: 38px; border-bottom: 1px dashed #7b8799; }}
.note, small {{ color: var(--muted); }} code {{ overflow-wrap: anywhere; }}
.roadmap li {{ margin-bottom: 18px; padding-left: 6px; }}
@page {{ size: A4; margin: 15mm; }}
@media print {{
  body {{ max-width: none; padding: 0; font-size: 10.5pt; }}
  .primer-section {{ padding: 14px 0; break-inside: auto; }}
  #aarrr, #next90 {{ break-before: page; }}
  #mix4p {{ break-inside: avoid; }}
  table, .cards, .applied, .roadmap li {{ break-inside: avoid; }}
  h2, h3 {{ break-after: avoid; }}
  h2, h3, p {{ margin-bottom: 5px; }}
  p {{ margin-top: 5px; }}
  .applied {{ margin: 8px 0; padding: 8px 12px; }}
  .roadmap li {{ margin-bottom: 8px; }}
  .aarrr th:last-child, .aarrr td:last-child {{ width: 28%; white-space: nowrap; }}
  code.path {{ white-space: nowrap; font-size: 9pt; }}
}}
@media (max-width: 650px) {{
  body {{ padding: 20px; }} .cards {{ grid-template-columns: 1fr; }}
  .matrix th, .matrix td {{ display: block; width: 100%; }}
  .aarrr {{ table-layout: fixed; }}
  .aarrr th:last-child, .aarrr td:last-child {{
    width: 40%; padding-left: 4px; padding-right: 4px;
    font-size: 0.85em; white-space: nowrap;
  }}
}}
</style>
</head>
<body>
<header><p>BEGINNER MARKETING PRIMER</p><h1>{_e(answers.company_name)}</h1>
<p>작성일: {_e(render_date)}</p></header>
<main>{sections}</main>
</body>
</html>"""
