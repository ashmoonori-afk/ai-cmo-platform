from __future__ import annotations

import socket
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest

from aicmo.errors import OnboardingError
from aicmo.web import RequestHandler, answers_from_form, generate_page, render_form_page

FIELDS = (
    "company_name",
    "offer",
    "audience",
    "problem",
    "differentiator",
    "channel",
    "proof",
    "cta",
    "neighborhood",
    "business_type",
    "price",
    "business_hours",
    "objective",
    "weekly_capacity",
    "campaign_start",
    "campaign_end",
)


def _form(**overrides: str) -> dict[str, list[str]]:
    base = {
        "company_name": ["brand"],
        "offer": ["offer"],
        "audience": ["audience"],
        "problem": ["problem"],
        "differentiator": ["differentiator"],
        "channel": ["인스타그램"],
        "proof": ["후기없음"],
        "cta": ["order"],
    }
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
    assert answers.neighborhood == "모름"


def test_web_and_cli_share_profile_validation() -> None:
    with pytest.raises(OnboardingError, match="price cannot be negative"):
        answers_from_form(_form(price="-1원"))

    with pytest.raises(OnboardingError, match="missing required answers: offer"):
        answers_from_form(_form(offer=""))


def test_web_defaults_missing_proof_without_inventing_a_review() -> None:
    form = _form()
    form.pop("proof")

    assert answers_from_form(form).proof == "후기없음"


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
        "엄마의 양초",
        "콩 왁스 향초",
        "그을음 문제",
        "저그을음 콩 왁스",
        "200명 재구매",
        "주문하기",
    )
    for value in expected:
        assert value in page


def test_generate_page_escapes_user_content() -> None:
    page = generate_page(_form(offer="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def _request(request: bytes) -> bytes:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            sock.sendall(request)
            sock.shutdown(socket.SHUT_WR)
            chunks: list[bytes] = []
            while chunk := sock.recv(65536):
                chunks.append(chunk)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return b"".join(chunks)


@pytest.mark.parametrize(
    ("headers", "body", "status"),
    [
        (b"Content-Length: \xb2\r\n", b"", 400),
        (b"Content-Length: -1\r\n", b"", 400),
        (b"", b"", 411),
        (b"Content-Length: 1\r\nContent-Length: 2\r\n", b"x", 400),
        (b"Transfer-Encoding: chunked\r\n", b"0\r\n\r\n", 400),
        (b"Content-Length: 65537\r\n", b"", 413),
        (b"Content-Length: 2\r\n", b"x", 400),
        (b"Content-Length: 1\r\n", b"\xff", 400),
    ],
)
def test_invalid_request_body_is_rejected(headers: bytes, body: bytes, status: int) -> None:
    response = _request(
        b"POST /generate HTTP/1.1\r\nHost: localhost\r\n"
        b"Content-Type: application/x-www-form-urlencoded\r\n" + headers + b"\r\n" + body,
    )
    assert response.startswith(f"HTTP/1.0 {status} ".encode())


def test_invalid_form_preserves_escaped_answers_for_correction() -> None:
    form = _form(company_name='A "brand" <script>', price="-1원")
    body = urlencode(form, doseq=True).encode()
    response = _request(
        b"POST /generate HTTP/1.1\r\nHost: localhost\r\n"
        b"Content-Type: application/x-www-form-urlencoded\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body,
    ).decode()
    assert response.startswith("HTTP/1.0 400 ")
    assert 'name="company_name" value="A &quot;brand&quot; &lt;script&gt;"' in response
    assert 'name="price" value="-1원"' in response
    assert 'role="alert"' in response
    assert 'action="/generate"' in response
    assert "Cache-Control: no-store" in response


def test_valid_http_form_still_generates() -> None:
    body = urlencode(_form(), doseq=True).encode()
    response = _request(
        b"POST /generate HTTP/1.1\r\nHost: localhost\r\n"
        b"Content-Type: application/x-www-form-urlencoded\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body,
    )
    assert response.startswith(b"HTTP/1.0 200 ")
    assert b"<!DOCTYPE html>" in response
