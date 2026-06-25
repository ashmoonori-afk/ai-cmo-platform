from __future__ import annotations

import socket
import threading
from http.server import ThreadingHTTPServer

from aicmo.web import RequestHandler, answers_from_form, generate_page, render_form_page

FIELDS = (
    "company_name", "offer", "audience", "problem",
    "differentiator", "channel", "proof", "cta",
)


def _form(**overrides: str) -> dict[str, list[str]]:
    base = {name: [name] for name in FIELDS}
    base.update({key: [value] for key, value in overrides.items()})
    return base


def test_form_page_has_questions_and_inputs() -> None:
    page = render_form_page()
    assert '<form method="post" action="/generate"' in page
    for name in FIELDS:
        assert f'name="{name}"' in page, f"form is missing input: {name}"
    assert "무엇을 파나요" in page
    assert "처음 온 사람" in page


def test_answers_from_form_maps_fields() -> None:
    answers = answers_from_form(
        _form(company_name="엄마의 양초", offer="콩 왁스 향초", cta="주문하기"),
    )
    assert answers.company_name == "엄마의 양초"
    assert answers.offer == "콩 왁스 향초"
    assert answers.cta == "주문하기"


def test_generate_page_is_mockup_with_brand() -> None:
    page = generate_page(
        _form(
            company_name="엄마의 양초",
            offer="콩 왁스 향초",
            problem="그을음 문제",
            differentiator="저그을음 콩 왁스",
            proof="200명 재구매, 평점 4.9",
            cta="주문하기",
        ),
    )
    assert page.startswith("<!DOCTYPE html>")
    assert "tailwindcss" in page
    expected = (
        "엄마의 양초", "콩 왁스 향초", "그을음 문제",
        "저그을음 콩 왁스", "200명 재구매", "주문하기",
    )
    for value in expected:
        assert value in page


def test_generate_page_escapes_user_content() -> None:
    page = generate_page(_form(offer="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_malformed_content_length_returns_clean_response() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Content-Length is a non-ASCII digit: str.isdigit() is True but int() rejects it.
    request = (
        b"POST /generate HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: \xb2\r\n"
        b"Connection: close\r\n\r\n"
    )
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(request)
            response = sock.recv(1024)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.startswith(b"HTTP/"), "server crashed instead of returning a clean response"
