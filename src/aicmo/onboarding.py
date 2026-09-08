# pyright: reportImportCycles=false

from __future__ import annotations

import re
import shutil
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from aicmo import mockup, primer
from aicmo.errors import OnboardingError
from aicmo.paths import native_io_path, parse_safe_id

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "onboarding"
_TOKEN_PATTERN = re.compile(r"\{\{(\w+)\}\}")

_VALID_MARKET_TYPES = frozenset({"b2b", "b2c", "both", "unknown"})
_VALID_FACT_STATUSES = frozenset({"confirmed", "unknown", "not_applicable"})
_CHANNEL_NAMES = (
    "네이버",
    "네이버 블로그",
    "네이버 플레이스",
    "네이버 스마트스토어",
    "스마트스토어",
    "인스타그램",
    "카카오",
    "카카오톡",
    "카카오맵",
    "유튜브",
    "당근",
    "오프라인",
    "블로그",
    "문자",
    "이메일",
    "naver",
    "instagram",
    "kakao",
    "youtube",
    "linkedin",
    "offline",
    "email",
    "web",
)
_CHANNEL_EMPTY_VALUES = frozenset({"모름", "해당없음"})
_CHANNEL_PATTERN = re.compile(
    rf"(?:{'|'.join(map(re.escape, sorted(_CHANNEL_NAMES, key=len, reverse=True)))})"
    rf"(?:\s*(?:,|/|&|\+|·|및|과|와)\s*"
    rf"(?:{'|'.join(map(re.escape, sorted(_CHANNEL_NAMES, key=len, reverse=True)))})\s*)*",
    re.IGNORECASE,
)
_ANSWERS_ADAPTER = TypeAdapter(dict[str, str | None])

_CLIENT_TEMPLATES = (
    "config.md",
    "brand-guidelines.md",
    "copy-patterns.md",
    "pricing-rules.md",
)
_KB_TEMPLATES = ("insights.md", "winning-copy.md", "lessons-learned.md")

_REQUIRED_FIELDS = (
    "client",
    "company_name",
    "offer",
    "audience",
    "problem",
    "differentiator",
    "channel",
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
    neighborhood: str = "모름"
    business_type: str = "모름"
    price: str = "모름"
    business_hours: str = "모름"
    objective: str = "모름"
    weekly_capacity: str = "모름"
    fact_status: str = "unknown"
    campaign_start: str = ""
    campaign_end: str = ""


@dataclass(frozen=True, slots=True)
class OnboardingResult:
    client: str
    created: tuple[Path, ...]
    pdf_status: str = "disabled"


def load_answers(path: Path) -> OnboardingAnswers:
    try:
        parsed = _ANSWERS_ADAPTER.validate_json(path.read_bytes(), strict=True)
    except ValidationError:
        reason = "answers file must be a JSON object with string or null values"
        raise OnboardingError(str(path), reason) from None
    values = {key: "" if value is None else value for key, value in parsed.items()}
    missing = [name for name in _REQUIRED_FIELDS if not values.get(name, "").strip()]
    if missing:
        joined = ", ".join(missing)
        raise OnboardingError(str(path), f"missing required answers: {joined}")
    answers = OnboardingAnswers(
        **{name: values[name] for name in _REQUIRED_FIELDS},
        proof=values.get("proof") or "후기없음",
        website=values.get("website", "미입력"),
        market_type=values.get("market_type", "both"),
        onboarding_date=values.get("onboarding_date", ""),
        neighborhood=values.get("neighborhood") or "모름",
        business_type=values.get("business_type") or "모름",
        price=values.get("price") or "모름",
        business_hours=values.get("business_hours") or "모름",
        objective=values.get("objective") or "모름",
        weekly_capacity=values.get("weekly_capacity") or "모름",
        fact_status=values.get("fact_status") or "unknown",
        campaign_start=values.get("campaign_start", ""),
        campaign_end=values.get("campaign_end", ""),
    )
    validate_answers(answers, subject=str(path))
    return answers


def validate_answers(answers: OnboardingAnswers, *, subject: str | None = None) -> None:
    name = subject or answers.client
    required = {field: getattr(answers, field) for field in _REQUIRED_FIELDS if field != "client"}
    missing = [field for field, value in required.items() if not value.strip()]
    if missing:
        raise OnboardingError(name, f"missing required answers: {', '.join(missing)}")
    if answers.market_type not in _VALID_MARKET_TYPES:
        allowed = ", ".join(sorted(_VALID_MARKET_TYPES))
        raise OnboardingError(name, f"market_type must be one of: {allowed}")
    if answers.fact_status not in _VALID_FACT_STATUSES:
        allowed = ", ".join(sorted(_VALID_FACT_STATUSES))
        raise OnboardingError(name, f"fact_status must be one of: {allowed}")
    channel = answers.channel.strip()
    if channel not in _CHANNEL_EMPTY_VALUES and _CHANNEL_PATTERN.fullmatch(channel) is None:
        raise OnboardingError(name, "channel must name a supported channel or use 모름/해당없음")
    _validate_price(answers.price, name)
    dates: dict[str, date] = {}
    for field in ("campaign_start", "campaign_end"):
        value = getattr(answers, field).strip()
        if value:
            try:
                dates[field] = date.fromisoformat(value)
            except ValueError:
                raise OnboardingError(name, f"{field} must be an ISO date") from None
    if all(field in dates for field in ("campaign_start", "campaign_end")) and (
        dates["campaign_start"] > dates["campaign_end"]
    ):
        raise OnboardingError(name, "campaign_start cannot be after campaign_end")


def _validate_price(raw: str, name: str) -> None:
    price = re.sub(
        r"(?<=[0-9원])\s+(?=[-\N{MINUS SIGN}\N{FULLWIDTH HYPHEN-MINUS}])",
        "",
        unicodedata.normalize("NFKC", raw),
    )
    if any(unicodedata.category(char).startswith("C") for char in price):
        raise OnboardingError(name, "price cannot contain control or invisible characters")
    negative_price = re.search(
        r"(?<![0-9원])(?:-|\N{MINUS SIGN}|\N{FULLWIDTH HYPHEN-MINUS})"
        r"\s*(?:\N{WON SIGN}|\$|KRW)?\s*\d",
        price,
        re.IGNORECASE,
    )
    if negative_price is not None:
        raise OnboardingError(name, "price cannot be negative")


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
        "neighborhood": answers.neighborhood,
        "business_type": answers.business_type,
        "price": answers.price,
        "business_hours": answers.business_hours,
        "objective": answers.objective,
        "weekly_capacity": answers.weekly_capacity,
        "fact_status": answers.fact_status,
        "campaign_start": answers.campaign_start or "해당없음",
        "campaign_end": answers.campaign_end or "해당없음",
    }
    return _TOKEN_PATTERN.sub(lambda found: tokens.get(found.group(1), found.group(0)), text)


def _restore_profile_files(written: list[Path], backups: dict[Path, Path]) -> list[str]:
    errors: list[str] = []
    for target in reversed(written):
        try:
            backup = backups[target]
            if backup.exists():
                backup.replace(target)
            else:
                target.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(f"{target}: {exc}")
    return errors


def _prepare_profile_backups(backups: dict[Path, Path]) -> None:
    for target, backup in backups.items():
        if target.exists():
            shutil.copy2(target, backup)


def _write_profile_files(contents: dict[Path, str], slug: str) -> None:
    """Replace profile files together; retain recoverable backups until commit."""
    # Containment is checked by scaffold_client; keep its returned paths logical.
    contents = {native_io_path(path): content for path, content in contents.items()}
    backups = {target: target.with_name(f".{target.name}.onboarding.bak") for target in contents}
    temporary = {target: target.with_name(f".{target.name}.onboarding.tmp") for target in contents}
    leftovers = [path for path in (*backups.values(), *temporary.values()) if path.exists()]
    if leftovers:
        names = ", ".join(str(path) for path in leftovers)
        raise OnboardingError(slug, f"unfinished onboarding backup exists: {names}")

    written: list[Path] = []
    try:
        _prepare_profile_backups(backups)
        for target, content in contents.items():
            temp = temporary[target]
            temp.write_text(content, encoding="utf-8")
            temp.replace(target)
            written.append(target)
    except Exception as exc:
        recovery_errors = _restore_profile_files(written, backups)
        if recovery_errors:
            detail = "; ".join(recovery_errors)
            message = f"profile update failed; backups retained: {detail}"
            raise OnboardingError(slug, message) from exc
        for backup in backups.values():
            backup.unlink(missing_ok=True)
        raise OnboardingError(slug, f"profile update failed and was rolled back: {exc}") from exc
    else:
        for backup in backups.values():
            backup.unlink(missing_ok=True)
    finally:
        for temp in temporary.values():
            temp.unlink(missing_ok=True)


def _profile_contents(
    client_dir: Path,
    kb_dir: Path,
    answers: OnboardingAnswers,
    date: str,
) -> dict[Path, str]:
    contents = {client_dir / name: _render(name, answers, date) for name in _CLIENT_TEMPLATES}
    contents.update(
        {
            kb_dir / name: _render(name, answers, date)
            for name in _KB_TEMPLATES
            if not native_io_path(kb_dir / name).exists()
        }
    )
    contents[client_dir / "primer-report.html"] = primer.render_primer_html(answers, date=date)
    return contents


def _remove_new_empty_directories(
    client_dir: Path,
    kb_dir: Path,
    *,
    client_existed: bool,
    kb_existed: bool,
) -> None:
    if not client_existed:
        with suppress(OSError):
            native_io_path(client_dir).rmdir()
    if not kb_existed:
        with suppress(OSError):
            native_io_path(kb_dir).rmdir()


def scaffold_client(
    repo_root: Path,
    answers: OnboardingAnswers,
    *,
    force: bool = False,
    pdf: bool = True,
) -> OnboardingResult:
    slug = parse_safe_id("client", answers.client)
    validate_answers(answers)
    date = answers.onboarding_date.strip() or datetime.now(UTC).date().isoformat()

    root = repo_root.resolve()
    client_dir = (root / "clients" / slug).resolve()
    kb_dir = (root / "knowledge-base" / slug).resolve()
    if not client_dir.is_relative_to(root) or not kb_dir.is_relative_to(root):
        raise OnboardingError(slug, "resolved path escapes the repository root")
    if native_io_path(client_dir).exists() and not force:
        msg = f"client already exists: {client_dir} (use force to update the profile)"
        raise OnboardingError(slug, msg)

    client_existed = native_io_path(client_dir).exists()
    kb_existed = native_io_path(kb_dir).exists()
    native_io_path(client_dir).mkdir(parents=True, exist_ok=True)
    native_io_path(kb_dir).mkdir(parents=True, exist_ok=True)
    contents = _profile_contents(client_dir, kb_dir, answers, date)
    html_path = client_dir / "primer-report.html"
    try:
        _write_profile_files(contents, slug)
    except OnboardingError:
        _remove_new_empty_directories(
            client_dir,
            kb_dir,
            client_existed=client_existed,
            kb_existed=kb_existed,
        )
        raise
    created = list(contents)
    pdf_status = "disabled"
    if pdf:
        pdf_status = mockup.render_pdf(html_path, client_dir / "primer-report.pdf")
        if pdf_status == "generated":
            created.append(client_dir / "primer-report.pdf")
    return OnboardingResult(client=slug, created=tuple(created), pdf_status=pdf_status)
