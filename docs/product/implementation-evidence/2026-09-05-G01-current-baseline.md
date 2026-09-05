# G01 현재 상태와 지원 기능 기준 고정 증거

## 한 장 요약

2026-09-05 기준으로 AI CMO Platform의 기능 지원 범위와 기본 품질 기준을 고정했다. `registry/capabilities.yaml`의 자연어 매핑은 SOP 지원, `workflows/*.workflow.yaml`은 CLI로 실행 가능한 workflow로 구분했다. 기본 stub 생성은 데모이며, 외부 발행·발송·결제·연동은 사람 승인 대상으로 README에 명시했다.

기존 미커밋 작업은 내용별로 `d9c5f18`(레지스트리·daily loop)과 `03d168e`(소상공인 제품화 로드맵)에 보존했다. 이후 G01 수정을 적용했으며 전체 227개 테스트, Ruff, basedpyright, diff 무결성 검사가 통과했다.

## 기능 지원 기준

| 범위 | 기준 소스 | 2026-09-05 상태 | 사용자에게 약속하는 수준 |
|---|---|---:|---|
| 에이전트 | registry / files | 13 / 13 | 역할 프롬프트와 매핑 가능 |
| 자연어 요청 매핑 | registry | 74 | 해당 SOP·agent 조합 선택 가능 |
| 플레이북 Markdown | files | 78 | 사람/에이전트가 읽고 실행할 SOP |
| 실행형 workflow | workflow YAML | 5 | `aicmo run/resume/approve`로 DAG 실행 가능 |
| 생성 executor | CLI 설정 | 기본 stub, 선택 executor | stub은 데모. 실제 납품 판정은 후속 G04 범위 |
| 외부 발행·연동 | 승인 gate | 자동 완료 주장 안 함 | 사람 승인과 실제 외부 결과가 필요 |

수량은 `uv run python scripts/doc_counts.py`로 재현할 수 있다. README의 정적 개수 표기를 제거하고 이 스크립트와 registry를 지식 소스로 사용했다.

## 변경과 근거

- `README.md`: 요청 매핑, 실행 workflow, 데모, 외부 연동을 구분하는 Capability status 표를 추가했다.
- `scripts/doc_counts.py`: 낡은 `CLAUDE.md` 표 파싱을 제거하고 registry·workflow YAML·실제 파일을 직접 세도록 바꾸었다.
- `src/aicmo/capabilities.py`: Pydantic의 설치된 `TypeAdapter`로 registry 구조를 읽는 경계에서 검증하고 타입을 전파했다.
- `src/aicmo/cli/run_cmds.py`: 변경 가능한 기본 리스트를 제거하고 inbox 처리 단위를 함수로 분리해 기존 재시도 동작을 유지했다.
- 나머지 수정은 Ruff·basedpyright의 기존 오류를 타입 표기, 가독성 있는 assert, 근거가 있는 SQL lint 면제로 정리했다. SQL 값은 계속 parameter binding을 사용한다.

## 검증 결과

| 명령 | 결과 |
|---|---|
| `uv run python scripts/doc_counts.py` | PASS — agents 13/13, playbooks 78, mappings 74, executable workflows 5 |
| `uv run ruff check src tests examples scripts/doc_counts.py` | PASS — All checks passed |
| `uv run basedpyright src tests` | PASS — 0 errors, 0 warnings, 0 notes |
| `uv run pytest -q tests/test_capabilities_registry.py tests/test_ingest.py tests/test_accept_edits.py tests/test_pdf_render.py tests/test_primer.py tests/test_primer_cli.py` | PASS — 44 passed in 10.97s |
| `uv run pytest -q` | PASS — 227 passed in 83.92s |
| `git diff --check` | PASS |

Windows checkout의 LF→CRLF 예고는 라인 종료 전환 예고이며 `git diff --check`의 공백 무결성 검사는 통과했다. 이 예고를 취약점으로 분류하지 않았다.

## Reviewer 판정

1차 WARN: evidence의 표적 테스트 수가 malformed-registry 회귀 검사 추가 전 값(43)으로 남아 있었다.

수정 후 재검증: 위의 동일 명령을 실행해 44 passed in 10.97s를 확인했다.

**최종 PASS** — reviewer가 README의 지원 범위 구분, registry 전체 구조 검증, doc counts 일치, inbox 동작 보존, 표적 44·전체 227 테스트와 정적 검사 결과를 독립 재현했다.

## 다음 단계

1. reviewer가 README 지원표, registry 타입, 기존 inbox 동작 보존을 검증한다.
2. PASS 후 G01을 완료 처리하고 원자적 커밋을 남긴다.
3. 다음 의존 항목인 G02 권리·유료 운영 검토 자료를 준비한다.
