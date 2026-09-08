# G09 취소 후 추가 검토 호출 차단 증거 — 2026-09-08

## 한 장 요약

**제한된 개발 검증(D) PASS.** 최초 reviewer 호출 중 실행 취소가 확정되고 잘못된 형식의 결과가 반환되면, 후속 `reviewer-format-repair` 호출과 검토 산출물 생성을 차단한다. 기준 커밋은 `a46c079`이며 변경은 `src/aicmo/step_executor.py`와 `tests/test_reviewer_contract.py` 두 파일에 한정한다. G09 전체 예산·가격·실제 비용과 운영 H, G02·전체 goal은 **OPEN**이다.

## 변경과 검증 범위

공통 `_invoke_adapter`가 호출 시작 기록과 실제 adapter 호출 직전에 기존 `_check_lease`를 재사용한다. draft·reviewer·형식 보정의 세 호출 경로가 같은 단계의 `lease_signal`을 전달한다. 별도 취소 상태를 만들거나 형식 보정의 순수 계약을 바꾸지 않았다.

새 회귀는 합성 adapter와 실제 runner/store로 취소를 확정한다. reviewer만 한 번 호출되고, 기존 draft는 보존되며, review 출력·파일이 생성되지 않는지 확인한다. 호출 원장에는 최초 reviewer의 시작/종료만 남고, resume 뒤에도 추가 호출이 없다.

## 실행 근거

로컬 로그는 `artifacts/real-use-review/` 아래에 있다. 문서 작성자는 소스 diff·로그·독립 검토를 읽었으며 검사를 재실행하지 않았다.

| 근거 | 결과 |
|---|---|
| `g09-cancel-repair-before.log` | **1 FAIL / 3.03초**. 취소 후에도 `reviewer-format-repair`가 호출되어 새 회귀가 실패했다. |
| `g09-cancel-repair-after.log` | **31 PASS / 23.10초**. `test_reviewer_contract.py`, `test_run_policy_cancel.py`, `test_lease.py` 세 모듈의 집중 회귀다. |
| 정적 검사 | `g09-cancel-repair-ruff.log`: 대상 Ruff PASS. `g09-cancel-repair-type.log`: **0 errors / 0 warnings / 0 notes**. |
| 독립 검토 | `g09-cancel-repair-review.md`: 소스·회귀·로그 대조 **PASS**, 추가 정적 blocker 없음. 독립 검토자가 별도 검사나 공급자를 호출한 결과는 아니다. |

독립 reviewer가 기록한 최종 소스 SHA-256:

- `src/aicmo/step_executor.py`: `b1135339a9e91faa7d8644dc7e9110e470ffe4865fb6726b90cc4a6a3e162723`
- `tests/test_reviewer_contract.py`: `5673f42641aaa9baf426a5a98ac52cadbb8b216cdd86671e4ae0de166d331420`

## 남은 범위

이 두 소스의 같은 SHA를 포함한 `g26-runtime-final-source.json` 기준으로 새 Python 3.13.15 / SQLite 3.53.1에서 전체 범위를 두 병렬 실행으로 검증했다. core **639 PASS / 1 Windows 권한 SKIP / 2219.75초**와 web **18 PASS / 2345.58초**를 합산한 **657 PASS / 1 SKIP**이며, 서로 겹치지 않는 고유 658개다. 단일 전체 실행으로 집계하지 않는다. 로그·런타임·빌드 근거는 [새 런타임 통합 검증](2026-09-08-store-inspection.md)에 있다.

실제 모델·공급자 호출이나 비용 절감은 측정하지 않았다. 이미 실행 중인 공급자 요청 중단, lease 검사 직후의 동시 취소, SDK 내부 재시도 차단을 보장하지 않는다. 진단·복구 기능 자체의 근거는 해당 문서에서 구분한다.

## 다음 단계

1. Root가 두 소스와 증거 문서를 함께 검토해 PR에 반영하고 수정 전 실패 이력을 보존한다.
2. 공통 논리 호출 예산은 후속 D로, 실제 요율·청구·공급자의 실행 중 취소 관측은 H로 검증한다. G02와 전체 goal은 OPEN으로 유지한다.
