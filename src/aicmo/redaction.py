"""Deterministic sanitizer: mask credential-shaped values, keep legitimate text."""

from __future__ import annotations

import re

REDACTED = "[redacted]"

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


def _mask(match: re.Match[str]) -> str:
    prefix = match.group(1) if match.lastindex else ""
    return f"{prefix}{REDACTED}"


def redact(text: str) -> str:
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(_mask, result)
    return result


def contains_raw_secret(value: str) -> bool:
    """Approved secret references (env:NAME) pass; credential-shaped literals do not."""
    if value.startswith("env:"):
        return False
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)
