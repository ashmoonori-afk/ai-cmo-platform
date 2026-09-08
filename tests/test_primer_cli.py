from pathlib import Path

import pytest
from typer.testing import CliRunner

from aicmo.cli import app
from aicmo.onboarding import load_answers, scaffold_client

_PAYLOAD = (
    '{"client":"demo","company_name":"Demo","offer":"Offer",'
    '"audience":"Audience","problem":"Problem","differentiator":"Diff",'
    '"channel":"Web","proof":"Proof","cta":"Buy"}'
)


def test_primer_writes_html(tmp_path: Path) -> None:
    source = tmp_path / "answers.json"
    source.write_text(_PAYLOAD, encoding="utf-8")
    out = tmp_path / "primer.html"

    result = CliRunner().invoke(app, ["primer", "--from", str(source), "--out", str(out)])

    assert result.exit_code == 0, result.stdout
    assert out.exists()
    assert "primer:" in result.stdout
    assert out.name in result.stdout


def test_scaffold_default_generates_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(_PAYLOAD, encoding="utf-8")

    def fake_render(_html_path: Path, pdf_path: Path) -> str:
        pdf_path.write_bytes(b"%PDF")
        return "generated"

    monkeypatch.setattr("aicmo.mockup.render_pdf", fake_render)
    result = scaffold_client(tmp_path, load_answers(answers_path))
    html = tmp_path / "clients" / "demo" / "primer-report.html"
    pdf = tmp_path / "clients" / "demo" / "primer-report.pdf"

    assert html in result.created
    assert pdf in result.created
    assert result.pdf_status == "generated"
    assert pdf.read_bytes() == b"%PDF"


def test_onboard_no_pdf(tmp_path: Path) -> None:
    answers = tmp_path / "answers.json"
    answers.write_text(_PAYLOAD, encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "onboard", "--client", "no-pdf", "--from", str(answers),
            "--repo", str(tmp_path), "--no-pdf",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "clients" / "no-pdf" / "primer-report.html").exists()
    assert not (tmp_path / "clients" / "no-pdf" / "primer-report.pdf").exists()
    assert "pdf: disabled" in result.stdout


def test_onboard_default_generates_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = tmp_path / "answers.json"
    answers.write_text(_PAYLOAD, encoding="utf-8")

    def fake_render(_html_path: Path, pdf_path: Path) -> str:
        pdf_path.write_bytes(b"%PDF")
        return "generated"

    monkeypatch.setattr("aicmo.mockup.render_pdf", fake_render)
    result = CliRunner().invoke(
        app,
        ["onboard", "--client", "with-pdf", "--from", str(answers), "--repo", str(tmp_path)],
    )

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "clients" / "with-pdf" / "primer-report.pdf").exists()
    assert "pdf: generated" in result.stdout


def test_primer_pdf_option_uses_renderer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "answers.json"
    source.write_text(_PAYLOAD, encoding="utf-8")
    out = tmp_path / "primer.html"
    pdf = tmp_path / "primer.pdf"
    calls: list[tuple[Path, Path]] = []

    def fake_render(_html_path: Path, pdf_path: Path) -> str:
        calls.append((_html_path, pdf_path))
        Path(pdf_path).write_bytes(b"%PDF")
        return "generated"

    monkeypatch.setattr("aicmo.cli.tool_cmds.render_pdf", fake_render, raising=False)
    result = CliRunner().invoke(
        app, ["primer", "--from", str(source), "--out", str(out), "--pdf", str(pdf)]
    )

    assert result.exit_code == 0, result.stdout
    assert calls == [(out, pdf)]
    assert "pdf: generated" in result.stdout
