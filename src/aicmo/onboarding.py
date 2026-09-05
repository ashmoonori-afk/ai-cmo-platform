# pyright: reportImportCycles=false

from __future__ import annotations

import re
import shutil
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from aicmo import mockup, primer
from aicmo.errors import OnboardingError
from aicmo.paths import parse_safe_id

_TEMPLATE_DIR = Path(__file__).parent / "templates" / "onboarding"
_TOKEN_PATTERN = re.compile(r"\{\{(\w+)\}\}")

_VALID_MARKET_TYPES = frozenset({"b2b", "b2c", "both"})
_ANSWERS_ADAPTER = TypeAdapter(dict[str, str | None])

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
    return OnboardingAnswers(
        **{name: values[name] for name in _REQUIRED_FIELDS},
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
    backups = {
        target: target.with_name(f".{target.name}.onboarding.bak") for target in contents
    }
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
    contents = {
        client_dir / name: _render(name, answers, date) for name in _CLIENT_TEMPLATES
    }
    contents.update(
        {
            kb_dir / name: _render(name, answers, date)
            for name in _KB_TEMPLATES
            if not (kb_dir / name).exists()
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
            client_dir.rmdir()
    if not kb_existed:
        with suppress(OSError):
            kb_dir.rmdir()


def scaffold_client(
    repo_root: Path,
    answers: OnboardingAnswers,
    *,
    force: bool = False,
    pdf: bool = True,
) -> OnboardingResult:
    slug = parse_safe_id("client", answers.client)
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
        msg = f"client already exists: {client_dir} (use force to update the profile)"
        raise OnboardingError(slug, msg)

    client_existed = client_dir.exists()
    kb_existed = kb_dir.exists()
    client_dir.mkdir(parents=True, exist_ok=True)
    kb_dir.mkdir(parents=True, exist_ok=True)
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
