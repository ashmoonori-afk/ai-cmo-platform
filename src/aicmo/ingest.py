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


def scan_inbox(repo_root: Path, client: str) -> list[InboxItem]:
    inbox = inbox_dir(repo_root, client)
    if not inbox.is_dir():
        return []
    items: list[InboxItem] = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.suffix.lower() not in INBOX_SUFFIXES:
            continue
        urls = parse_urls(path.read_text(encoding="utf-8"))
        items.append(InboxItem(source_file=path, urls=tuple(urls)))
    return items


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
