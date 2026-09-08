# 입력 최소화·과거 실행 재개·웹 입력 복구

## 한 장 요약

2026-09-06에는 인식 가능한 미국 고객 정보의 누락, 과거 입력 재개 경계, 과대 HTTP 입력 및 오류 시 폼 소실을 수정했다. 기획 원본은 로컬에 보존하고 Git 추적에서 제외한다. G02와 전체 실사용 제품 목표는 아직 완료되지 않았다. 다음 구현은 국내 가게용 실행팩과 승인된 실제 납품 파일 연결이다.

## 수정과 검증 범위

| 문제 | 변경 | 증거 |
|---|---|---|
| 미국 번호·명시된 이름·주소가 유지됨 | redaction 공통 함수에 NANP 표기, 이름/주소 라벨, 고객 JSON 문맥·camelCase 키 처리. 입력·참조·모델 결과·로그가 같은 함수를 사용 | tests/test_source_boundary.py 및 기존 privacy 검사 |
| required 고객 필드의 빈 값이 마스킹 문자열로 바뀜 | 빈/공백은 유지해 기존 필수 입력 검증이 작동 | 빈 문자열·공백 회귀 |
| 일반 URL을 이름으로 오인 | 일반 영문 name/customer URL은 보존하고 명시된 customer_name/reviewer_name은 마스킹 | 일반/percent URL의 원형 보존 검사 |
| 중첩 고객 객체 누락·JSON null 훼손 | JSON 파서로 타입을 보존하고 고객 문맥을 하위 dict/list로 전달 | 중첩 customer/reviewer·camelCase·null 및 납품 manifest 검사 |
| 지나치게 깊은 JSON의 재귀 예외 | 파싱·순회·비교·직렬화의 재귀 오류를 고정 사유의 WorkflowExecutionError로 전환 | 약 12 KiB/1000단계 입력에서 adapter·DB·아티팩트 미생성 |
| 과거 run의 원본 입력을 재전송 | 현재 최소화 결과가 저장 입력과 다르면 실행 전에 새 run 안내. 정상 최소화 입력은 재개 가능 | tests/test_resume_spec_drift.py의 old inputs→adapter 미호출/저장소 불변 및 정상 재개 |
| 큰 HTTP 본문 일부가 처리될 수 있음 | 64 KiB 상한 초과 413, 잘못된 framing·길이·UTF-8 400, 누락 길이 411, 다른 media type 415 | tests/test_web.py 실제 loopback HTTP 검사 |
| 오류 시 입력이 사라짐 | escape한 입력값을 폼에 복원하고 alert 표시. no-store/nosniff 응답 | 실제 HTTP 및 Chromium 390px 오류→수정→정상 생성 |

## 지원 한계

이 기능은 법적 익명화나 자유 서술의 모든 개인정보 제거를 보장하지 않는다. 인명으로 해석할 수 있는 일반 영문 URL의 name/customer 값은 상품명과 구별할 수 없으므로 자동 인명 추정을 하지 않는다. 그런 URL 및 미지원 표기의 잔여 정보 검토, 과거 저장소의 실제 삭제, 고객 동의·국외 이전·보관 정책은 별도 운영 과제다.

source manifest의 기존 `pii_minimized`는 호환성을 위해 유지하며 검사 방법과 `anonymization_status=not_verified`를 추가했다. 기존 SQLite·아티팩트 원문을 소급 삭제하지 않으며, 새 규칙이 바꾸는 과거 입력을 조용히 전송하지 않는다. 스텁은 여전히 데모이고 웹은 로컬 시안 도구다. 이 변경으로 유료 서비스·결제·외부 게시가 활성화되지 않는다.

## 검토·검사 기록

독립 reviewer의 초기 검토에서 빈 필드, generic URL 오탐, 하이픈 라벨, 중첩 JSON 및 고객 문맥 전파 문제를 발견해 해당 경로를 수정했다. 전체 회귀에서는 `reviewer: null` JSON 손상을 발견해 타입 보존을 추가했다. 마지막 재귀 예외까지 수정한 뒤 reviewer가 이전 실패 사례를 재검증했다. **최종 독립 판정 PASS, 필수 코드 수정 없음**이다. 이는 이번 입력·복구 수정 범위의 판정이다.

- 수정 전 미국 개인정보 신규 표적 9개 실패로 누락 확인.
- 구현 중 개인정보·재개·납품·웹 표적 151개 통과. 최종 검사 수치와 구분한다.
- 최종 `.venv/Scripts/python.exe -m pytest -q`: **390 passed in 140.42s**.
- 최종 Ruff PASS, basedpyright **0 errors, 0 warnings, 0 notes**, `git diff --check` PASS.
- 독립 reviewer의 privacy·ingest·source·resume·web 검사: **155 passed in 20.00s**. 독립 Ruff/basedpyright/diff 검사도 PASS.
- 모바일 실제 Chromium 390px: 오류 400→입력 유지→가격 수정→시안 200 통과. 스크린샷은 로컬 `artifacts/real-use-review/web-error-mobile.png`, `web-success-mobile.png`에 보관한다. 실제 고객 조사로 세지 않는다.
- 계획·결정·연구 파일은 존재/본문 읽기/`git check-ignore`/`git ls-files`로 로컬 보존과 추적 제외를 확인했다. 기존 Git 커밋 이력은 유지한다.

## 다음 단계

1. 개발 담당은 검증된 입력·복구 변경을 원자적 커밋으로 남기고 PR의 원격 SHA를 확인한다.
2. 개발·제품 담당은 국내 실행팩과 실제 납품 파일을 기존 runner에 연결한다.
3. 운영·검토 담당은 G02를 OPEN으로 유지하며 법적 처리 근거·실제 계약·잔여 정보 검토를 이어간다.
