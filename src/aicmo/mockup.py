# pyright: reportImportCycles=false

from __future__ import annotations

import html
import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aicmo.onboarding import OnboardingAnswers

_ACCENT = "#0F6E56"
_SCREENSHOT_TIMEOUT = 120
_PDF_TIMEOUT = 120
_DETAIL_LIMIT = 300

# Run in a child process so this module never statically imports the optional `playwright`
# dependency. argv: <html-file-uri> <png-output-path>.
_SCREENSHOT_SCRIPT = """
import sys
from playwright.sync_api import sync_playwright

uri, out = sys.argv[1], sys.argv[2]
with sync_playwright() as runner:
    browser = runner.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(uri)
    page.screenshot(path=out, full_page=True)
    browser.close()
"""

_PDF_SCRIPT = """
import sys
from playwright.sync_api import sync_playwright

uri, out = sys.argv[1], sys.argv[2]
with sync_playwright() as runner:
    browser = runner.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(uri, wait_until="networkidle")
    page.pdf(path=out, format="A4", print_background=True)
    browser.close()
"""


@dataclass(frozen=True, slots=True)
class LandingBrief:
    company: str
    offer: str
    audience: str
    problem: str
    differentiator: str
    proof: str
    cta: str
    accent: str = _ACCENT


def brief_from_answers(answers: OnboardingAnswers) -> LandingBrief:
    return LandingBrief(
        company=answers.company_name,
        offer=answers.offer,
        audience=answers.audience,
        problem=answers.problem,
        differentiator=answers.differentiator,
        proof=answers.proof,
        cta=answers.cta,
    )


def render_landing_mockup(brief: LandingBrief) -> str:
    """Render a self-contained, responsive HTML landing-page mockup from a brand brief.

    All brief fields are HTML-escaped, so untrusted brand copy cannot inject markup.
    The output is both a viewable 시안 and a clickable minimum prototype (open in a browser).
    """
    company = html.escape(brief.company)
    offer = html.escape(brief.offer)
    audience = html.escape(brief.audience)
    problem = html.escape(brief.problem)
    differentiator = html.escape(brief.differentiator)
    proof = html.escape(brief.proof)
    cta = html.escape(brief.cta)
    accent = html.escape(brief.accent)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{company} — {offer}</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>.accent{{background:{accent}}} .accent-text{{color:{accent}}}</style>
</head>
<body class="bg-white text-slate-800">
<header class="max-w-3xl mx-auto px-6 pt-16 pb-12 text-center">
  <p class="text-sm tracking-wide accent-text font-medium">{company}</p>
  <h1 class="mt-4 text-4xl md:text-5xl font-bold leading-tight">{offer}</h1>
  <p class="mt-4 text-lg text-slate-500">{audience}</p>
  <a href="#cta"
     class="accent inline-block mt-8 px-8 py-3 rounded-lg text-white font-medium">{cta}</a>
</header>
<section class="max-w-3xl mx-auto px-6 py-12 border-t border-slate-100">
  <h2 class="text-2xl font-bold">이런 점이 불편하셨죠</h2>
  <p class="mt-3 text-lg text-slate-600">{problem}</p>
</section>
<section class="max-w-3xl mx-auto px-6 py-12 border-t border-slate-100">
  <h2 class="text-2xl font-bold">그래서 이렇게 다릅니다</h2>
  <p class="mt-3 text-lg text-slate-600">{differentiator}</p>
</section>
<section class="max-w-3xl mx-auto px-6 py-12 border-t border-slate-100">
  <h2 class="text-2xl font-bold">믿을 수 있는 이유</h2>
  <p class="mt-3 text-lg text-slate-600">{proof}</p>
</section>
<section id="cta" class="accent text-white text-center px-6 py-16">
  <h2 class="text-3xl font-bold">{offer}</h2>
  <a href="#"
     class="inline-block mt-6 px-8 py-3 rounded-lg bg-white accent-text font-semibold">{cta}</a>
</section>
<footer class="max-w-3xl mx-auto px-6 py-10 text-center text-sm text-slate-400">
  <p>{company} · AI CMO 자동 생성 시안 (검토 필요)</p>
</footer>
</body>
</html>
"""


def _run_browser_script(
    script: str, html_path: Path, output_path: Path, *, timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed inline script via sys.executable, argv-only, no shell
        [sys.executable, "-c", script, html_path.resolve().as_uri(), str(output_path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def render_pdf(html_path: Path, pdf_path: Path) -> str:
    """Render the HTML mockup to a validated PDF if Playwright is available."""
    if importlib.util.find_spec("playwright") is None:
        return "unavailable: install playwright"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _run_browser_script(_PDF_SCRIPT, html_path, pdf_path, timeout=_PDF_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"unavailable: playwright PDF timed out after {_PDF_TIMEOUT}s"
    if result.returncode != 0:
        return f"unavailable: playwright error: {result.stderr.strip()[:_DETAIL_LIMIT]}"
    try:
        valid_pdf = pdf_path.stat().st_size > 0 and pdf_path.read_bytes().startswith(b"%PDF")
    except OSError:
        valid_pdf = False
    return "generated" if valid_pdf else "unavailable: playwright produced no valid PDF"


def render_png(html_path: Path, png_path: Path) -> str:
    """Screenshot the HTML mockup to a PNG if Playwright is installed; else say so.

    Returns 'generated' on success, or an 'unavailable: ...' status — never crashes.
    """
    if importlib.util.find_spec("playwright") is None:
        return "unavailable: install playwright (uv add playwright && playwright install chromium)"
    png_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _run_browser_script(
            _SCREENSHOT_SCRIPT, html_path, png_path, timeout=_SCREENSHOT_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return f"unavailable: playwright screenshot timed out after {_SCREENSHOT_TIMEOUT}s"
    if result.returncode != 0:
        return f"unavailable: playwright error: {result.stderr.strip()[:_DETAIL_LIMIT]}"
    return "generated"
