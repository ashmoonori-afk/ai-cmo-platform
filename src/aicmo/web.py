from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from aicmo.mockup import brief_from_answers, render_landing_mockup
from aicmo.onboarding import OnboardingAnswers

_MAX_BODY = 64 * 1024

_QUESTIONS = (
    ("company_name", "회사·브랜드 이름", "예: 엄마의 양초"),
    ("offer", "1) 무엇을 파나요? 한 문장으로", "예: 작은 집을 위한 콩 왁스 향초"),
    ("audience", "2) 누가 살까요? 가장 살 것 같은 사람", "예: 원룸에 사는 사람"),
    ("problem", "3) 그 사람이 겪는 가장 큰 불편은?", "예: 싼 향초는 그을음이 난다"),
    ("differentiator", "4) 왜 당신을 골라야 하나요?", "예: 저그을음 콩 왁스"),
    ("channel", "5) 그 사람들은 어디서 시간을 보내나요?", "예: 인스타그램, 스마트스토어"),
    ("proof", "6) 결과를 본 고객 사례가 있나요?", "예: 200명 재구매, 평점 4.9"),
    ("cta", "7) 처음 온 사람이 했으면 하는 행동은?", "예: 첫 향초 주문하기"),
)


def _field_html(name: str, label: str, placeholder: str) -> str:
    return (
        f'<label class="block mt-5"><span class="font-medium">{html.escape(label)}</span>'
        f'<input name="{name}" placeholder="{html.escape(placeholder)}" '
        'class="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2"></label>'
    )


def render_form_page() -> str:
    fields = "\n".join(
        _field_html(name, label, placeholder) for name, label, placeholder in _QUESTIONS
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI CMO — 내 브랜드 시안 만들기</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-50 text-slate-800">
<main class="max-w-xl mx-auto px-6 py-12">
  <h1 class="text-3xl font-bold">내 브랜드 시안 만들기</h1>
  <p class="mt-2 text-slate-500">쉬운 질문에 답하면 랜딩페이지 시안을 만들어 드려요.</p>
  <form method="post" action="/generate">
{fields}
    <button type="submit"
      class="mt-8 w-full bg-emerald-700 text-white rounded-lg py-3 font-medium">
      시안 만들기</button>
  </form>
</main>
</body>
</html>
"""


def _first(form: dict[str, list[str]], key: str, default: str = "") -> str:
    values = form.get(key)
    return values[0] if values else default


def answers_from_form(form: dict[str, list[str]]) -> OnboardingAnswers:
    return OnboardingAnswers(
        client="web",
        company_name=_first(form, "company_name", "브랜드"),
        offer=_first(form, "offer"),
        audience=_first(form, "audience"),
        problem=_first(form, "problem"),
        differentiator=_first(form, "differentiator"),
        channel=_first(form, "channel"),
        proof=_first(form, "proof"),
        cta=_first(form, "cta", "주문하기"),
    )


def generate_page(form: dict[str, list[str]]) -> str:
    return render_landing_mockup(brief_from_answers(answers_from_form(form)))


class RequestHandler(BaseHTTPRequestHandler):
    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send_html(render_form_page())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/generate":
            self.send_error(404)
            return
        try:
            declared = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            declared = 0
        length = max(0, min(declared, _MAX_BODY))
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        self._send_html(generate_page(form))


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
