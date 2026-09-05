# G04 데모·실행 성공·납품 가능 상태 분리 증거

## 한 장 요약

워크플로 실행 상태와 고객 납품 가능 상태를 분리했다. 터미널 게이트는 기존처럼 데모를 포함한 실행 자체를 성공으로 끝낼 수 있지만, `delivery-review.json`의 `deliverable`은 실제 생성기, 의미 검토기, PASS 판정, 전체 검토 입력, 버전·SHA-256 참조가 모두 있을 때만 `true`가 된다.

오프라인 스텁은 `delivery_status=demo`, 의미 검토가 없거나 입력/참조가 잘리면 `delivery_status=blocked`로 기록된다. 근거 없는 가격, 금지된 안전 문구, 필수 placeholder는 게이트 FAIL로 실행도 차단한다. `[미확인]`과 `[추정]`은 WARN으로 남겨 선택 정보 부재와 필수 사실 누락을 구분한다.

## 납품 판정 규칙

| 조건 | 실행 게이트 | 납품 상태 |
|---|---|---|
| `LocalAdapter` 또는 오프라인 스텁 표식 | WARN 허용 가능 | `demo`, 납품 불가 |
| 실제 생성, 의미 검토 없음 | 결정론 판정에 따라 성공 가능 | `blocked`, 납품 불가 |
| 실제 생성, 의미 검토 PASS, 전체 검토·참조 완료 | PASS | `deliverable` |
| 의미 검토 입력 또는 artifact reference 잘림 | 기존 판정에 따라 성공 가능 | `blocked`, 납품 불가 |
| 근거/추정 태그 없는 가격 | FAIL | `blocked`, 납품 불가 |
| `매출 보장`, `100% 보장`, `무조건 1위`, `guaranteed ranking` | FAIL | `blocked`, 납품 불가 |
| `[미확인]`, `[추정]` | WARN | `blocked`, 납품 불가 |
| `{{required_value}}`, TODO 등 필수 미완성 표식 | FAIL | `blocked`, 납품 불가 |

## 매니페스트 계약

`aicmo.delivery-manifest.v1`은 run/workflow/step 상태, 납품 가능 여부와 사람이 읽을 수 있는 사유, 생성기·검토기, 검토 문자 수와 잘림 여부, 각 직접 입력 artifact의 `v1`·생성 단계·경로·SHA-256·잘림 여부를 저장한다.

판매용 내보내기는 이 매니페스트의 `deliverable=true`인 버전만 받아야 한다. 현재 저장소에는 별도 판매용 export 명령이 없으므로, 데모나 미검수 결과를 납품 가능으로 표시하는 경로부터 닫았다.

## 변경 파일

- `src/aicmo/gate.py`: 가격 근거, 안전 문구, 선택 미확인과 필수 미완성 판정.
- `src/aicmo/step_executor.py`: 터미널 delivery manifest와 demo/blocked/deliverable 상태.
- `src/aicmo/reviewer_contract.py`: 검증된 의미 reviewer 판정 사유 보존.
- `workflows/*.workflow.yaml`: 터미널 게이트가 보고서와 고객용 결과 파일을 함께 참조.
- `tests/test_delivery_manifest.py`: 합성 워크플로의 납품 판정 통합 검사.
- 기존 `tests/test_launch_pack_spec.py`: 저장소의 실제 workflow YAML이 터미널 delivery gate를 하나씩 갖는지 검사.

## 검증 결과

| 명령 | 결과 |
|---|---|
| `uv run pytest -q tests/test_delivery_manifest.py tests/test_reviewer_contract.py tests/test_gate_and_kb.py tests/test_llm_integration.py tests/test_launch_pack_spec.py` | PASS — 55 passed |
| `uv run pytest -q` | PASS — 240 passed in 82.21s |
| `uv run ruff check .` | PASS |
| `uv run basedpyright` | PASS — 0 errors, 0 warnings |
| `git diff --check` | PASS |
| 실제 `blog-article` LocalAdapter smoke | run success + `delivery_status=demo`, `deliverable=false`; manifest에 `content-log.md`와 `draft.md`의 `v1`·SHA-256 포함 |

## Reviewer 판정

**PASS** — 1차 검토에서 한국식 가격·조사 변형 안전 문구·무관한 URL 우회와 실제 고객 파일 참조 누락을 발견해 수정했다. 2차 검토에서 의미 reviewer의 원문 사유 유실을 발견해 `semantic_review`에 보존하고 WARN/FAIL 회귀검사를 추가했다. 최종 독립 검증에서 우회 입력 차단, 명시 출처 가격 통과, 5개 실제 workflow의 고객 파일별 `v1`·SHA-256 일치, reviewer 사유 보존을 재현했다. reviewer 표적 54개와 전체 240개, Ruff, basedpyright, diff-check가 모두 통과했다.

## 다음 단계

1. G04를 원자적 커밋으로 고정한다.
2. G05에서 실행기·모델·검토 정책을 run에 보존한다.
3. 재개·중복·취소·실패 복구 계약을 같은 정책에 연결한다.
