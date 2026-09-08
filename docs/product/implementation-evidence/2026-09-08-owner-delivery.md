# 승인 문안 복사와 직접 게시 보고 구현 증거

## 한 장 요약

사장님이 최종 검토된 소식·답글을 복사하고 같은 파일을 ZIP으로 저장한 뒤 직접 게시 날짜를 기록하는 경로를 연결했다.
기존 승인·최종 PASS·파일 검증을 재사용하며 새 생성 서비스나 외부 게시 연동을 추가하지 않았다.
**G21 개발 범위 독립 reviewer PASS(2026-09-08).** 신규 검사와 합성 브라우저 검증을 마쳤다. 전체 회귀에서 기존 동시 학습 검사 1개가 30초 대기를 초과했고, 같은 코드를 그대로 재검사해 통과했다. 전체 실행 자체를 전부 통과로 표시하지 않는다. G02 및 실제 외부 게시·고객 사용성·유료 출시는 OPEN이다.

## 구현과 발견한 문제

- `export.verified_pack`은 기존 ZIP 생성 직전의 검증·렌더 함수를 공개 읽기 경로로 재사용한다. 반환한 동일 바이트를 복사 카드와 ZIP이 공유한다.
- `services._delivery_reader`는 성공/취소 상태·가게·웹 Job 입력 전체를 확인한다. 기존 ZIP의 같은 가게만 비교하던 경계를 보강해 사실/사진 등 입력 불일치를 거절한다.
- `/jobs/<uuid>/delivery/`는 로그인·가게 권한을 먼저 확인하고 승인·terminal PASS·문안·사진·명세를 재검증한다. GET은 납품 파일·사용량·보고 기록을 생성하지 않는다. SQLite WAL/SHM 읽기 조정 파일은 생성될 수 있어 비즈니스 데이터 변경과 구분한다.
- `json_script`로 보관한 정확한 TXT 텍스트를 클릭에서 Clipboard API에 전달한다. 완료 전 성공을 표시하지 않으며 거절/사용 불가 때 readonly 문안을 선택한다. JS가 없어도 직접 선택할 수 있다.
- `PublicationReport`는 승인 묶음/항목/파일 SHA·계정·요청 UUID·revision·게시 날짜·서버 시각을 보존한다. DB unique와 최신 revision 비교로 경합을 제어하고 정정·취소도 새 행으로 추가한다.
- 권한을 철회한 운영자가 캐시된 권한으로 기록할 가능성을 독립 리뷰에서 찾았다. 저장 트랜잭션 안에서 계정을 다시 읽어 활성 상태·가게 권한을 확인하도록 수정했다.
- 한국 날짜는 Job 생성일부터 오늘까지만 허용한다. 오기록 취소는 앱 보고 취소이며 외부 게시물 삭제가 아니다. 최신 20개 이력을 표시하고 이전 기록도 보관한다.
- 게시 URL·고객 리뷰 원문·자유 메모는 추가 수집하지 않는다. 클릭·복사·다운로드·사용자 보고는 성과 원장·매출·KB 학습을 자동 변경하지 않는다.

## 실행 증거

| 검사 | 현재 확인 결과 |
|---|---|
| 기존 내보내기/승인 회귀 | root 35 passed in 53.25s; 독립 35 passed in 152.82s. 실제 엔진과 합성 reviewer를 사용하고 새 읽기 결과와 ZIP 전체 파일 사전이 일치한다. |
| 새 Django 통합 검사 | 최종 전체 실행의 Delivery 4개·Publication 8개 행렬 모두 PASS. SQLite sidecar 구분, KST 미래 시각 안의 로그인 fixture, 날짜/다른 유효 카드의 요청 UUID 충돌 assertion을 포함한 현재 코드다. 초기 Delivery의 sidecar 비교와 Publication의 시각 이동 세션 만료는 검사 fixture 문제를 수정한 뒤 해당 사례를 각각 476.449초·199.616초에 직접 통과했고, 이번 전체 실행에서도 확인했다. |
| 검사 대기 한도 | 기존 180초 wrapper 종료를 PASS로 세지 않는다. 8개 직접 행렬의 1512.860초 실측을 근거로 suite subprocess 대기만 유한 2400초로 확대했다. DB/엔진 제한과 assertion은 유지한다. 서비스 응답 성능이나 SLO의 완료 증거가 아니다. |
| 전체 회귀 | `uv run python -u -m pytest -q`: **593 passed, 1 failed, 1 skipped / 1417.63초**. 유일 실패는 기존 `test_concurrent_learning_activates_one_record`의 subprocess 30초 대기 초과다. 제품·테스트 코드를 변경하지 않고 해당 검사만 재실행해 **1 passed / 9.34초**를 확인했다. skip은 Windows 실제 symlink 생성 권한이다. 로그: `artifacts/real-use-review/g21-final-full-tests.log`, `g21-learning-recheck.log`. |
| 정적·배포 검사 | Ruff 전체 PASS, basedpyright 0 errors/warnings/notes, Django deploy check 0 issues, makemigrations --check --dry-run 변경 없음. |
| 독립 최종 reviewer | **G21 D PASS**. 현재 소스·문서·ZIP/원장·브라우저 증거와 전체/국소 로그를 검토했고 G21의 열린 blocker 없음. 원래 전체 검사의 실패와 호스트 지연 원인 미확정을 보존한다. `artifacts/real-use-review/g21-review.md`. |

빌드한 wheel의 변경 모듈·템플릿·마이그레이션 10개를 현재 소스와 바이트 단위로 비교해 일치했다.
wheel SHA-256은 `45d96569d89c5f337c766fb222c2a2240f69645ac7a676465cbe1dda89e04b7e`이며
로컬 목록은 `artifacts/real-use-review/g21-wheel/evidence.json`에 보관한다.

로컬 Chromium의 합성 실행 `web-d908cb52b77346d38bb81d04ba19c1a5`에서 승인 확인→복사→게시 보고→날짜 정정→이전 요청 재전송→오기록 취소→ZIP을 검증했다.
390/1280px 13개 화면, 키보드 복사, 실제 클립보드 쓰기/읽기, 거절된 Promise의 선택 복구, JS 없음, CSS 글자 18→36px 확대를 확인했다.
Clipboard에 전달한 문자열은 TXT와 정확히 일치하며 OS에서 읽은 값은 Windows CRLF를 정규화해 비교했다.
고의로 대기 중인 Promise는 성공으로 표시되지 않았다. 오래된 요청의 재전송은 최신 정정 기록을 되돌리지 않았고 다른 요청의 오래된 revision은 HTTP 409였다.

- 로컬 증거: `artifacts/real-use-review/g21-synthetic-7a56a169/evidence.json` — SHA-256 `fc5a77f85e59c93d6d60551f9df402bdce5caf8b8b335cbb9592cd5522a66566`.
- 납품 묶음: `4244562e53f76c508e5961d48fe1aaf11b3446b2154da0540c504942ce2f6940`.
- 실제 ZIP: `44a30e87f72f3ed77f140720454370f564e7b7ffc2795186491a282ef2a34db8`; 검증된 모든 파일 바이트와 일치한다.
- 보고·정정·취소 3개 행을 확인했고 엔진 DB 본체 SHA와 상품 사용량은 전후 동일했다(작성 1, 납품 1).
- 첫 브라우저 시도의 대기 Promise 주입 코드가 테스트를 멈춰 종료했다. 제품 코드는 바꾸지 않고 주입 함수의 반환을 수정한 뒤 위 최종 실행을 완료했다.

## 검증 범위와 지원 한계

공급자는 로컬 합성 PackAdapter/PASS reviewer다. 현재 G21 검사는 준비된 가게/작업의 승인 이후 경로를 확인하며 실제 고객 온보딩 관측을 대체하지 않는다.
공식 [네이버 스마트플레이스](https://smartplace.naver.com/) 목적지는 2026-09-08 확인했다. 브라우저 검사에서는 새 탭 목적지 요청을 로컬에서 가로채 `window.opener=null`만 확인했다. 외부 로그인·게시·발송을 실행하지 않았다.
Clipboard 구현은 [MDN writeText](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText)와 [WebKit 설명](https://webkit.org/blog/10855/async-clipboard-api/)의 클릭·보안 컨텍스트·비동기 완료 조건을 따랐다(2026-09-08 열람).
CSS 글자 확대는 실제 OS 배율/브라우저 page zoom/스크린리더·실제 IME 검증이 아니다. 사용자 보고는 실제 게시의 독립 검증이 아니다.
사진 픽셀 개인정보·사용권 진위, 실제 법적 보관/삭제 근거, 공급자·백업 삭제, 실제 결제·고객·유료 운영은 별도 미완료 항목이다.

## 다음 단계

1. 개발자는 위 독립 기술 판정과 전체/국소 검사 결과를 구분해 PR에 반영한다.
2. 운영자는 업데이트 시 `migrate`를 적용하고 기존 승인 파일·게시 보고의 접근/보관 범위를 확인한다.
3. 제품·개발 담당은 G22 공개 경계와 G24 수기 성과 화면을 이어 검증하며 G02와 실제 고객 관측 항목을 OPEN으로 유지한다.
