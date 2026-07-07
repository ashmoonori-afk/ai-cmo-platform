"""Inbox ingestion: URL parsing, scanning, archiving, and the content-engine handoff."""

from __future__ import annotations

from pathlib import Path

import pytest

from aicmo.ingest import InboxItem, archive_item, parse_urls, retain_failed_urls, scan_inbox
from aicmo.runner import WorkflowRunner
from aicmo.store import WorkflowStore


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_parse_urls_filters_and_dedupes() -> None:
    text = "\n".join(
        [
            "# 오늘 본 기사",
            "https://a.example/one",
            "",
            "메모: 이건 URL 아님",
            "http://b.example/two",
            "https://a.example/one",
        ],
    )
    assert parse_urls(text) == ["https://a.example/one", "http://b.example/two"]


def test_scan_inbox_missing_dir_and_suffix_filter(tmp_path: Path) -> None:
    assert scan_inbox(tmp_path, "sample-client-a") == []
    _write(tmp_path / "inbox" / "sample-client-a" / "b.txt", "https://b.example\n")
    _write(tmp_path / "inbox" / "sample-client-a" / "a.md", "https://a.example\n")
    _write(tmp_path / "inbox" / "sample-client-a" / "ignore.png", "binary-ish")
    items = scan_inbox(tmp_path, "sample-client-a")
    assert [item.source_file.name for item in items] == ["a.md", "b.txt"]
    assert items[0].urls == ("https://a.example",)


def test_scan_inbox_rejects_unsafe_client(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="unsafe"):
        scan_inbox(tmp_path, "../evil")


def test_archive_item_is_collision_safe(tmp_path: Path) -> None:
    first = tmp_path / "inbox" / "c" / "same.txt"
    _write(first, "https://a.example\n")
    archived = archive_item(InboxItem(source_file=first, urls=("https://a.example",)))
    assert archived.name == "same.txt"
    _write(first, "https://b.example\n")
    archived_again = archive_item(InboxItem(source_file=first, urls=("https://b.example",)))
    assert archived_again.name == "same-1.txt"
    assert not first.exists()


def test_scan_inbox_survives_cp949_files(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "sample-client-a"
    inbox.mkdir(parents=True)
    (inbox / "memo.txt").write_bytes(
        "# 오늘 본 기사\nhttps://a.example/one\n".encode("cp949"),
    )
    items = scan_inbox(tmp_path, "sample-client-a")
    assert items[0].urls == ("https://a.example/one",)


def test_retain_failed_urls_rewrites_only_failures(tmp_path: Path) -> None:
    source = tmp_path / "inbox" / "c" / "mixed.txt"
    _write(source, "https://ok.example\nhttps://bad.example\n")
    item = InboxItem(source_file=source, urls=("https://ok.example", "https://bad.example"))
    retain_failed_urls(item, ["https://bad.example"])
    assert parse_urls(source.read_text(encoding="utf-8")) == ["https://bad.example"]


@pytest.fixture
def engine_repo(repo_root: Path) -> Path:
    _write(
        repo_root / "agents" / "researcher.md",
        "# Researcher\n\nVerify and summarize the source.\n",
    )
    _write(
        repo_root / "playbooks" / "03-content" / "content-engine.md",
        "# Content Engine\n\nVerify, report, post.\n",
    )
    _write(
        repo_root / "workflows" / "content-engine.workflow.yaml",
        "\n".join(
            [
                "id: content-engine",
                "name: Content Engine",
                "inputs:",
                "  client: required",
                "  source_url: required",
                "steps:",
                "  - id: load_context",
                "    type: file.load",
                "    paths:",
                "      - clients/${client}/config.md",
                "    outputs:",
                "      - artifacts/${run_id}/context.md",
                "  - id: posts_generate",
                "    type: agent",
                "    role: researcher",
                "    depends_on: [load_context]",
                "    prompt: playbooks/03-content/content-engine.md",
                "    outputs:",
                "      - artifacts/${run_id}/channel-posts.md",
                "  - id: owner_gate",
                "    type: gate",
                "    requires_approval: true",
                "    depends_on: [posts_generate]",
                "    outputs:",
                "      - artifacts/${run_id}/owner-approval.json",
            ],
        ),
    )
    return repo_root


def test_ingested_url_reaches_owner_gate(engine_repo: Path) -> None:
    runner = WorkflowRunner(
        repo_root=engine_repo,
        store=WorkflowStore(engine_repo / "runs.sqlite3"),
    )
    result = runner.run(
        "content-engine",
        "run_ingest_1",
        {"client": "sample-client-a", "source_url": "https://a.example/one"},
    )
    assert result.status == "waiting_approval"
    posts = engine_repo / "artifacts" / "run_ingest_1" / "channel-posts.md"
    assert posts.exists()
    assert "source_url" in posts.read_text(encoding="utf-8")
