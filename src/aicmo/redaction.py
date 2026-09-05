"""Deterministic sanitizer: mask credential-shaped values, keep legitimate text."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import unquote

REDACTED = "[redacted]"
CUSTOMER_EMAIL_REDACTED = "[customer-email]"
CUSTOMER_PHONE_REDACTED = "[customer-phone]"
CUSTOMER_NAME_REDACTED = "[customer-name]"

# Each pattern either captures a prefix to keep (group 1: the key name / scheme up to
# its separator) followed by the secret value, or matches a bare token wholesale.
# Emails, phone numbers, and ordinary Korean/It English prose must never match.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(bearer\s+)[a-z0-9_.=/+\-]{8,}"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|token|secret|password|passwd|credential)\s*[=:]\s*)[^\s&\"']{6,}"
    ),
    re.compile(
        r"(?i)([?&][^=&\s]*(?:signature|sig|token|key|credential|session)[^=&\s]*=)[^&\s\"']+"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.|\n)*?-----END [A-Z ]*PRIVATE KEY-----"),
)

_CANONICAL_EMAIL_PATTERN = re.compile(
    r"(?i)(?<![\w.+-])[\w.+-]+@"
    r"[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])"
)
_EMAIL_INVISIBLE = "\u200b\u200c\u200d\u2060\ufeff"
_EMAIL_LOCAL = rf"[\w+\-{_EMAIL_INVISIBLE}]+"
_EMAIL_DOMAIN = rf"[\w\-{_EMAIL_INVISIBLE}]+"
_EMAIL_DOT = (
    r"(?:\.|%2[eE]|\N{FULLWIDTH FULL STOP}|"
    r"\s*(?:\[dot\]|\(dot\))\s*)"
)
_FULLWIDTH_AT = "\uff20"
_EMAIL_AT = rf"(?:@|%40|{_FULLWIDTH_AT}|\[at\]|\(at\)|&#(?:0*64|x0*40);)"
_EMAIL_CANDIDATE_PATTERN = re.compile(
    rf"(?i)(?<![\w.+-]){_EMAIL_LOCAL}(?:{_EMAIL_DOT}{_EMAIL_LOCAL})*\s*"
    rf"{_EMAIL_AT}\s*{_EMAIL_DOMAIN}"
    rf"(?:{_EMAIL_DOT}{_EMAIL_DOMAIN})+(?![\w.-])"
)
_CANONICAL_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:(?:(?:\+?82(?:[ ._\N{FULLWIDTH HYPHEN-MINUS}-]?\(0\))?"
    r"[ ._\N{FULLWIDTH HYPHEN-MINUS}-]?|0)"
    r"(?:1[016789]|2|[3-6][1-5]|50[2-8]|70|80)"
    r"[ ._\N{FULLWIDTH HYPHEN-MINUS}-]?\d{3,4}"
    r"[ ._\N{FULLWIDTH HYPHEN-MINUS}-]?\d{4})|"
    r"(?:1[568]\d{2}[ ._\N{FULLWIDTH HYPHEN-MINUS}-]?\d{4}))(?!\d)"
)
_D = r"[0-9\N{FULLWIDTH DIGIT ZERO}-\N{FULLWIDTH DIGIT NINE}]"
_D0 = r"[0\N{FULLWIDTH DIGIT ZERO}]"
_D1 = r"[1\N{FULLWIDTH DIGIT ONE}]"
_D2 = r"[2\N{FULLWIDTH DIGIT TWO}]"
_D3_6 = r"[3-6\N{FULLWIDTH DIGIT THREE}-\N{FULLWIDTH DIGIT SIX}]"
_D1_5 = r"[1-5\N{FULLWIDTH DIGIT ONE}-\N{FULLWIDTH DIGIT FIVE}]"
_D2_8 = r"[2-8\N{FULLWIDTH DIGIT TWO}-\N{FULLWIDTH DIGIT EIGHT}]"
_D5 = r"[5\N{FULLWIDTH DIGIT FIVE}]"
_D6 = r"[6\N{FULLWIDTH DIGIT SIX}]"
_D7 = r"[7\N{FULLWIDTH DIGIT SEVEN}]"
_D8 = r"[8\N{FULLWIDTH DIGIT EIGHT}]"
_D9 = r"[9\N{FULLWIDTH DIGIT NINE}]"
_PHONE_SEPARATOR = (
    r"(?:(?:[ ._\N{FULLWIDTH HYPHEN-MINUS}\u200b\u200c\u200d\u2060\ufeff-]|"
    r"%2[dD]|%20)){0,3}"
)
_MOBILE_PREFIX = rf"{_D1}(?:{_D0}|{_D1}|{_D6}|{_D7}|{_D8}|{_D9})"
_AREA_PREFIX = (
    rf"(?:{_MOBILE_PREFIX}|{_D2}|{_D3_6}{_D1_5}|{_D5}{_D0}{_D2_8}|"
    rf"{_D7}{_D0}|{_D8}{_D0})"
)
_PHONE_CANDIDATE_PATTERN = re.compile(
    rf"(?<!{_D})(?:(?:(?:\+?{_D8}{_D2}"
    rf"(?:{_PHONE_SEPARATOR}\({_D0}\))?{_PHONE_SEPARATOR}|{_D0})"
    rf"{_AREA_PREFIX}{_PHONE_SEPARATOR}{_D}{{3,4}}{_PHONE_SEPARATOR}{_D}{{4}})|"
    rf"(?:{_D1}(?:{_D5}|{_D6}|{_D8}){_D}{{2}}{_PHONE_SEPARATOR}{_D}{{4}}))"
    rf"(?!{_D})"
)
_GAP = r"[\s\u200b\u200c\u200d\u2060\ufeff]*"
_REQUIRED_GAP = r"[\s\u200b\u200c\u200d\u2060\ufeff]+"
_LABELED_NAME_PATTERN = re.compile(
    rf"(?P<label>(?:고{_GAP}객(?:{_GAP}명|{_GAP}이{_GAP}름)|"
    rf"구{_GAP}매{_GAP}자{_GAP}명|주{_GAP}문{_GAP}자|예{_GAP}약{_GAP}자|"
    rf"작{_GAP}성{_GAP}자|리{_GAP}뷰{_GAP}어|이{_GAP}름|성{_GAP}명)"
    rf"(?:{_GAP}[:=\uff1a-]{_GAP}|{_REQUIRED_GAP}))"
    rf"(?P<name>[^,;/\n]{{2,40}})"
)
_URL_NAME_PATTERN = re.compile(
    r"(?i)(?P<label>(?:customer[_-]?name|customer|reviewer|name)=|"
    r"/(?:customer[_-]?name|customer|reviewer|name)/)"
    r"(?P<name>[가-힣]{2,4})(?![가-힣])"
)
_CUSTOMER_NAME_PATTERN = re.compile(r"(?<![가-힣])(?P<name>[가-힣]{2,4})(?=\s*고객(?:님)?)")
_INVISIBLE_CHARACTERS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))
_PERCENT_COMPONENT = re.compile(
    r"(?=[^/?#&=\s]*%[0-9A-Fa-f]{2})[^/?#&=\s]+"
)


def _normalized_pii_candidate(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(_INVISIBLE_CHARACTERS)
    normalized = re.sub(
        r"(?i)\s*(?:\[at\]|\(at\)|&#(?:0*64|x0*40);)\s*",
        "@",
        normalized,
    )
    normalized = re.sub(r"(?i)\s*(?:\[dot\]|\(dot\))\s*", ".", normalized)
    normalized = re.sub(r"(?i)%40", "@", normalized)
    normalized = re.sub(r"(?i)%2d", "-", normalized)
    normalized = re.sub(r"(?i)%2e", ".", normalized)
    return re.sub(r"(?i)%20", " ", normalized)


def _mask(match: re.Match[str]) -> str:
    prefix = match.group(1) if match.lastindex else ""
    return f"{prefix}{REDACTED}"


def redact(text: str) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(_mask, result)
    return result


def _minimize_clear_customer_pii(text: str, allow: frozenset[str]) -> str:
    def replace_email(match: re.Match[str]) -> str:
        normalized = _normalized_pii_candidate(match.group(0))
        if _CANONICAL_EMAIL_PATTERN.fullmatch(normalized) is None:
            return match.group(0)
        return match.group(0) if normalized in allow else CUSTOMER_EMAIL_REDACTED

    result = _EMAIL_CANDIDATE_PATTERN.sub(replace_email, text)

    def replace_phone(match: re.Match[str]) -> str:
        normalized = _normalized_pii_candidate(match.group(0))
        if _CANONICAL_PHONE_PATTERN.fullmatch(normalized) is None:
            return match.group(0)
        return match.group(0) if normalized in allow else CUSTOMER_PHONE_REDACTED

    result = _PHONE_CANDIDATE_PATTERN.sub(replace_phone, result)
    result = _LABELED_NAME_PATTERN.sub(
        lambda match: f"{match.group('label')}{CUSTOMER_NAME_REDACTED}",
        result,
    )
    result = _URL_NAME_PATTERN.sub(
        lambda match: f"{match.group('label')}{CUSTOMER_NAME_REDACTED}",
        result,
    )
    return _CUSTOMER_NAME_PATTERN.sub(CUSTOMER_NAME_REDACTED, result)


def minimize_customer_pii(text: str, *, allowed: tuple[str, ...] = ()) -> str:
    """Remove customer contact details and explicitly labelled names from model data."""
    allow = frozenset(_normalized_pii_candidate(value) for value in allowed if value)

    def replace_encoded(match: re.Match[str]) -> str:
        try:
            decoded = unquote(match.group(0), errors="strict")
        except UnicodeDecodeError:
            return "[invalid-percent-encoding]"
        minimized = _minimize_clear_customer_pii(decoded, allow)
        markers = tuple(
            marker
            for marker in (
                CUSTOMER_NAME_REDACTED,
                CUSTOMER_EMAIL_REDACTED,
                CUSTOMER_PHONE_REDACTED,
            )
            if marker in minimized
        )
        if markers:
            return "".join(markers)
        prefix = text[max(0, match.start() - 32) : match.start()]
        name_context = re.search(
            r"(?i)(?:name|customer|reviewer|customer[_-]name|고객명|이름)(?:=|/)$",
            prefix,
        )
        if name_context and re.fullmatch(r"[가-힣]{2,4}", decoded):
            return CUSTOMER_NAME_REDACTED
        return match.group(0)

    decoded_pii_minimized = _PERCENT_COMPONENT.sub(replace_encoded, text)
    return _minimize_clear_customer_pii(decoded_pii_minimized, allow)


def is_customer_phone(value: str) -> bool:
    normalized = _normalized_pii_candidate(value).strip()
    return _CANONICAL_PHONE_PATTERN.fullmatch(normalized) is not None


def contains_raw_secret(value: str) -> bool:
    """Approved secret references (env:NAME) pass; credential-shaped literals do not."""
    if value.startswith("env:"):
        return False
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)
