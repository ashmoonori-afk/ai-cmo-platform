# 국내 가게 실행팩과 승인 버전 내보내기

## 한 장 요약

기존 러너에 네이버 가게 소식·제공 리뷰 답글·주간 실행 카드의 작은 워크플로우를 추가했다.
사장님 승인 뒤 최종 reviewer가 검토한 버전만 실제 TXT/Markdown ZIP으로 내보낸다.
새 버전이 재생성돼도 이전 승인 기록을 재사용하던 공통 버그를 함께 수정했다.
다음 작업은 공급자 응답 잘림·사용량과 수기 성과 기록이며 G02 및 전체 제품 목표는 OPEN이다.

## 구현 범위

| 흐름 | 동작 | 확인 경로 |
|---|---|---|
| 입력 | UTF-8/BOM 파일, 한글, 12 KiB 한도, 명시된 사실 1~2개와 리뷰 0~5개, 주간 여력 검증 | `--brief-file`, `local_pack.parse_brief` |
| 생성 | 네이버 1채널, 소식 최대 2건·답글 최대 5건. 사진 부재 또는 20분 미만이면 소식 1건, 20분 미만이면 답글 최대 2개 | 기존 adapter·runner와 새 workflow |
| 계약 | JSON 필수 구조·출처/리뷰 번호·건수·시간 상한·가시 문자 확인. 누락·가짜 사진·중복 키·잘린 참조 거부 | `local_pack.validate_pack`, `test_local_pack.py` |
| 승인 | 사장님 편집을 받은 뒤 최종 reviewer가 현재 문안을 검토. 재생성 시 이전 승인을 무효화하고 다시 승인 대기 | `step_state`, `step_executor`, `test_accept_edits.py` |
| 내보내기 | 성공 상태·승인·reviewer PASS·현재 파일/참조 hash·실행 사양 확인 후 ZIP 생성 | `runner.verified_export_outputs`, `export.export_local_pack` |
| 복사 파일 | 소식·답글 TXT와 기간/출처/사진 안내/직접 게시 단계 Markdown, 파일별 SHA-256 manifest | 실제 ZIP 생성 후 모든 entry 읽기 |
| 복구 | 동일 버전의 동일 ZIP, 외부에서 변경한 ZIP 보존/오류, 미승인·데모·WARN·취소·누락·변경된 파일 차단 | 부정 경로 회귀 |

새 매핑 75와 AGENTS·워크플로우 토폴로지 검사를 동기화했다. 사용법은 `docs/LOCAL_PACK.md`,
입력 예시는 `examples/local-pack-brief.json`이다. 계획 원본은 기존 gitignore 아래에 남는다.

## 발견한 결함과 수정

1. 승인된 결과를 재개하면서 다시 생성할 때 approvals의 예전 approved 행이 유지됐다.
   공통 pending 전환에서 승인 행을 제거하고 승인 이벤트 이력은 남긴다.
   이미 기다리는 gate도 선행 결과가 무효화되면 다시 대기하도록 재개 경로를 맞췄다.
2. 새 워크플로우를 추가한 뒤 저장소 전체 terminal gate의 기대 목록이 빠져 회귀가 실패했다.
   실제 의존 관계에 맞게 생산자·선행 입력 기대 목록을 갱신했다.
3. 독립 reviewer가 제로폭·결합문자만 있는 문자열의 빈 납품 우회를 재현했다.
   모든 입력/산출물 Text에 NFKC 가시 문자와 제어문자 검증을 적용했다. Windows CRLF는 보존한다.
4. 독립 reviewer가 사진 상태는 unavailable인데 사진 안내에 생성 완료를 쓰는 모순을 재현했다.
   사진 안내를 고정 Literal로 제한하고 허위 완료 문구를 거부한다.

## 검사와 실제 실행 증거

개발 중 전체 회귀는 412 PASS/1 FAIL(토폴로지 기대 목록), 수정 뒤 418 PASS였다.
이 수치는 마지막 제로폭·사진·CRLF 회귀를 포함한 최종 수치와 구분한다.
최종 기록(제로폭·사진·CRLF 수정 포함):

- 전체 `.venv/Scripts/python.exe -m pytest -q --tb=short`: **425 passed in 162.33s**.
- 독립 reviewer 표적: **124 passed in 68.68s**, 최종 판정 **PASS**, 필수 수정 없음.
- 최종 Ruff PASS, basedpyright **0 errors / 0 warnings / 0 notes**, `git diff --check` PASS.
- 최종 합성 ZIP의 각 TXT/Markdown entry를 읽고 manifest SHA-256과 일치함을 확인했다.
- 독립 reviewer 보고서는 로컬 `artifacts/real-use-review/local-pack-review.md`에 보관한다.

실제 PowerShell에서 `python -m aicmo run local-store-pack --brief-file ...` 명령으로
한글 합성 입력을 읽고 `native-cli-demo: waiting_approval`을 확인했다.
`artifacts/real-use-review/local-pack-final-synthetic/`에서는 합성 PackAdapter/PassReviewer로
승인→재개→ZIP 생성→모든 entry 읽기를 수행했다. 파일 검증 fixture이며 실제 공급자나 고객 납품 증거가 아니다.

## 지원 한계

사진·HTML·PDF 내보내기와 자동 게시·발송은 제공하지 않는다. 텍스트 안내에 사진 부재를 명시한다.
공통 마스킹은 자유 서술의 모든 개인정보 탐지나 법적 익명화를 보장하지 않는다.
리뷰 원문은 ZIP에 별도 첨부하지 않으며 잔여 문안 검토가 필요하다.
내보내기는 SQLite 쓰기 잠금과 검증한 바이트를 사용해 로컬 retry/cancel과 순서를 맞춘다.
이미 가져간 파일의 회수, 멀티테넌트 웹 권한, 실제 공급자 비용·사용량, 실제 가게 사용성은 별도 과제다.
합성 PASS를 모델 품질·매출·계약·공개 운영 승인으로 세지 않는다.

## 다음 단계

1. 개발·reviewer는 최종 검사 결과와 수정 범위 판정을 남기고 PR의 원격 SHA를 확인한다.
2. 개발자는 공급자 잘림/사용량과 수기 성과 입력을 기존 러너·저장소에 연결한다.
3. 운영자는 G02를 OPEN으로 유지하며 실제 계약·가게 사용성 증거를 별도로 준비한다.
