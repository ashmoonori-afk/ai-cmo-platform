# 한 장 요약

승인된 실행팩의 문안 한 건에서 원본·최종본을 검증하고 사용자 보고 채택/수정 이유를 reviewer에게 전달한다. owner 승인·최종 semantic PASS 뒤 명시적 learn-feedback으로 반영하면 새 팩의 입력 문맥에 검토된 제안이 전달된다. 실제 게시·모델 훈련·매출 인과의 증거로 취급하지 않는다.

## 구현과 완료 조건

| 단계 | 구현 계약 | 검사 위치 |
|---|---|---|
| 원본 고정 | 승인 대기 전 성공 산출물 SHA와 실제 바이트를 대조하고 짧은 .aicmo/snapshots 해시 경로와 approval_snapshots에 연결. 기존 _pre_edit은 보존 | test_accept_edits.py, test_learning.py |
| 후보 입력 | strict JSON·중복 키·보고한 사용 여부·실제 item·날짜·500자 요약, 새 run/event 저장 전 지원 PII/시크릿 최소화 | test_learning.py |
| 증거 비교 | 현재 명세/개인정보 기준·실행 성공·owner 승인·terminal semantic PASS·산출물 SHA, 원본 SHA 및 같은 가게/주간 보고서 확인 | learning.py, export.py, test_local_pack.py |
| 검토/승인 | native feedback.report→owner_gate→delivery_gate. 원본/최종 문안과 이유, 사용자 제안, 선택한 수기 성과 전체를 검토. 잘린 근거·WARN·demo 반영 금지 | local-pack-feedback.workflow.yaml, test_learning.py |
| Reporter 반영 | SQLite IMMEDIATE 거래 안에서 검증→append→정확한 블록 확인→receipt commit. 실패하면 활성 receipt 없음. 동일 evidence ID는 1개 블록/행으로 유지하고 새 유효 run으로 검증 근거 갱신 | test_learning.py 별도 프로세스/중단/재실행 검사 |
| 다음 생성 | 같은 가게의 최신 후보20개 중 유효5개를 learning.context에 기록. 같은 팩·문안은 최신 유효 제안만 선택하며 손상된 최신 근거는 이전 유효 제안으로 복귀. drafts가 그 버전을 dependency로 소비 | 합성 CTA 변경, 정정·이력 보존·손상 fallback 및 제외/대체 수 회귀 |

## 검증 기록

독립 최종 판정은 **PASS**다. 아래 증거는 검토된 피드백을 다음 생성에 전달하는 개발 범위이며 실제 고객 효과 검증과 구분한다. 리뷰 기록은 로컬 `artifacts/real-use-review/approved-feedback-review.md`에 보존한다.

- 최종 전체 pytest: **503 passed, 1 skipped in 253.24s**. Ruff PASS, basedpyright **0 errors / 0 warnings**, diff 검사 PASS. skip은 Windows 호스트의 실제 파일 심볼릭 링크 생성 권한 제한이다. 별도 프로세스 동시 반영·저장 중단 후 재실행·원본/승인/KB 변조·가게/주간 경계는 실행했다.
- 독립 리뷰의 전체 검사: **502 passed, 1 skipped in 252.44s**. 이후 추가된 정정 회귀까지 포함한 최종 전체 수치는 위 503개다. 독립 리뷰는 오래된 receipt 의존과 생성일 이전 관측 허용을 재현했고, 새 유효 실행으로 증거 갱신 및 UTC→KST 생성일 하한으로 수정했다.
- 독립 최신 표적 검사: **64 passed in 117.98s**, Ruff·basedpyright·diff PASS. 최신 정정의 검증 우선 선택과 손상 시 이전 유효값 복귀를 재검토했다. context의 제외/대체 수는 유효한 5개를 찾을 때까지 실제 검사한 범위의 집계이며 최근 20개 전체 총계가 아니다.
- 실제 PowerShell CLI에서 합성 입력으로 run→승인 대기(exit 75)→approve→resume→learn-feedback을 실행했다. 같은 피드백을 두 번 반영한 뒤 KB 블록과 receipt는 각각 한 건이며, 다음 합성 팩의 CTA가 `안내를 확인해 주세요.`로 바뀌었다. reviewer와 생성기는 합성 실행기다. 실제 공급자·고객 채택 성공을 증명하지 않는다.
- 합성 CLI의 후보 SHA-256: `8cde7f1ef3fb3070500da244fb498f3740d3f3d1644760d71a80694017b258bf`. 원본·승인·최종 검토 파일 검증과 다음 출력 관측은 로컬 `artifacts/real-use-review/approved-feedback-synthetic/verified-smoke.json`에 보존한다.

## 지원 범위와 한계

- 문안 한 건의 사건이다. 여러 항목을 수정했다면 항목별로 각각 이유와 제안을 기록한다. 기준 원본은 해당 owner 승인 단계가 대기하기 시작할 때의 검증된 버전이다.
- 기록일은 원본 생성일의 한국 날짜 이상, 오늘 이하여야 한다. 주간 보고서는 같은 가게·네이버·관측 주의 검토된 스냅샷이며 인과를 증명하지 않는다.
- JSON 입력8KiB·후보6,000자·요약각500자·다음 생성의 유효5개는 구현 한도다. 사용자 보고는 실제 가게 권한/게시/효과의 인증이 아니다.
- 원본 검증 기록이 없는 과거 실행은 backfill하지 않는다. 현재 명세로 새 팩을 만든다. 기존 생성 실행의 learning-context는 스냅샷으로 유지하므로 추가 학습은 새 실행에서 반영한다.
- SQLite와 KB는 협조적인 로컬 프로세스 범위다. 정전 내구성·다중 가게 계정 권한·모든 자유 서술 PII 인식은 이번 증거에 포함되지 않는다. 지원되지 않는 데이터는 리뷰 전에 요약한다.
- 사용자는 candidate 파일을 직접 고쳐 승인하지 말고 입력을 고쳐 새 실행을 만든다. 검토된 입력/근거와 다른 candidate는 학습에서 거부한다.

표준 라이브러리의 [SQLite transaction control](https://docs.python.org/3/library/sqlite3.html#transaction-control)과 [hashlib SHA-256](https://docs.python.org/3/library/hashlib.html)을 사용한다(2026 확인). 파일 append와 DB가 하나의 원자적 저장소라는 뜻은 아니며, append 후 DB 미반영의 재실행을 검사한다.

## 다음 단계

1. 운영자와 reviewer는 [사용 안내](../../FEEDBACK_LEARNING.md)에 따라 기록·검토·승인·반영 버전을 확인한다.
2. 운영자는 실제 고객의 허용된 사례로 사용 여부와 수정 이유를 확인한다. 실제 고객 효과는 합성 검사로 대체하지 않는다.
