"""Deterministic sanitizer: mask credential-shaped values, keep legitimate text."""

from __future__ import annotations

import json
import re
import unicodedata
from urllib.parse import unquote

from aicmo.errors import WorkflowExecutionError

REDACTED = "[redacted]"
CUSTOMER_EMAIL_REDACTED = "[customer-email]"
CUSTOMER_PHONE_REDACTED = "[customer-phone]"
CUSTOMER_NAME_REDACTED = "[customer-name]"
CUSTOMER_ADDRESS_REDACTED = "[customer-address]"
CUSTOMER_FIELD_MARKERS = {
    **dict.fromkeys(
        (
            "customer_name",
            "customer",
            "reviewer",
            "reviewer_name",
            "full_name",
            "first_name",
            "last_name",
        ),
        CUSTOMER_NAME_REDACTED,
    ),
    **dict.fromkeys(
        ("customer_address", "home_address", "shipping_address", "billing_address"),
        CUSTOMER_ADDRESS_REDACTED,
    ),
}

# Each pattern either captures a prefix to keep (group 1: the key name / scheme up to
# its separator) followed by the secret value, or matches a bare token wholesale.
# Emails, phone numbers, and ordinary Korean/It English prose must never match.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/\s?#@]+@"),
    re.compile(r"(?i)\b(bearer\s+)[a-z0-9_.=/+\-]{8,}"),
    re.compile(
        r"(?i)\b((?:api[_-]?key|token|secret|password|passwd|credential|"
        r"비밀[ _-]?번호|암호|(?:인증|API)[ _-]?키|토큰)\s*[=:]\s*)[^\s&\"']{6,}"
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
_NANP_FIRST = r"[2-9\N{FULLWIDTH DIGIT TWO}-\N{FULLWIDTH DIGIT NINE}]"
_NANP_AREA = rf"{_NANP_FIRST}{_D}{{2}}"
_NANP_PHONE_PATTERN = re.compile(
    r"(?<![\w+])(?:[+\N{FULLWIDTH PLUS SIGN}]?"
    rf"{_D1}{_PHONE_SEPARATOR})?"
    rf"(?:\({_NANP_AREA}\)|{_NANP_AREA}){_PHONE_SEPARATOR}"
    rf"{_NANP_FIRST}{_D}{{2}}{_PHONE_SEPARATOR}{_D}{{4}}(?!\w)"
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
_PERSON_NAME = r"[가-힣]{2,4}"
_URL_NAME_PATTERN = re.compile(
    r"(?i)(?P<label>(?<![\w-])(?:customer[_-]?name|customer|reviewer|name)=|"
    r"/(?:customer[_-]?name|customer|reviewer|name)/)"
    rf"(?P<name>{_PERSON_NAME})(?![\w'-])"
)
_URL_CUSTOMER_NAME_PATTERN = re.compile(
    r"(?i)(?P<label>(?<![\w-])(?:customer[_-]?name|reviewer[_-]?name)(?:=|/))"
    r"[^/?&#\s\"'<>\[\]]+"
)
_ENGLISH_NAME_PATTERN = re.compile(
    r"(?im)(?P<label>(?:^\s*name|(?<![\w?&/-])(?:customer(?:[ _-]+name)?|"
    r"reviewer(?:[ _-]+name)?|(?:full|first|last)[ _-]+name))"
    r"[ \t]*[\"']?[ \t]*(?:[:=]| - )[ \t]*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^,;/\r\n&\"<>\[\]{}]+)"
)
_CUSTOMER_ADDRESS_PATTERN = re.compile(
    r"(?im)(?P<label>(?<![\w-])(?:customer|home|shipping|billing)[ _-]+address"
    r"[ \t]*[\"']?[ \t]*(?:[:=]| - )[ \t]*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^;\r\n&\"<>\[\]{}]+)"
)
_CUSTOMER_NAME_PATTERN = re.compile(r"(?<![가-힣])(?P<name>[가-힣]{2,4})(?=\s*고객(?:님)?)")
_INVISIBLE_CHARACTERS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))
_PERCENT_COMPONENT = re.compile(r"(?=[^/?#&=\s]*%[0-9A-Fa-f]{2})[^/?#&=\s]+")


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
    # A normalized shadow detects disguised credentials without activating fullwidth markup.
    normalized = unicodedata.normalize("NFKC", result)
    if any(pattern.sub(_mask, normalized) != normalized for pattern in _SECRET_PATTERNS):
        return REDACTED
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
    result = _NANP_PHONE_PATTERN.sub(
        lambda match: (
            match.group(0)
            if _normalized_pii_candidate(match.group(0)) in allow
            else CUSTOMER_PHONE_REDACTED
        ),
        result,
    )
    result = _LABELED_NAME_PATTERN.sub(
        lambda match: f"{match.group('label')}{CUSTOMER_NAME_REDACTED}",
        result,
    )
    for pattern in (_URL_NAME_PATTERN, _URL_CUSTOMER_NAME_PATTERN):
        result = pattern.sub(
            lambda match: f"{match.group('label')}{CUSTOMER_NAME_REDACTED}",
            result,
        )
    for pattern, marker in (
        (_ENGLISH_NAME_PATTERN, CUSTOMER_NAME_REDACTED),
        (_CUSTOMER_ADDRESS_PATTERN, CUSTOMER_ADDRESS_REDACTED),
    ):

        def mask_field(match: re.Match[str], marker: str = marker) -> str:
            value = match.group("value")
            if not value.strip() or value.strip() in {"null", "true", "false"}:
                return match.group(0)
            quote = value[0] if value[0] in "\"'" and value[-1] == value[0] else ""
            return f"{match.group('label')}{quote}{marker}{quote}"

        result = pattern.sub(mask_field, result)
    return _CUSTOMER_NAME_PATTERN.sub(CUSTOMER_NAME_REDACTED, result)


type _JsonValue = str | int | float | bool | None | list[_JsonValue] | dict[str, _JsonValue]


def normalize_customer_key(key: str) -> str:
    return (
        re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key).casefold().replace("-", "_").replace(" ", "_")
    )


def _minimize_json_fields(
    value: _JsonValue,
    allowed: tuple[str, ...],
    *,
    customer_context: bool = False,
) -> _JsonValue:
    if isinstance(value, dict):
        result: dict[str, _JsonValue] = {}
        for key, item in value.items():
            field = normalize_customer_key(key)
            marker = CUSTOMER_FIELD_MARKERS.get(field)
            if customer_context and field in {"name", "address"}:
                marker = CUSTOMER_NAME_REDACTED if field == "name" else CUSTOMER_ADDRESS_REDACTED
            result[key] = (
                marker
                if marker and isinstance(item, str) and item.strip()
                else _minimize_json_fields(
                    item,
                    allowed,
                    customer_context=customer_context
                    or field
                    in {
                        "customer",
                        "customers",
                        "reviewer",
                        "reviewers",
                    },
                )
            )
        return result
    if isinstance(value, list):
        return [
            _minimize_json_fields(item, allowed, customer_context=customer_context)
            for item in value
        ]
    if isinstance(value, str):
        return minimize_customer_pii(value, allowed=allowed)
    return value


def minimize_customer_pii(text: str, *, allowed: tuple[str, ...] = ()) -> str:
    """Mask recognized contacts and labelled fields; this is not anonymization.

    ponytail: free-text identity inference is not covered; minimize structured inputs
    first and review residual text before enabling additional personal-data use.
    """
    if text.lstrip().startswith(("{", "[")):
        try:
            data: _JsonValue = json.loads(text)
            minimized = _minimize_json_fields(data, allowed)
            return (
                text if minimized == data else json.dumps(minimized, ensure_ascii=False, indent=2)
            )
        except RecursionError:
            step_id = "privacy"
            reason = "JSON nesting exceeds privacy inspection limits; provide shallower data"
            raise WorkflowExecutionError(step_id, reason) from None
        except ValueError:
            pass
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
                CUSTOMER_ADDRESS_REDACTED,
            )
            if marker in minimized
        )
        if markers:
            return "".join(markers)
        prefix = text[max(0, match.start() - 32) : match.start()]
        name_context = re.search(
            r"(?i)(?<![\w-])(?:name|customer|reviewer|customer[_-]name|고객명|이름)(?:=|/)$",
            prefix,
        )
        if name_context and re.fullmatch(_PERSON_NAME, decoded):
            return CUSTOMER_NAME_REDACTED
        return match.group(0)

    decoded_pii_minimized = _PERCENT_COMPONENT.sub(replace_encoded, text)
    return _minimize_clear_customer_pii(decoded_pii_minimized, allow)


def is_customer_phone(value: str) -> bool:
    normalized = _normalized_pii_candidate(value).strip()
    return any(
        pattern.fullmatch(normalized)
        for pattern in (
            _CANONICAL_PHONE_PATTERN,
            _NANP_PHONE_PATTERN,
        )
    )


def contains_raw_secret(value: str) -> bool:
    """Approved secret references (env:NAME) pass; credential-shaped literals do not."""
    if re.fullmatch(r"env:[A-Za-z_][A-Za-z0-9_]*", value):
        return False
    normalized = unicodedata.normalize("NFKC", value)
    return any(pattern.search(normalized) for pattern in _SECRET_PATTERNS)


MAX_KB_ENTRY_CHARS = 500
_MAX_RAW_KB_CHARS = 16 * 1024


def safe_kb_text(text: str) -> str:
    """Validate/minimize new KB and feedback entries before SQLite or file persistence."""
    step_id = "knowledge-storage"
    if len(text) > _MAX_RAW_KB_CHARS:
        reason = "knowledge entry is too large; provide a short summary"
        raise WorkflowExecutionError(step_id, reason)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs"} and char not in "\n\t" for char in text
    ):
        reason = "knowledge entry contains unsupported control or invisible characters"
        raise WorkflowExecutionError(step_id, reason)
    safe = minimize_customer_pii(redact(text)).strip()
    if not safe or not any(unicodedata.category(char)[0] in "LNPS" for char in safe):
        reason = "knowledge entry must contain visible content"
        raise WorkflowExecutionError(step_id, reason)
    if len(safe) > MAX_KB_ENTRY_CHARS:
        reason = "knowledge entry exceeds 500 characters after minimization; summarize first"
        raise WorkflowExecutionError(step_id, reason)
    return safe
