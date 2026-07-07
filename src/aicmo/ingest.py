"""Inbox ingestion: URL files dropped under inbox/<client>/ become content-engine runs.

The Korean-market replacement for the original pipeline's Slack ingestion — an
operator (or a cron'd Claude Code session) drops one .txt/.md file per source,
one URL per line. Processed files are archived under inbox/<client>/processed/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aicmo.paths import parse_safe_id

INBOX_SUFFIXES = (".txt", ".md")
_URL_SCHEMES = ("http://", "https://")


@dataclass(frozen=True, slots=True)
class InboxItem:
    source_file: Path
    urls: tuple[str, ...]


def parse_urls(text: str) -> list[str]:
    """One URL per line; blank lines and # comments are ignored, order-preserving dedupe."""
    urls: list[str] = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if candidate.startswith(_URL_SCHEMES):
            urls.append(candidate)
    return list(dict.fromkeys(urls))


def inbox_dir(repo_root: Path, client: str) -> Path:
    slug = parse_safe_id("client", client).value
    return repo_root / "inbox" / slug


def _read_inbox_text(path: Path) -> str:
    """Korean Windows editors commonly save CP949 — never crash the whole ingest
    on one file's encoding. URLs are ASCII, so a lossy last-resort decode is safe."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def scan_inbox(repo_root: Path, client: str) -> list[InboxItem]:
    inbox = inbox_dir(repo_root, client)
    if not inbox.is_dir():
        return []
    items: list[InboxItem] = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.suffix.lower() not in INBOX_SUFFIXES:
            continue
        urls = parse_urls(_read_inbox_text(path))
        items.append(InboxItem(source_file=path, urls=tuple(urls)))
    return items


def retain_failed_urls(item: InboxItem, failed: list[str]) -> None:
    """Partial failure: rewrite the inbox file to only the still-failing URLs so
    the next pass retries those without duplicating already-started runs."""
    body = "\n".join(["# retry: 이전 ingest에서 실패한 URL만 남김", *failed])
    item.source_file.write_text(body + "\n", encoding="utf-8")


def archive_item(item: InboxItem) -> Path:
    """Move a processed inbox file into processed/, never overwriting an earlier archive."""
    processed = item.source_file.parent / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    target = processed / item.source_file.name
    counter = 1
    while target.exists():
        target = processed / f"{item.source_file.stem}-{counter}{item.source_file.suffix}"
        counter += 1
    item.source_file.replace(target)
    return target
