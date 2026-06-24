from __future__ import annotations

from pathlib import Path

import pytest


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def lines(*values: str) -> str:
    return "\n".join(values)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    write_text(
        tmp_path / "clients" / "sample-client-a" / "config.md",
        "# Sample Client A\n\n- Product: Corporate flower subscription\n",
    )
    write_text(
        tmp_path / "clients" / "sample-client-a" / "brand-guidelines.md",
        "# Brand\n\nClear, calm, evidence-led.\n",
    )
    write_text(
        tmp_path / "agents" / "seo-specialist.md",
        "# SEO Specialist\n\nResearch keywords before drafting.\n",
    )
    write_text(
        tmp_path / "agents" / "copywriter.md",
        "# Copywriter\n\nWrite concise drafts.\n",
    )
    write_text(
        tmp_path / "agents" / "reviewer.md",
        "# Reviewer\n\nReturn PASS, WARN, FAIL, or ESCALATE.\n",
    )
    write_text(
        tmp_path / "agents" / "reporter.md",
        "# Reporter\n\nRecord delivery and KB queue.\n",
    )
    write_text(
        tmp_path / "playbooks" / "05-seo" / "keyword-research.md",
        "# Keyword Research\n\nFind target search intent.\n",
    )
    write_text(
        tmp_path / "playbooks" / "03-content" / "blog-article.md",
        "# Blog Article\n\nDraft the article.\n",
    )
    write_text(
        tmp_path / "workflows" / "blog-article.workflow.yaml",
        lines(
            "id: blog-article",
            "name: SEO Blog Article",
            "inputs:",
            "  client: required",
            "  topic: required",
            "  target_keyword: optional",
            "steps:",
            "  - id: load_context",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
            "      - clients/${client}/brand-guidelines.md",
            "    outputs:",
            "      - artifacts/${run_id}/context.md",
            "  - id: keyword_research",
            "    type: agent",
            "    role: seo-specialist",
            "    depends_on: [load_context]",
            "    prompt: playbooks/05-seo/keyword-research.md",
            "    outputs:",
            "      - artifacts/${run_id}/keyword-brief.md",
            "  - id: draft",
            "    type: agent",
            "    role: copywriter",
            "    depends_on: [keyword_research]",
            "    prompt: playbooks/03-content/blog-article.md",
            "    outputs:",
            "      - artifacts/${run_id}/draft.md",
            "  - id: review",
            "    type: gate",
            "    role: reviewer",
            "    depends_on: [draft]",
            "    pass_if: \"status in ['PASS','WARN']\"",
            "    outputs:",
            "      - artifacts/${run_id}/review.json",
            "  - id: report",
            "    type: agent",
            "    role: reporter",
            "    depends_on: [review]",
            "    outputs:",
            "      - artifacts/${run_id}/content-log.md",
        ),
    )
    return tmp_path
