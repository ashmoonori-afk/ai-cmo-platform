# G05 재개 정책·중복·취소·실패 복구 계약 증거

## 한 장 요약

run마다 `aicmo.run-policy.v1` 실행 정책을 SQLite에 저장한다. 정책에는 실행기 유형, raw command를 노출하지 않는 command SHA-256과 timeout, 의미 reviewer 유형, workflow 각 단계의 model이 들어간다. 같은 정책만 기본 재개되며, 다른 정책은 `--allow-policy-change`를 명시해야 하고 변경 이벤트가 남는다. CLI에서 이전 실행기 옵션을 빼 local로 재개하면 정책 불일치로 작업 전에 중단된다.

`run_id`는 요청 중복키다. 같은 workflow·입력·정책으로 같은 `run_id`를 다시 호출하면 성공 단계와 파일을 재생성하지 않는다. 다른 workflow·입력·spec·정책이면 충돌로 중단한다. 각 step은 총 3회까지만 실행할 수 있다.

`aicmo cancel RUN_ID`는 성공하지 않은 step을 `cancelled`로 바꾸고 lease를 회수한다. 실행 중 adapter가 뒤늦게 반환해도 취소된 lease로 파일 교체·성공 기록·납품 게이트를 진행할 수 없다. 취소 전 성공 파일과 해시는 유지되며 취소 run은 재개해도 추가 작업을 하지 않는다.

## 상태 계약

| 상황 | 결과 |
|---|---|
| 동일 run_id·spec·입력·정책 재호출 | 기존 성공 단계 재사용 |
| 실행기/reviewer/command timeout·model 변경 | 기본 재개 차단 |
| `--allow-policy-change` 명시 | 정책 갱신 + `run.policy_changed` 이벤트 |
| 공급자 실패 | step/run FAILED, 이전 성공 파일 유지 |
| step 세 번째 실패 | 네 번째 실행 차단 + `step.retry_exhausted` 이벤트 |
| 실행 중 취소 | run/미완료 step CANCELLED, lease 해제 |
| 취소 adapter의 늦은 반환 | 파일 교체·성공·납품 진행 차단 |
| terminal delivery 뒤 독립 step 또는 terminal gate 복수 선언 | workflow 파싱 차단 |
| 성공 완료 후 취소 | 잘못된 상태 전이로 차단 |

## 변경 파일

- `src/aicmo/schema.py`, `db.py`, `run_state.py`: 실행 정책 저장과 기존 DB nullable migration.
- `src/aicmo/models.py`, `step_state.py`: CANCELLED 상태, 3회 상한, 유일한 최종 terminal gate, 취소 원자 전이와 claim 경쟁 차단.
- `src/aicmo/runner.py`, `step_executor.py`: 정책 대조, 명시 변경, 취소/재시도 중단, 납품 진행 차단.
- `src/aicmo/cli/run_cmds.py`, `_shared.py`: `cancel`, `--allow-policy-change`, cancelled exit code.
- `tests/test_run_policy_cancel.py`: 정책·중복키·재시도 상한·실행 중 취소 통합 검사.
- 기존 lease/spec drift 검사: 정책 변경을 명시한 lease 탈취와 기존 DB migration 회귀.

## 검증 결과

| 명령 | 결과 |
|---|---|
| `uv run pytest -q tests/test_run_policy_cancel.py tests/test_resume_spec_drift.py tests/test_lease.py tests/test_workflow_engine.py tests/test_workflow_safety.py tests/test_operating_contract.py tests/test_launch_pack_spec.py tests/test_atomic_completion.py` | PASS — reviewer 독립 확장 표적 67 passed in 37.62s |
| `uv run pytest -q` | PASS — 구현자 246 passed in 93.69s, reviewer 246 passed in 92.35s |
| `uv run ruff check .` | PASS |
| `uv run basedpyright` | PASS — 0 errors, 0 warnings |
| `uv run aicmo resume --help` / `uv run aicmo cancel --help` | PASS — 새 옵션·명령 노출 |
| `git diff --check` | PASS |

## Reviewer 판정

**PASS** — 1차 검토에서 Anthropic 기본 모델·토큰 한도 누락과 terminal manifest 완료 직후 취소 경합을 발견해 수정했다. 2차 검토에서 terminal gate 뒤 독립 step을 허용하는 토폴로지 우회를 발견해 terminal gate를 유일한 최종 step으로 강제했다. 최종 독립 검증에서 실행기/reviewer 정책, silent local 차단, 명시 변경, run_id 멱등, 3회 상한, live cancel과 완료 직전 cancel 경합, 이전 성공 파일 보존, 기존 DB migration, lease·atomic 회귀를 재현했다.

## 다음 단계

1. G05를 원자적 커밋으로 고정한다.
2. G06에서 소상공인 프로필과 CLI/웹 입력 검증을 한 스키마로 통일한다.
3. 신규 고객과 기존 config migration을 같은 입력 계약으로 검증한다.
