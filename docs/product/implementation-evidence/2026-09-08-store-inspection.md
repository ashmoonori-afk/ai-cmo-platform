# G26 운영자 읽기 점검 구현 증거 — 2026-09-08

## 한 장 요약

**G26-P02 읽기 진단 D와 새 런타임 개발 호환성의 독립 최종 PASS.** 운영자가 기존 저장소의 웹·엔진 DB 집계를 확인하는 `aicmo inspect-store --repo PATH`를 추가했다. 영문 JSON을 출력하는 운영자 CLI이며 사장님용 화면이나 자동 health 서비스는 아니다. `g26-runtime-final-review.md`에서 소스 6개·전체 회귀 분할·wheel·합성 CLI·문서·PR 본문을 독립 대조했다. G26 전체·운영 H·G02-T01–16·전체 goal은 **OPEN**이다.

## 구현과 관측 경계

- `src/aicmo/store_inspection.py`는 기존 `StoreDb(read_only=True)`로 `.aicmo/web.sqlite3`와 `.aicmo/runs.sqlite3`를 각각 읽는다. initialize·migration·mkdir·writer 잠금·Django 설정 초기화·공급자 호출을 하지 않는다.
- `src/aicmo/cli/inspect_cmds.py`에 등록한 명령은 Job/작업 종류·온보딩/실행 상태별 수, 취소 대기와 가장 오래된 queued/heartbeat 경과를 집계한다. 기존 status/list-runs/usage 동작은 유지한다. 임의 상태·날짜 오류는 `invalid_data`, 읽기 실패는 `unavailable`, 파일/필수 schema 부재는 `missing`/`schema_unsupported`이며 해당 `summary`는 null이다. 성공한 집계 0과 구분한다.
- 출력에 원문·계정/가게/작업 ID·경로·SQL 오류·시크릿을 담지 않는다. 종료 코드 0은 두 DB 집계가 available이라는 뜻이다. `worker_process=unverified`, `provider_cost=unavailable`이며 두 DB는 독립 읽기 트랜잭션이다. 동시점·참조 일치·성공 납품을 검증하지 않는다.
- DB별 busy timeout 1초와 공유 SQL progress 예산 2초를 적용한다. OS 파일 I/O·Python 처리까지 포함한 전체 실행 시간 제한은 아니다. 읽기 전용 WAL도 보조 파일이 필요할 수 있어 업무 원장/DB 본체 불변을 디렉터리 전체 바이트 불변으로 확대하지 않는다.

## 집중 검사와 소스 근거

로컬 근거는 `artifacts/real-use-review/` 아래에 있다. 문서 작성자는 소스·계약·로그·독립 리뷰를 읽었으며 CLI나 검사·런타임을 실행하지 않았다.

| 근거 | 결과와 범위 |
|---|---|
| `g26-inspection-tests.log` | 기존 Python **3.13.5 / SQLite 3.49.1**에서 **10 PASS / 29.45초**. 정상 0/혼합 상태, 누락·schema·손상·실제 잠금, 잘못된 상태/날짜, 커밋된 WAL과 논리 원장/본체 불변을 확인했다. 환경 버전은 root 관측 전달이다. |
| CLI·SQL 제한 | 테스트의 Typer `CliRunner`가 등록된 실제 entrypoint와 0/1 종료 코드를 검증했다. 별도 쉘 근거는 아래에서 구분한다. SQL 제한은 합성 2,000행과 주입한 시계로 실제 progress callback 중단을 검증했다. |
| 정적 검사 | `g26-inspection-ruff.log`, `g26-inspection-test-ruff.log`: 대상 Ruff PASS. `g26-inspection-type.log`: 대상 타입 0/0/0. `g26-inspection-review.md`: 읽기 진단에 한정한 독립 D PASS. |
| 소스 대응 | `g26-inspection-tested-source.json`의 아래 세 SHA가 독립 reviewer의 현재 소스 대조와 일치한다. |

| 파일 | SHA-256 |
|---|---|
| `src/aicmo/store_inspection.py` | `bc4beb89e8d28aa3db70e05657881e77a91fe491ff22b9ecd3918bfcebe5c83b` |
| `src/aicmo/cli/inspect_cmds.py` | `26b7cf3ce6d93afa527d0a51988e35d5d53dd9277f1e07484f39a914d9f38daa` |
| `tests/test_store_inspection.py` | `87d9af29cf7bfeb7a627ec5910dc98f70b1781101a3f57bad2bc984da12d0199` |

## 별도 런타임 변경과 현재 전체 검증

`g26-runtime-environments.json`의 실제 관측은 구 환경 **Python 3.13.5 / SQLite 3.49.1**, 새 환경 **Python 3.13.15 / SQLite 3.53.1**이다. 구 SQLite를 WAL-reset 수정 포함 버전으로 표시할 수 없어 이미 설치된 새 interpreter를 선택했다. `.python-version`에 3.13.15를 지정하고 기존 `.venv`를 유지한 채 별도 ignored 환경 `artifacts/real-use-review/runtime-31315`를 만들었다. `g26-runtime-sync.log`는 기존 로컬 `uv.lock`의 frozen 동기화를 기록한다. 새 환경의 33개 패키지 버전은 구 환경과 같지만, 구 환경에 PDF 관련 추가 9개가 있어 전체 설치 집합은 다르다. 전역 설치나 기존 서버 교체의 증거는 아니다.

`g26-runtime-core.log`: **639 PASS / 1 SKIP / 2219.75초**, `g26-runtime-web.log`: **18 PASS / 2345.58초**, 각각 종료 코드 0이다. 두 별도 병렬 실행의 core 640개와 web 18개는 겹치지 않으며, 고유 수집 658개 전체를 합산하면 **657 PASS / 1 Windows 심볼릭 링크 권한 SKIP**다. 단일 전체 pytest 실행 결과로 표현하지 않는다. `g26-runtime-final-source.json`은 이번 Python 5개 소스와 `.python-version`의 고정 SHA를 기록한다.

`g26-runtime-type.log`: 변경 Python 5개 **0 errors / 0 warnings / 0 notes**, `g26-runtime-ruff.log`: 전체 Ruff PASS. wheel의 현재 소스 **115개 파일 바이트 일치**, SHA-256 `3f9f9f6b704675faf30f3c82cec73b998d387f3ca62b88e3b52ebdeeffb33b4a`는 root 대조 전달이다. 최초 wheel 대조 실패는 검증기 예상 목록에서 실제 포함된 Markdown 7개를 빠뜨린 오류였으며, 목록에 `.md`를 포함한 뒤 제품 변경 없이 115개 일치를 확인했다.

`g26-inspection-shell-proof.json`과 `g26-inspection-shell.log`: 새 런타임의 합성 복구 실습 **exit 0 / 13.645초**, 실제 `aicmo.exe`의 복원 사본 조회 **exit 0 / available / 2.751초**, 없는 저장소 조회 **exit 1 / needs_review / 2.650초**, 모두 stderr 0이다. 원본↔복원 DB의 schema·논리 SHA가 같고 각 DB 본체·논리는 조회 전후 불변이며 없는 root는 생성되지 않았다. 새 합성 자료의 실제 쉘 실행으로, 운영 DB·worker·공급자를 확인한 증거는 아니다.

설치한 바이너리마다 SQLite 버전과 수정 포함 여부를 확인해야 한다. Python 버전 고정만으로 모든 플랫폼의 SQLite 패치를 보장하지 않는다. 이 명령의 버전 분류는 공식 수정 계열 대조이며 별도 backport·결함 재현을 검증하지 않는다. 실제 서버의 중단·런타임 전환·배포·worker·비용·복구/지원 검증은 운영 H다.

## 다음 단계

1. 독립 PASS 소스·문서를 PR에 반영하고 각 실행의 원본 근거와 소스 해시를 보존한다.
2. 운영 환경의 실제 SQLite 바이너리와 전환 절차·worker·비용·지원 관측을 별도 검증한다. G26 전체·G02·전체 goal은 OPEN으로 유지한다.
