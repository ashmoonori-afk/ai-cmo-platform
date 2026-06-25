from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from aicmo.errors import OnboardingError
from aicmo.paths import parse_safe_id

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "onboarding"
_TOKEN_PATTERN = re.compile(r"\{\{(\w+)\}\}")

_VALID_MARKET_TYPES = frozenset({"b2b", "b2c", "both"})

_CLIENT_TEMPLATES = ("config.md", "brand-guidelines.md")
_KB_TEMPLATES = ("insights.md", "winning-copy.md", "lessons-learned.md")

_REQUIRED_FIELDS = (
    "client",
    "company_name",
    "offer",
    "audience",
    "problem",
    "differentiator",
    "channel",
    "proof",
    "cta",
)


@dataclass(frozen=True, slots=True)
class OnboardingAnswers:
    client: str
    company_name: str
    offer: str
    audience: str
    problem: str
    differentiator: str
    channel: str
    proof: str
    cta: str
    website: str = "미입력"
    market_type: str = "both"
    onboarding_date: str = ""


@dataclass(frozen=True, slots=True)
class OnboardingResult:
    client: str
    created: tuple[Path, ...]


def load_answers(path: Path) -> OnboardingAnswers:
    parsed = json.loads(path.read_text("utf-8"))
    if not isinstance(parsed, dict):
        raise OnboardingError(str(path), "answers file must be a JSON object")
    raw = cast("dict[str, object]", parsed)
    values = {key: "" if value is None else str(value) for key, value in raw.items()}
    missing = [name for name in _REQUIRED_FIELDS if not values.get(name, "").strip()]
    if missing:
        joined = ", ".join(missing)
        raise OnboardingError(str(path), f"missing required answers: {joined}")
    return OnboardingAnswers(
        client=values["client"],
        company_name=values["company_name"],
        offer=values["offer"],
        audience=values["audience"],
        problem=values["problem"],
        differentiator=values["differentiator"],
        channel=values["channel"],
        proof=values["proof"],
        cta=values["cta"],
        website=values.get("website", "미입력"),
        market_type=values.get("market_type", "both"),
        onboarding_date=values.get("onboarding_date", ""),
    )


def _render(template_name: str, answers: OnboardingAnswers, date: str) -> str:
    text = (_TEMPLATE_DIR / template_name).read_text("utf-8")
    tokens = {
        "company": answers.company_name,
        "offer": answers.offer,
        "audience": answers.audience,
        "problem": answers.problem,
        "differentiator": answers.differentiator,
        "channel": answers.channel,
        "proof": answers.proof,
        "cta": answers.cta,
        "website": answers.website,
        "market_type": answers.market_type,
        "date": date,
        "client": answers.client,
    }
    return _TOKEN_PATTERN.sub(lambda found: tokens.get(found.group(1), found.group(0)), text)


def scaffold_client(
    repo_root: Path,
    answers: OnboardingAnswers,
    *,
    force: bool = False,
) -> OnboardingResult:
    slug = parse_safe_id("client", answers.client).value
    if answers.market_type not in _VALID_MARKET_TYPES:
        allowed = ", ".join(sorted(_VALID_MARKET_TYPES))
        raise OnboardingError(slug, f"market_type must be one of: {allowed}")
    date = answers.onboarding_date.strip() or datetime.now(UTC).date().isoformat()

    root = repo_root.resolve()
    client_dir = (root / "clients" / slug).resolve()
    kb_dir = (root / "knowledge-base" / slug).resolve()
    if not client_dir.is_relative_to(root) or not kb_dir.is_relative_to(root):
        raise OnboardingError(slug, "resolved path escapes the repository root")
    if client_dir.exists() and not force:
        msg = f"client already exists: {client_dir} (use force to overwrite)"
        raise OnboardingError(slug, msg)

    created: list[Path] = []
    client_dir.mkdir(parents=True, exist_ok=True)
    for name in _CLIENT_TEMPLATES:
        out = client_dir / name
        out.write_text(_render(name, answers, date), encoding="utf-8")
        created.append(out)
    kb_dir.mkdir(parents=True, exist_ok=True)
    for name in _KB_TEMPLATES:
        out = kb_dir / name
        out.write_text(_render(name, answers, date), encoding="utf-8")
        created.append(out)
    return OnboardingResult(client=slug, created=tuple(created))
