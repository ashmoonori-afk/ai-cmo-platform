from __future__ import annotations

import re
from dataclasses import dataclass

_HEADLINE_MAX_WORDS = 12
_STRONG_SIGNAL = 2
_SENT_OK_WORDS = 20
_SENT_LONG_WORDS = 30
_MIN_BODY_WORDS = 40
_MIN_LINES = 3
_EARLY_FRACTION = 0.4
_BAND_PASS = 80
_BAND_WARN = 60
_BAND_FAIL = 40

_CTA_TERMS = (
    "buy", "order", "sign up", "signup", "get started", "start", "subscribe", "try",
    "book", "register", "download", "contact", "shop now",
    "주문", "구매", "신청", "시작", "등록", "다운로드", "문의", "예약", "구독", "지금",
)
_DIFF_TERMS = (
    "unlike", "instead of", " vs ", "versus", "only",
    "차별", "다릅", "달리", "대신", "보다", "유일", "차이",
)
_PROOF_TERMS = (
    "review", "testimonial", "customers", "rated", "rating", "guarantee", "trusted", "award",
    "고객", "후기", "평점", "보장", "신뢰", "수상", "1위", "재구매", "검증",
)
_SECOND_PERSON = ("you", "your", "당신", "여러분", "고객님", "너의")
_PROBLEM_TERMS = (
    "problem", "struggle", "frustrat", "difficult", "pain",
    "문제", "어려움", "힘든", "불편", "고민", "답답", "스트레스",
)

_SENTENCE_SPLIT = re.compile(r"[.!?。\n]+")
_DIGIT = re.compile(r"\d")


@dataclass(frozen=True, slots=True)
class EvaluationDimension:
    name: str
    score: int
    max: int
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    total: int
    band: str
    dimensions: tuple[EvaluationDimension, ...]
    improvements: tuple[str, ...]


def _present(text_lower: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in text_lower)


def _has_term_early(text_lower: str, terms: tuple[str, ...]) -> bool:
    cutoff = max(1, int(len(text_lower) * _EARLY_FRACTION))
    head = text_lower[:cutoff]
    return any(term in head for term in terms)


def _headline(text: str) -> str:
    for line in text.splitlines():
        stripped = line.lstrip("# ").strip()
        if stripped:
            return stripped
    return ""


def _dim_clarity(headline: str) -> EvaluationDimension:
    if not headline:
        return EvaluationDimension(
            "Clarity / headline", 0, 20,
            ("No clear headline — lead with a one-line promise.",),
        )
    if len(headline.split()) <= _HEADLINE_MAX_WORDS:
        return EvaluationDimension("Clarity / headline", 20, 20, ())
    return EvaluationDimension(
        "Clarity / headline", 13, 20,
        ("Headline is long (>12 words) — tighten the main promise.",),
    )


def _dim_value(text_lower: str) -> EvaluationDimension:
    hits = _present(text_lower, _DIFF_TERMS)
    if hits >= _STRONG_SIGNAL:
        return EvaluationDimension("Value / differentiation", 20, 20, ())
    if hits == 1:
        return EvaluationDimension(
            "Value / differentiation", 12, 20,
            ("Differentiation is weak — say clearly why you beat the alternatives.",),
        )
    return EvaluationDimension(
        "Value / differentiation", 0, 20,
        ("No differentiation (UVP missing) — why you instead of doing nothing?",),
    )


def _dim_cta(text_lower: str) -> EvaluationDimension:
    has = _present(text_lower, _CTA_TERMS) > 0
    if has and _has_term_early(text_lower, _CTA_TERMS):
        return EvaluationDimension("CTA strength", 15, 15, ())
    if has:
        return EvaluationDimension(
            "CTA strength", 9, 15,
            ("CTA appears late — repeat the one next step above the fold.",),
        )
    return EvaluationDimension(
        "CTA strength", 0, 15,
        ("No clear CTA — tell visitors the single next step.",),
    )


def _dim_proof(text_lower: str) -> EvaluationDimension:
    hits = _present(text_lower, _PROOF_TERMS) + (1 if _DIGIT.search(text_lower) else 0)
    if hits >= _STRONG_SIGNAL:
        return EvaluationDimension("Proof / trust", 15, 15, ())
    if hits == 1:
        return EvaluationDimension(
            "Proof / trust", 8, 15,
            ("Thin proof — add a number, testimonial, or named result.",),
        )
    return EvaluationDimension(
        "Proof / trust", 0, 15,
        ("No proof — add evidence (reviews, numbers, guarantees).",),
    )


def _dim_narrative(text_lower: str) -> EvaluationDimension:
    has_person = _present(text_lower, _SECOND_PERSON) > 0
    has_problem = _present(text_lower, _PROBLEM_TERMS) > 0
    if has_person and has_problem:
        return EvaluationDimension("Customer narrative", 10, 10, ())
    if has_person or has_problem:
        return EvaluationDimension(
            "Customer narrative", 6, 10,
            ("Address the customer (you) and name their problem.",),
        )
    return EvaluationDimension(
        "Customer narrative", 0, 10,
        ("Brand-centered copy — make the customer the hero and name their pain.",),
    )


def _dim_readability(text: str) -> EvaluationDimension:
    sentences = [part for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    if not sentences:
        return EvaluationDimension("Readability", 0, 10, ("No readable sentences.",))
    average = sum(len(part.split()) for part in sentences) / len(sentences)
    if average <= _SENT_OK_WORDS:
        return EvaluationDimension("Readability", 10, 10, ())
    if average <= _SENT_LONG_WORDS:
        return EvaluationDimension(
            "Readability", 6, 10, ("Some sentences are long — shorten them.",),
        )
    return EvaluationDimension(
        "Readability", 3, 10, ("Sentences are very long — break them up.",),
    )


def _dim_structure(text: str, headline: str) -> EvaluationDimension:
    words = len(text.split())
    lines = [line for line in text.splitlines() if line.strip()]
    score = 0
    findings: list[str] = []
    if words >= _MIN_BODY_WORDS:
        score += 5
    else:
        findings.append("Too short — add enough copy to make the case.")
    if len(lines) >= _MIN_LINES:
        score += 3
    else:
        findings.append("Single block — split into headline, body, and CTA.")
    if headline:
        score += 2
    return EvaluationDimension("Structure", score, 10, tuple(findings))


def _band(total: int) -> str:
    if total >= _BAND_PASS:
        return "PASS"
    if total >= _BAND_WARN:
        return "WARN"
    if total >= _BAND_FAIL:
        return "FAIL"
    return "CRITICAL"


def _improvements(dimensions: tuple[EvaluationDimension, ...]) -> tuple[str, ...]:
    ranked = sorted(dimensions, key=lambda dim: dim.score / dim.max if dim.max else 1.0)
    out: list[str] = []
    for dim in ranked:
        if dim.score < dim.max:
            out.extend(f"[{dim.name}] {finding}" for finding in dim.findings)
    return tuple(out)


def evaluate_asset(text: str) -> EvaluationResult:
    """Deterministically score a marketing asset 0-100 across sourced dimensions.

    Heuristic and repeatable; it judges structure and presence of conversion signals,
    not deep semantic quality (that belongs to an LLM reviewer via the adapter).
    """
    lower = text.lower()
    headline = _headline(text)
    dimensions = (
        _dim_clarity(headline),
        _dim_value(lower),
        _dim_cta(lower),
        _dim_proof(lower),
        _dim_narrative(lower),
        _dim_readability(text),
        _dim_structure(text, headline),
    )
    total = sum(dim.score for dim in dimensions)
    return EvaluationResult(
        total=total,
        band=_band(total),
        dimensions=dimensions,
        improvements=_improvements(dimensions),
    )


def render_report(result: EvaluationResult, title: str) -> str:
    lines = [
        f"# 평가 스코어카드 — {title}",
        "",
        f"**총점: {result.total}/100 — {result.band}**",
        "",
        "| 항목 | 점수 |",
        "|------|------|",
    ]
    lines.extend(f"| {dim.name} | {dim.score}/{dim.max} |" for dim in result.dimensions)
    lines.extend(["", "## 개선 우선순위 (낮은 점수 먼저)"])
    if result.improvements:
        lines.extend(f"- {item}" for item in result.improvements)
    else:
        lines.append("- 주요 약점 없음. 유지하고 모니터링하세요.")
    lines.append("")
    return "\n".join(lines)
