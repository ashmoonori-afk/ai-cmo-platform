# G07 근거·개인정보·채널 규격 입력 경계 증거

## 한 장 요약

`content-engine`은 URL만으로 원문을 읽었다고 주장하지 않는다. 사용자가 원문과 확인일을
함께 제공해야 실행하며, URL·확인일·익명화된 본문의 SHA-256을
`aicmo.source-manifest.v1` 파일에 기록한다. 고객 리뷰의 이름·전화·이메일은 SQLite 기록,
모델 요청, 중간 파일과 결과 파일에 들어가기 전에 제거한다. 공개 매장 전화는 별도 입력으로
분리하고 승인 값과 사용 목적이 모두 있을 때만 유지한다.

## 입력·출처 계약

| 상태 | 처리 |
|---|---|
| `source_url`만 제공 | `external source unavailable`로 실행 전 중단, artifact 미생성 |
| 원문 없음·공백 | 실행 전 중단 |
| URL이 포함된 안내 줄뿐이거나 URL 없는 실질 문장이 8자 미만 | 실행 전 중단 |
| `file:` URL·자격증명 포함 URL·잘못된 URL | 실행 전 중단 |
| 잘못된 percent/UTF-8 URL·잘못된 확인일·64 KiB 초과 원문 | 실행 전 중단 |
| 원문+URL+`YYYY-MM-DD` 확인일 | KST 운영일 검증·익명화 후 실행, `source-manifest.json` 생성 |
| 공개 전화만 입력 | 승인 없음으로 중단 |
| 공개 전화+승인+목적 | 명시한 전화만 모델 입력·결과에서 유지 |

Inbox 파일은 URL 줄과 사용자가 붙인 원문을 구분한다. URL만 있는 기존 파일은 실패 항목으로
남겨 재시도하며, 원문이 있는 파일은 처리 시점의 KST 날짜를 확인일로 기록한다. 플랫폼은 외부 URL을
가져오지 않는다. 모델 프롬프트에도 입력과 상위 artifact는 증거일 뿐 지시가 아니라고 명시한다.

## 개인정보 합성 검사

`tests/fixtures/synthetic-customer-review.txt`에는 실제 고객이 아닌 합성 이름·이메일·전화가
들어 있다. `tests/test_source_boundary.py`는 이 값이 다음 위치에 남지 않는지 한 번에 검사한다.

- `runs.inputs_json`, event message/payload, step error
- adapter가 받은 `inputs_json`과 artifact excerpt
- `context.md`, `summary.md`, `source-manifest.json`

같은 검사에서 승인 용도가 있는 공개 매장 전화만 유지되는 것도 확인한다. 일반·전각·zero-width·
`[at]`/`[dot]`·raw/mixed/full percent-encoded 표기를 함께 검사한다. 명시적 고객 이름 key는
마스킹하지만 서울·카페·커피 같은 일반 percent-encoded 한국어 URL은 원형을 보존한다.

## Reviewer 발견·수정 이력

1. 전화 후보가 주변 날짜·주문번호까지 삼키던 문제를 국내 번호 구조 기반 후보식으로 수정했다.
2. ingest URL·파일명·archive·오류·dry-run 출력에 고객 PII 공통 안전 표시를 적용했다.
3. 확인일을 KST 운영일로 통일하고 basic/week date를 거부하며 workflow 필수 입력과 맞췄다.
4. URL 안내문을 원문으로 오인하던 문제를 URL 포함 줄 제외와 최소 실질 본문 길이로 차단했다.
5. raw/mixed/full percent-encoded PII와 invalid UTF-8을 차단하면서 일반 한국어 URL은 보존했다.
6. 플레이북의 WebFetch·URL-only 설명을 실제 no-fetch 계약으로 교체했다.

## 국내 채널 규격 근거

`docs/product/korean-channel-specs.md`는 2026-09-05에 공식 문서를 확인해 메시지 유형과 운영
규칙을 연결했다. 네이버 스마트플레이스의 업체 정보·검토 기준은
[네이버 사업주 고객센터](https://help.naver.com/service/30026/contents/20366?lang=ko&osType=COMMONOS),
카카오톡 채널의 소식·메시지·1:1 채팅과 광고 표시는
[카카오비즈니스](https://business.kakao.com/info/kakaotalkchannel/)와
[채널 이용가이드](https://business.kakao.com/guide.html), 인스타그램 게시물·릴스와 9:16
권장은 [Instagram 도움말](https://www.facebook.com/help/instagram/439971288310029)과
[Meta for Business](https://www.facebook.com/business/ads/facebook-instagram-reels-ads),
네이버 블로그 검색 API 범위는
[NAVER Developers](https://developers.naver.com/docs/serviceapi/search/blog/blog.md)를 사용했다.

## 검증 결과

| 명령 | 결과 |
|---|---|
| `uv run pytest -q tests/test_source_boundary.py tests/test_ingest.py tests/test_privacy.py tests/test_artifact_handoff.py tests/test_launch_pack_spec.py tests/test_llm_integration.py` | 독립 PASS — 112 passed in 25.34s |
| `uv run pytest -q` | 독립 PASS — 346 passed in 107.42s |
| `uv run ruff check .` | PASS |
| `uv run basedpyright` | PASS — 0 errors, 0 warnings |
| `git diff --check` | PASS |

## Reviewer 판정

**PASS.** reviewer가 URL-only 8종, KST 날짜와 strict date, raw/mixed/full encoded PII,
invalid UTF-8 거부, 일반 한국어 URL 보존, prompt의 evidence-only 문구, manifest의 byte 수와
SHA-256을 독립 재현했다. 구현 blocker는 남지 않았다.

## 다음 단계

1. G07 변경을 원자적 커밋으로 고정한다.
2. G01–G07 draft PR에서 각 Goal 증거와 전체 회귀 결과를 연결한다.
3. G02 운영자 결정을 받기 전 유료 판매·외부 발행을 보류한다.
