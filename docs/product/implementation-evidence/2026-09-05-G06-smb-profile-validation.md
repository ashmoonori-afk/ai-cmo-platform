# G06 소상공인 프로필·입력 검증 통일 증거

## 한 장 요약

웹과 CLI 온보딩이 같은 검증 함수를 사용한다. 가게의 동네, 업종, 대표 상품 가격,
영업시간, 목적, 채널, 주당 마케팅 여력과 사실 확인 상태는 Markdown `config.md`에
`aicmo.smb-profile.v1`로 저장된다. 신규 매장은 검증된 고객 사례가 없어도 `후기없음`으로
시작하며, 생성되는 카피와 가격 규칙은 확인되지 않은 후기·가격을 만들지 말라고 명시한다.

## 입력 스키마

| 필드 | 기본값·허용 상태 | 검증 |
|---|---|---|
| 회사명·상품·고객·문제·차별점·채널·CTA | 필수 문자열 | 공백 차단 |
| 고객 근거 | `후기없음` | 미입력 허용, 허구 후기 생성 금지 |
| 동네·업종·가격·영업시간·목적·주당 여력 | `모름` 또는 `해당없음` | 음수 가격 차단 |
| 사실 확인 상태 | `confirmed`, `unknown`, `not_applicable` | 열거값 밖 입력 차단 |
| 캠페인 시작일·종료일 | 선택 ISO 날짜 | 잘못된 날짜와 기간 역전 차단 |
| 채널 | 지원 채널명, `모름`, `해당없음` | 임의 채널명 차단 |

`load_answers()`와 `answers_from_form()`은 `validate_answers()`로 합류한다. 웹은 브라우저의
필수 입력·날짜 입력을 사용하고 서버에서도 같은 규칙으로 재검증하여 오류를 HTTP 400으로
돌려준다.

## 기존 고객 마이그레이션과 파일

- 기존 고객의 Markdown `config.md`는 계속 실행기의 원천이다.
- `aicmo onboard --force`는 기존 파일마다 복구용 백업을 만든 다음 v1 프로필로 교체한다.
- 교체 중 하나라도 실패하면 이미 바뀐 파일을 원래 바이트로 되돌린다.
- 기존 knowledge-base 파일은 갱신하지 않는다.
- 신규 고객은 `config.md`, `brand-guidelines.md`, `copy-patterns.md`, `pricing-rules.md`와
  primer를 함께 받는다.

## 검증 결과

| 명령 | 결과 |
|---|---|
| `uv run pytest tests/test_onboarding.py tests/test_web.py tests/test_primer.py tests/test_primer_cli.py tests/test_mockup.py -q` | PASS — reviewer 독립 63 passed in 7.76s |
| `uv run pytest -q` | PASS — reviewer 독립 269 passed in 87.51s |
| `uv run ruff check .` | PASS |
| `uv run basedpyright` | PASS — 0 errors, 0 warnings |
| `git diff --check` | PASS |

## Reviewer 판정

**PASS** — 1차 검토에서 음수 부호 위치·채널 부분문자열·시각이 붙은 날짜 입력 우회를
발견해 전체 일치 채널 문법과 ISO 날짜 전용 파싱으로 수정했다. 2차 검토에서 통화기호가
붙은 음수와 정상 가격 범위의 충돌을 발견해, 숫자·`원` 뒤 범위 구분자는 허용하면서
`-₩1000`, `KRW -1000`, `price -1000`은 차단하도록 보완했다. 최종 검증에서 신규 매장의
`후기없음`, 웹·CLI 공통 검증, 국내 채널 별칭, 기존 config 백업·복구, KB 보존을 재현했다.

## 다음 단계

1. G06을 원자적 커밋으로 고정한다.
2. G07에서 제공 원문과 URL만 있는 출처를 구분한다.
3. 모델 입력 전 고객 PII 최소화와 국내 채널 규격을 검증한다.
