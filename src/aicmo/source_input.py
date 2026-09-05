from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

from aicmo.errors import WorkflowExecutionError
from aicmo.redaction import is_customer_phone, minimize_customer_pii

SOURCE_MANIFEST_SCHEMA_VERSION = "aicmo.source-manifest.v1"
MAX_SOURCE_TEXT_BYTES = 64 * 1024
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
_PUBLIC_CONTACT_INPUTS = frozenset(
    {"public_store_phone", "public_contact_approved", "public_contact_purpose"}
)
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\((?:https?://|www\.)[^)]+\)", re.IGNORECASE)
_HTML_LINK = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*['\"]?(?:https?://|www\.)[^>]+>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_SOURCE_LINK_WORDS = re.compile(
    r"(?i)\b(?:see|source|original|link|url|available|at|here|is)\b"
)
_SOURCE_LINK_KOREAN = re.compile(
    r"(?:원문|출처|링크|주소|여기|보기|참조|참고|확인|있습니다|있어요|은|는|이|가|에)"
)
_MIN_SOURCE_CONTENT_CHARS = 8
_INVISIBLE_CHARACTERS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))
_KST = timezone(timedelta(hours=9), "KST")


@dataclass(frozen=True, slots=True)
class PreparedInputs:
    values: dict[str, str]
    source_manifest: dict[str, JsonValue] | None = None


def operating_inputs() -> frozenset[str]:
    return _PUBLIC_CONTACT_INPUTS


def source_checked_date(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(_KST).date()


def _minimize_inputs(inputs: dict[str, str]) -> dict[str, str]:
    step_id = "inputs"
    approved = inputs.get("public_contact_approved", "false").casefold()
    if approved not in {"true", "false"}:
        raise WorkflowExecutionError(step_id, "public_contact_approved must be true or false")
    public_phone = inputs.get("public_store_phone", "").strip()
    purpose = inputs.get("public_contact_purpose", "").strip()
    if public_phone and approved != "true":
        raise WorkflowExecutionError(
            step_id,
            "public store phone requires public_contact_approved=true",
        )
    if approved == "true" and (not public_phone or not purpose):
        raise WorkflowExecutionError(
            step_id,
            "approved public contact requires public_store_phone and public_contact_purpose",
        )
    if public_phone and not is_customer_phone(public_phone):
        raise WorkflowExecutionError(step_id, "public_store_phone must be a valid phone number")

    return {
        key: (
            value
            if key == "public_store_phone" and approved == "true"
            else minimize_customer_pii(value)
        )
        for key, value in inputs.items()
    }


def _has_source_content(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text).translate(
        _INVISIBLE_CHARACTERS,
    )
    for line in normalized.splitlines():
        if _URL.search(line) or _MARKDOWN_LINK.search(line) or _HTML_LINK.search(line):
            continue
        without_english = _SOURCE_LINK_WORDS.sub("", line)
        without_boilerplate = _SOURCE_LINK_KOREAN.sub("", without_english)
        content = re.sub(r"[\s\W_]+", "", without_boilerplate, flags=re.UNICODE)
        if len(content) >= _MIN_SOURCE_CONTENT_CHARS:
            return True
    return False


def prepare_workflow_inputs(  # noqa: C901 — sequential fail-closed source validation
    declared_inputs: dict[str, str],
    inputs: dict[str, str],
) -> PreparedInputs:
    step_id = "inputs"
    safe = _minimize_inputs(inputs)
    if "source_url" not in declared_inputs:
        return PreparedInputs(safe)

    url = inputs.get("source_url", "").strip()
    try:
        parsed = urlsplit(url)
        valid_url = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        reason = "source_url must be an http(s) URL without credentials"
        raise WorkflowExecutionError(step_id, reason)
    if re.search(r"%(?![0-9A-Fa-f]{2})", url):
        raise WorkflowExecutionError(step_id, "source_url must use valid percent encoding")
    try:
        unquote(url, errors="strict")
    except UnicodeDecodeError:
        raise WorkflowExecutionError(
            step_id,
            "source_url must use valid UTF-8 percent encoding",
        ) from None
    source_text = inputs.get("source_text", "")
    if not _has_source_content(source_text):
        raise WorkflowExecutionError(
            step_id,
            "external source unavailable: source_url was provided without source content; "
            "this runner does not fetch external URLs",
        )
    if len(source_text.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES:
        raise WorkflowExecutionError(
            step_id,
            f"source_text exceeds {MAX_SOURCE_TEXT_BYTES} UTF-8 bytes",
        )
    checked_at = inputs.get("source_checked_at", "").strip()
    try:
        checked_date = date.fromisoformat(checked_at)
    except ValueError:
        raise WorkflowExecutionError(step_id, "source_checked_at must be an ISO date") from None
    if checked_date.isoformat() != checked_at:
        raise WorkflowExecutionError(step_id, "source_checked_at must be an ISO date")
    if checked_date > source_checked_date():
        raise WorkflowExecutionError(step_id, "source_checked_at cannot be in the future")

    safe_text = safe["source_text"]
    manifest: dict[str, JsonValue] = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "source_url": safe["source_url"],
        "checked_at": checked_at,
        "content_status": "provided_by_user",
        "external_fetch": "unavailable",
        "pii_minimized": True,
        "content_bytes": len(safe_text.encode("utf-8")),
        "content_sha256": hashlib.sha256(safe_text.encode()).hexdigest(),
    }
    return PreparedInputs(safe, manifest)
