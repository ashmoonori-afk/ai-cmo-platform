# G03 가게 정보 수정 시 KB 보존 증거

## 한 장 요약

`scaffold_client(..., force=True)`를 기존 고객 폴더 전체를 덮어쓰는 동작에서 **프로필 파일 갱신**으로 바꾸었다. `config.md`, `brand-guidelines.md`, `primer-report.html`만 갱신하고, `knowledge-base/{client}/` 파일은 없을 때만 초기화한다. 기존 insights, winning copy, lessons learned는 갱신 전후 바이트 단위로 같다.

프로필 갱신은 각 대상의 백업을 만든 뒤 임시 파일을 `Path.replace`로 교체한다. 중간 쓰기가 실패하면 이미 교체한 모든 파일을 역순으로 복구한다. 복구 자체가 실패하면 `.onboarding.bak`을 삭제하지 않고 경로를 오류에 남긴다.

## 동작 규칙

| 상황 | 동작 |
|---|---|
| 신규 client | 프로필 3개와 KB 3개를 생성 |
| 기존 client, `force=False` | 기존처럼 중단하고 수정 안 함 |
| 기존 client, `force=True` | 프로필 3개만 갱신, 기존 KB는 바이트 보존 |
| KB 파일 일부 누락 | 누락 파일만 초기화 |
| 임시 파일 교체 중 실패 | 이미 교체한 파일 전체 롤백 |
| 롤백 실패 | 백업 보존 + 명시적 오류. 다음 갱신은 잔여 백업을 덮어쓰지 않고 중단 |

## 변경 파일

- `src/aicmo/onboarding.py`: 프로필/KB 생성 대상 분리, 백업·임시 파일·롤백.
- `tests/test_onboarding.py`: KB 바이트 보존과 두 번째 교체 실패 롤백 회귀 검사.

## 검증 결과

| 명령 | 결과 |
|---|---|
| `uv run pytest -q tests/test_onboarding.py tests/test_primer_cli.py` | PASS — 23 passed |
| `uv run pytest -q` | PASS — 229 passed in 79.65s |
| `uv run ruff check src tests examples scripts` | PASS |
| `uv run basedpyright src tests` | PASS — 0 errors, 0 warnings |
| `git diff --check` | PASS |

## Reviewer 판정

**PASS** — reviewer가 KB 3개 바이트 보존, 누락 KB만 생성, 두 번째 프로필 교체 실패의 전체 롤백, 복구 실패 시 백업 보존과 다음 갱신 차단, 신규 생성·PDF 옵션을 독립 재현했다. 표적 23·전체 229 테스트와 정적 검사도 통과했다.

## 다음 단계

1. reviewer가 KB 보존·실패 롤백·신규 생성을 재검증한다.
2. PASS 후 G03을 체크하고 원자적 커밋으로 고정한다.
3. G04에서 데모 실행 성공과 고객 납품 가능 상태를 분리한다.
