# G23 보고서 읽기 개선 구현 증거 — 2026-09-08

## 한 장 요약

**G23-R01–04 bounded D PASS.** 검토 당시 숫자 요약과 다음 행동을 원문보다 먼저 보여주고, 상단 바로가기와 기본 접힌 원문을 제공한다. 독립 reviewer는 최종 diff·로그·브라우저 증거·실제 화면을 대조해 추가 blocker가 없다고 판정했다. 이는 아래 세 파일 변경의 개발 검증이며, 실제 사장님 H·전체 G23 사용성·G02·T01–T16·전체 goal은 **OPEN**이다. Git 반영 여부는 이 소스 기반 판정과 별도로 확인한다.

## 변경 경계

- `src/aicmo/store_app/report_views.py`: 요약은 검증된 `report.source.totals`의 네 지표만 사용한다. 현재 원장이나 원문 파싱으로 숫자를 만들지 않는다. 미입력과 0을 구분하고, 입력 N/7일과 비교 가능한 증감률을 표시한다.
- `src/aicmo/store_app/templates/store_app/report.html`: 숫자 요약 → 기존 다음 행동 → 검토 원문 순서다. 상단 native anchor와 기본 닫힌 `details/summary`를 사용한다. 정정·원장 확인 불가 안내는 접지 않으며, 기존 행동 폼·CSRF·요청 키를 유지한다. 원문은 전체를 escape해 표시하고 다운로드는 기존의 정확한 `report.raw`를 사용한다.
- `tests/store_report_cases.py`: 검토 게시 2/현재 3, 원장 확인 불가, 미입력/0, 완전 주 증감률, 검증 실패 시 요약 부재, 원문 escape·동일 다운로드와 읽기 불변을 확인한다. 새 DB·모델·의존성·Markdown 렌더러는 추가하지 않았다.

## 현재 소스의 검증 근거

아래 로그와 브라우저 산출물은 `artifacts/real-use-review/` 아래의 로컬 증거다. 문서 작성 시 원문과 독립 검토 `g23-final-review.md`를 읽어 대조했으며 검사를 재실행하지 않았다.

| 관측 | 결과와 범위 |
|---|---|
| 보고 모듈 최초 실행 | `g23-report-tests.log`: **8 PASS + 1 fixture ERROR / 21.944초**, 총 9개. 신규 오류 주입에서 필수 인자 없이 만든 예외의 TypeError가 발생했다. |
| fixture 수정 후 재검사 | 오류 주입 한 줄을 `OSError(SECRET)`로 바꾼 뒤 해당 신규 사례만 재실행했다. `g23-report-recheck.log`: **1 PASS / 3.205초**, system check 0. 최신 전체 모듈을 한 번에 재실행한 결과는 아니다. |
| 정적 검사 | `g23-report-ruff.log`: 대상 Ruff PASS. `g23-type.log`: 대상 basedpyright **0 errors / 0 warnings / 0 notes**. |
| 빌드·소스 대응 | `g23-build.log`: wheel 빌드 성공, root 종료 코드 0 전달. `g23-final-source.json`의 세 소스 SHA는 독립 검토와 일치한다. 패키지 파일 **114개**가 현재 소스 bytes와 일치했다는 root 대조 결과를 기록했다. wheel SHA-256: `2b234f2d722d21a24b5008bb38e35760c1b3d87e3e61c54eedbf868793ef8365`. |
| 실제 localhost Chromium | `g23-browser.log`: root 실행 종료 코드 0 전달. `g23-report-5e3f7a16/evidence.json`과 PNG **13개**: 합성 native weekly-report/PASS reviewer, 폭 360/390/1280px, 글자 18→36px 확대, 키보드, JavaScript 없는 페이지. |
| 행동과 숫자 | 390×844px 첫 화면의 다음 행동 링크 y=369.21875px, 높이 52.796875px. Enter로 행동 제목, Tab으로 기존 폼에 초점이 이동한다. 검토 게시 2/현재 3, 확인한 문의 0/예약 미입력, 빈 스냅샷과 원장 확인 불가에서도 검토 숫자 유지가 관측됐다. |
| 원문과 읽기 불변 | `g23_readability_smoke.py`는 표시 원문을 줄바꿈 정규화 후 대조하고 다운로드 bytes를 검증한다. 정상 읽기·이동·펼침·저장 전후 엔진 SQL dump 해시, Job ID/state, KB 파일 해시와 합성 adapter 요청 수를 대조했다. 오류 주입 원장은 별도 기준으로 대조 후 복원했다. 외부 요청은 0이다. |
| 독립 검토 | `g23-final-review.md`: **G23-R01–04 bounded D PASS**. 최종 세 파일·로그·script/JSON·PNG 여섯 장과 원문 파일 SHA를 읽기 대조했다. |

실제 다운로드와 엔진 검토 원문의 동일 SHA-256:
`9f3c4b37eda1c9163a8be78302a25e3123baf579602a59ec7e383931d955a42e`.
브라우저 `evidence.json` SHA-256:
`6c4d9a14a8cd9b797966ee9c433a514e1681a105b87b2792365569da9eca280e`.

## 관측의 한계

이번 변경 뒤 저장소 전체 pytest·전체 타입 검사는 재실행하지 않았다. G24의 두 병렬 shard 합산 **633 PASS / 1 SKIP**는 기준 커밋 `793175924e3cfb9f8a2e0ad87215a7beeee643a8`의 과거 결과이며 현재 G23 전체 회귀 결과로 사용하지 않는다. 읽기 불변 관측은 웹 DB 전체 테이블이나 WAL/SHM 파일의 바이트 불변을 증명하지 않는다.

합성 브라우저와 글자 확대는 실제 고객의 이해도·작업 시간 개선, OS 확대·보조기기, 실매출·게시·라이브 서비스 또는 현행 국내·미국 법률 검증의 증거가 아니다. 해당 H와 G02는 계속 OPEN이다.

## 다음 단계

1. 소스 기반 D 판정과 이 문서를 함께 검토하고 Git 반영 상태를 확인한다. 최초 fixture 실패와 단일 재검사 이력을 보존한다.
2. 실제 사장님이 미입력/0·부분 주·검토 시점을 이해하고 행동과 원문을 찾는지, 실제 보조기기에서 이동할 수 있는지 H로 검증한다. G02·T01–T16·전체 goal은 OPEN으로 유지한다.
