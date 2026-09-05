from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from aicmo.mockup import render_pdf

if TYPE_CHECKING:
    import pytest


def test_render_pdf_without_playwright(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_playwright(_name: str) -> None:
        return None

    monkeypatch.setattr("aicmo.mockup.importlib.util.find_spec", missing_playwright)

    status = render_pdf(tmp_path / "page.html", tmp_path / "page.pdf")

    assert status.startswith("unavailable: install playwright")


def test_render_pdf_generates_valid_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def installed_playwright(_name: str) -> object:
        return object()

    monkeypatch.setattr("aicmo.mockup.importlib.util.find_spec", installed_playwright)

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        Path(argv[-1]).write_bytes(b"%PDF-1.4\ncontent")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("aicmo.mockup.subprocess.run", fake_run)
    output = tmp_path / "nested" / "page.pdf"

    assert render_pdf(tmp_path / "page.html", output) == "generated"
    assert output.read_bytes().startswith(b"%PDF")


def test_render_pdf_process_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def installed_playwright(_name: str) -> object:
        return object()

    def failed_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, "", "browser failed")

    monkeypatch.setattr("aicmo.mockup.importlib.util.find_spec", installed_playwright)
    monkeypatch.setattr("aicmo.mockup.subprocess.run", failed_run)

    assert render_pdf(tmp_path / "page.html", tmp_path / "page.pdf") == (
        "unavailable: playwright error: browser failed"
    )


def test_render_pdf_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def installed_playwright(_name: str) -> object:
        return object()

    monkeypatch.setattr("aicmo.mockup.importlib.util.find_spec", installed_playwright)

    def timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="playwright", timeout=1)

    monkeypatch.setattr("aicmo.mockup.subprocess.run", timeout)

    status = render_pdf(tmp_path / "page.html", tmp_path / "page.pdf")
    assert status.startswith("unavailable: playwright PDF timed out after ")
