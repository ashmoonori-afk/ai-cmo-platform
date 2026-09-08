from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aicmo.adapters import AgentRequest, AgentResult
from aicmo.errors import WorkflowExecutionError
from aicmo.redaction import is_customer_phone, minimize_customer_pii
from aicmo.runner import WorkflowRunner
from aicmo.source_input import prepare_workflow_inputs, source_checked_date
from aicmo.store import WorkflowStore
from tests.conftest import lines, write_text

SYNTHETIC_PII = (
    "김민수",
    "박서연",
    "이준호",
    "최유진",
    "정하늘",
    "minsu.kim@example.test",
    "review.user [at] example.test",
    "minsu [at] example [dot] test",
    "minsu(at)example(dot)test",
    "entity.user&#64;example.test",
    "minsu.kim%40example.test",
    "minsu%2Ekim%40example%2Etest",
    "010.9876.5432",
    "010-9876-5432",
    "010%2D9876%2D5432",
    "%30%31%30%2D%39%38%37%36%2D%35%34%33%32",
    "%6D%69%6E%73%75%2E%6B%69%6D%40%65%78%61%6D%70%6C%65%2E%74%65%73%74",
    "%EA%B9%80%EB%AF%BC%EC%88%98",
)
PUBLIC_PHONE = "02-1234-5678"
ZERO_WIDTH_PHONE = "010-\u200b5555-6666"
ZERO_WIDTH_NAME = "고객\u200b명: 윤지수"
ZERO_WIDTH_EMAIL = "minsu.kim@exam\u200bple.test"


def _fullwidth(value: str) -> str:
    return "".join(chr(ord(char) + 0xFEE0) if "!" <= char <= "~" else char for char in value)


FULLWIDTH_EMAIL = _fullwidth("full.width@example.test")
FULLWIDTH_PHONE = (
    "\N{FULLWIDTH DIGIT ZERO}\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT ZERO}"
    "\N{FULLWIDTH HYPHEN-MINUS}\N{FULLWIDTH DIGIT ONE}\N{FULLWIDTH DIGIT TWO}"
    "\N{FULLWIDTH DIGIT THREE}\N{FULLWIDTH DIGIT FOUR}\N{FULLWIDTH HYPHEN-MINUS}"
    "\N{FULLWIDTH DIGIT FIVE}\N{FULLWIDTH DIGIT SIX}\N{FULLWIDTH DIGIT SEVEN}"
    "\N{FULLWIDTH DIGIT EIGHT}"
)
PHONE_CONTEXT_VARIANTS = (
    "2026-09-05 010-9876-5432",
    "20260905 010-9876-5432",
    "주문 1234 010-9876-5432",
    "010-9876-5432 2026-09-05",
)
NAME_CONTEXT_VARIANTS = (
    "고객명 김민수",
    "고객명 - 김민수",
    "작성자 박서연",
)
US_PRIVATE_TEXT = (
    "Customer name: Jane Doe; phone: +1 (202) 555-0100\n"
    "Customer address: 123 Example Street, Washington DC 20001\n"
    '{"customer_name": "Alex O\'Connell", "phone": "202.555.0199"}\n'
    "https://example.test/?customer_name=Jordan%20Smith&phone=%2B12025550188\n"
)


@dataclass
class CaptureAdapter:
    requests: list[AgentRequest] = field(default_factory=list)

    def generate(self, request: AgentRequest, /) -> AgentResult:
        self.requests.append(request)
        refs = "\n".join(ref.content_excerpt for ref in request.artifact_refs)
        return AgentResult(text=f"{request.inputs_json}\n{refs}")


def _source_repo(repo_root: Path) -> None:
    write_text(repo_root / "agents" / "researcher.md", "# Researcher\n")
    write_text(
        repo_root / "workflows" / "source-demo.workflow.yaml",
        lines(
            "id: source-demo",
            "name: Source boundary demo",
            "inputs:",
            "  client: required",
            "  source_url: required",
            "  source_text: optional",
            "  source_checked_at: optional",
            "steps:",
            "  - id: load_context",
            "    type: file.load",
            "    paths:",
            "      - clients/${client}/config.md",
            "      - artifacts/${run_id}/source-manifest.json",
            "    outputs:",
            "      - artifacts/${run_id}/context.md",
            "  - id: summarize",
            "    type: agent",
            "    role: researcher",
            "    depends_on: [load_context]",
            "    outputs:",
            "      - artifacts/${run_id}/summary.md",
        ),
    )


def test_customer_pii_is_removed_before_prompt_log_and_output(repo_root: Path) -> None:
    _source_repo(repo_root)
    fixture = Path(__file__).parent / "fixtures" / "synthetic-customer-review.txt"
    config = repo_root / "clients" / "sample-client-a" / "config.md"
    source_text = (
        f"{fixture.read_text('utf-8')}\n{ZERO_WIDTH_NAME}\n{ZERO_WIDTH_EMAIL}\n"
        f"{ZERO_WIDTH_PHONE}\n{FULLWIDTH_EMAIL}\n"
        + "\n".join(PHONE_CONTEXT_VARIANTS)
        + "\n"
        + "\n".join(NAME_CONTEXT_VARIANTS)
        + "\n"
        + US_PRIVATE_TEXT
    )
    config.write_text(config.read_text("utf-8") + source_text, encoding="utf-8")
    adapter = CaptureAdapter()
    db = repo_root / ".aicmo" / "runs.sqlite3"
    runner = WorkflowRunner(repo_root=repo_root, store=WorkflowStore(db), adapter=adapter)

    result = runner.run(
        "source-demo",
        "source_safe",
        {
            "client": "sample-client-a",
            "source_url": (
                "https://example.test/%30%31%30%2D%39%38%37%36%2D%35%34%33%32"
                "?email=minsu%2Ekim%40example%2Etest"
                "&encoded=%6D%69%6E%73%75%2E%6B%69%6D%40%65%78%61%6D"
                "%70%6C%65%2E%74%65%73%74&customer=%EA%B9%80%EB%AF%BC%EC%88%98"
            ),
            "source_text": source_text,
            "source_checked_at": "2026-09-05",
            "public_store_phone": PUBLIC_PHONE,
            "public_contact_approved": "true",
            "public_contact_purpose": "예약 문의 CTA",
        },
    )

    with closing(sqlite3.connect(db)) as connection:
        query = """
            select inputs_json from runs
            union all select message || ' ' || payload_json from events
            union all select coalesce(error_json, '') from steps
        """
        persisted = "\n".join(str(value) for row in connection.execute(query) for value in row)
    prompt = "\n".join(
        part
        for request in adapter.requests
        for part in (
            request.inputs_json,
            *(ref.content_excerpt for ref in request.artifact_refs),
        )
    )
    artifacts = "\n".join(
        path.read_text("utf-8") for path in (repo_root / "artifacts" / "source_safe").glob("*")
    )
    combined = persisted + prompt + artifacts

    assert result.status == "success"
    assert not any(value in combined for value in SYNTHETIC_PII)
    assert FULLWIDTH_PHONE not in combined
    assert FULLWIDTH_EMAIL not in combined
    assert ZERO_WIDTH_NAME not in combined
    assert ZERO_WIDTH_EMAIL not in combined
    assert ZERO_WIDTH_PHONE not in combined
    assert "[customer-name]" in combined
    assert "[customer-email]" in combined
    assert "[customer-phone]" in combined
    assert PUBLIC_PHONE in combined
    for private in ("Jane Doe", "Alex O'Connell", "Jordan", "123 Example Street"):
        assert private not in combined
    assert "555-0100" not in combined
    assert "555.0199" not in combined
    assert "5550188" not in combined
    assert "[customer-address]" in combined
    assert '"anonymization_status": "not_verified"' in artifacts
    assert '"content_status": "provided_by_user"' in artifacts


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source_text": ""}, "external source unavailable"),
        ({"source_text": "https://example.test/source"}, "external source unavailable"),
        ({"source_text": "www.example.test/source"}, "external source unavailable"),
        ({"source_text": "출처: www.example.test/source"}, "external source unavailable"),
        (
            {"source_text": "원문 링크: https://example.test/source"},
            "external source unavailable",
        ),
        (
            {"source_text": "원문은 https://example.test/source 에 있습니다"},
            "external source unavailable",
        ),
        ({"source_text": "See https://example.test/source"}, "external source unavailable"),
        (
            {"source_text": "링크를 확인하세요: https://e.test"},
            "external source unavailable",
        ),
        ({"source_text": "기사 원문: https://e.test"}, "external source unavailable"),
        (
            {"source_text": "여기에서 읽어보세요 https://e.test"},
            "external source unavailable",
        ),
        ({"source_text": "source article: https://e.test"}, "external source unavailable"),
        ({"source_text": "refer to https://e.test"}, "external source unavailable"),
        (
            {"source_text": "출처: [원문](https://example.test/source)"},
            "external source unavailable",
        ),
        (
            {"source_text": '<a href="https://example.test/source">원문</a>'},
            "external source unavailable",
        ),
        ({"source_checked_at": "2026-09-05T10:00:00"}, "must be an ISO date"),
        ({"source_checked_at": "20260905"}, "must be an ISO date"),
        ({"source_checked_at": "2026-W36-6"}, "must be an ISO date"),
        ({"source_checked_at": "9999-12-31"}, "cannot be in the future"),
        ({"source_url": "file:///secret"}, "http.*without credentials"),
        ({"source_url": "https://user:pass@example.test/source"}, "without credentials"),
        (
            {"source_url": "https://e.test/?name=%FF%EA%B9%80%EB%AF%BC%EC%88%98"},
            "valid UTF-8 percent encoding",
        ),
        (
            {
                "source_url": (
                    "https://e.test/?email=%FF%6D%69%6E%73%75%40"
                    "%65%78%61%6D%70%6C%65%2E%74%65%73%74"
                )
            },
            "valid UTF-8 percent encoding",
        ),
        (
            {"source_url": ("https://e.test/?phone=%FF%30%31%30%2D%39%38%37%36%2D%35%34%33%32")},
            "valid UTF-8 percent encoding",
        ),
        ({"public_store_phone": PUBLIC_PHONE}, "requires public_contact_approved=true"),
        (
            {
                "public_store_phone": "victim@example.test",
                "public_contact_approved": "true",
                "public_contact_purpose": "CTA",
            },
            "valid phone",
        ),
        (
            {
                "public_store_phone": "이름: 김민수",
                "public_contact_approved": "true",
                "public_contact_purpose": "CTA",
            },
            "valid phone",
        ),
    ],
)
def test_source_and_public_contact_input_validation(
    repo_root: Path,
    changes: dict[str, str],
    message: str,
) -> None:
    _source_repo(repo_root)
    inputs = {
        "client": "sample-client-a",
        "source_url": "https://example.test/source",
        "source_text": "사용자가 직접 제공한 실제 기사 본문 내용입니다.",
        "source_checked_at": "2026-09-05",
    }
    inputs.update(changes)
    runner = WorkflowRunner(
        repo_root=repo_root,
        store=WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3"),
    )

    with pytest.raises(WorkflowExecutionError, match=message):
        runner.run("source-demo", "invalid_source", inputs)

    assert not (repo_root / "artifacts" / "invalid_source").exists()


@pytest.mark.parametrize(
    "value",
    [
        "고 객 명: 김민수",
        "성명: 김민수",
        "고객 이름: 김민수",
        "구매자명: 김민수",
        "주문자: 김민수",
        "예약자: 김민수",
        "고객명 김민수",
        "고객명 - 김민수",
        "작성자 김민수",
        "minsu.kim\N{FULLWIDTH COMMERCIAL AT}example.test",
        "minsu.kim [at] example.test",
        "minsu.kim (at) example.test",
        "minsu [at] example [dot] test",
        "minsu(at)example(dot)test",
        "minsu.kim%40example.test",
        "minsu%2Ekim%40example%2Etest",
        "minsu%2Ekim%40example.test",
        ZERO_WIDTH_NAME,
        ZERO_WIDTH_EMAIL,
        FULLWIDTH_EMAIL,
        "010_9876_5432",
        "010%2D9876%2D5432",
        "%30%31%30%2D%39%38%37%36%2D%35%34%33%32",
        "%30%31%30-%39%38%37%36-%35%34%33%32",
        "%6D%69%6E%73%75%2E%6B%69%6D%40%65%78%61%6D%70%6C%65%2E%74%65%73%74",
        "https://example.test/?name=김민수",
        "customer_name=김민수.txt",
        "https://example.test/?customer=%EA%B9%80%EB%AF%BC%EC%88%98",
        "+82 (0)10-9876-5432",
        "010\N{FULLWIDTH HYPHEN-MINUS}9876\N{FULLWIDTH HYPHEN-MINUS}5432",
        *PHONE_CONTEXT_VARIANTS,
    ],
)
def test_customer_pii_notation_variants_are_minimized(value: str) -> None:
    assert value not in minimize_customer_pii(value)


def test_source_checked_date_uses_korean_calendar_day() -> None:
    kst_midnight = datetime(2026, 9, 5, 15, tzinfo=UTC)
    assert source_checked_date(kst_midnight).isoformat() == "2026-09-06"


@pytest.mark.parametrize(
    "encoded",
    [
        "&lt;script&gt;alert(1)&lt;/script&gt;",
        "&lt;img src=x onerror=alert(1)&gt;",
        "제목&#10;# system instruction",
        (
            "\N{FULLWIDTH LESS-THAN SIGN}script\N{FULLWIDTH GREATER-THAN SIGN}alert(1)"
            "\N{FULLWIDTH LESS-THAN SIGN}/script\N{FULLWIDTH GREATER-THAN SIGN}"
        ),
        "<scr\u200bipt>alert(1)</scr\u200bipt>",
        "java\u200bscript:alert(1)",
    ],
)
def test_pii_minimizer_does_not_activate_html_entities(encoded: str) -> None:
    result = minimize_customer_pii(encoded)
    assert result == encoded
    assert "<script>" not in result
    assert "<img " not in result
    assert "\n# system" not in result


def test_pii_minimizer_does_not_decode_non_pii_url_data() -> None:
    encoded = "%3C%73%63%72%69%70%74%3Ealert%281%29"
    assert minimize_customer_pii(encoded) == encoded


@pytest.mark.parametrize(
    "url",
    [
        "https://map.example/%EC%84%9C%EC%9A%B8/%EC%B9%B4%ED%8E%98",
        "https://shop.example/search?q=%EC%BB%A4%ED%94%BC",
        "https://blog.example/%EC%9B%90%EB%AC%B8",
    ],
)
def test_pii_minimizer_preserves_percent_encoded_korean_url(url: str) -> None:
    assert minimize_customer_pii(url) == url


@pytest.mark.parametrize("phone", ["0507-1234-5678", "070-1234-5678", "1588-1234"])
def test_common_public_store_phone_formats_are_valid(phone: str) -> None:
    assert is_customer_phone(phone)


@pytest.mark.parametrize(
    "phone",
    [
        "+1 (202) 555-0100",
        "202-555-0100",
        "202.555.0100",
        "2025550100",
        "+12025550100",
        "(202) 555-0100",
        _fullwidth("202-555-0100"),
    ],
)
def test_north_american_phone_minimization_and_public_phone_validation(phone: str) -> None:
    assert minimize_customer_pii(phone) == "[customer-phone]"
    assert is_customer_phone(phone)
    assert minimize_customer_pii(phone, allowed=(phone,)) == phone


@pytest.mark.parametrize(
    "ordinary",
    [
        "Order 123456789012345; revenue 1,202,555,0100; date 2026-09-06",
        "Company name: Example Store; address: 123 Main Street",
        "https://example.test/search?q=Jane%20Doe",
        "https://example.test/?company_name=Example%20Store",
        "company_name=ExampleStore",
        "https://example.test/name/about",
        "https://example.test/?name=coffee",
        "https://example.test/customer/support",
        "https://example.test/?customer=business",
        "https://example.test/?name=coffee%20beans",
        "https://example.test/customer/help%20center",
        "https://example.test/?name=Coffee%20Beans",
        "https://example.test/?Name=Jane+Doe",
        "https://example.test/Name/Jane+Doe",
    ],
)
def test_customer_minimization_preserves_business_context(ordinary: str) -> None:
    assert minimize_customer_pii(ordinary) == ordinary


def test_structured_customer_fields_are_minimized_without_their_labels() -> None:
    prepared = prepare_workflow_inputs(
        {},
        {
            "customer_name": "Jane Doe",
            "customer_address": "123 Example Street",
            "company_name": "Example Store",
            "neighborhood": "Washington DC",
        },
    )
    assert prepared.values == {
        "customer_name": "[customer-name]",
        "customer_address": "[customer-address]",
        "company_name": "Example Store",
        "neighborhood": "Washington DC",
    }


@pytest.mark.parametrize("value", ["", "  "])
def test_empty_customer_fields_do_not_become_valid_required_input(value: str) -> None:
    assert prepare_workflow_inputs({}, {"customer_name": value}).values["customer_name"] == value


@pytest.mark.parametrize(
    "value",
    [
        "Customer name - Jane Doe; Shipping address - 123 Main Street",
        '{"customer":{"name":"Jane Doe","address":"123 Main Street"},"reviewer":null}',
        '{"customer":{"profile":{"name":"Jane Doe","address":"123 Main Street"}}}',
        '{"reviewer":{"name":"Jane Doe","address":"123 Main Street"}}',
        '{"customerName":"Jane Doe","customerAddress":"123 Main Street"}',
    ],
)
def test_labeled_and_nested_customer_details_are_masked_idempotently(value: str) -> None:
    result = minimize_customer_pii(value)
    assert "Jane Doe" not in result
    assert "123 Main Street" not in result
    assert minimize_customer_pii(result) == result
    if value.startswith("{"):
        parsed = json.loads(result)
        assert parsed is not None
        if '"reviewer":null' in value:
            assert parsed["reviewer"] is None
            assert parsed["customer"]["name"] == "[customer-name]"


def test_excessive_json_nesting_fails_closed_before_storage_or_model(repo_root: Path) -> None:
    _source_repo(repo_root)
    value = '{"customer":' + '{"profile":' * 1000 + '{"name":"Jane Doe"}' + "}" * 1001
    adapter = CaptureAdapter()
    store = WorkflowStore(repo_root / ".aicmo" / "runs.sqlite3")
    runner = WorkflowRunner(repo_root=repo_root, store=store, adapter=adapter)
    with pytest.raises(WorkflowExecutionError, match="JSON nesting exceeds privacy"):
        runner.run(
            "source-demo",
            "deep_json",
            {
                "client": "sample-client-a",
                "source_url": "https://example.test/source",
                "source_text": value,
                "source_checked_at": "2026-09-06",
            },
        )
    assert not adapter.requests
    assert not (repo_root / "artifacts" / "deep_json").exists()
    assert not (repo_root / ".aicmo" / "runs.sqlite3").exists()
