# 한 장 요약

가게 실행팩의 월간 상품 수량을 작업 실행권 획득과 같은 SQLite 트랜잭션에서 예약하고, 검토된 납품의 완료 때 한 번 차감한다. 승인 대기·실패·재시도·취소·상품 단위 반환을 기존 엔진에 연결했다. 실제 금전 결제·공급자 비용 상한은 별도 범위다.

## 구현 계약

| 경계 | 구현과 검증 |
|---|---|
| 월간 한도 | 가게/한국 시간 달력 월 단위 팩 수와 drafts claim 수. 관리 이력 있는 가게의 미설정 월 차단, 하향 변경은 이미 예약/차감/시도한 수량 이상이어야 함 |
| 중복·동시 요청 | 기존 step CAS와 같은 쓰기 트랜잭션에서 예약/시도 기록. 성공·승인 대기로 바뀐 step은 오래된 관측값으로 다시 claim하지 못함 |
| 승인 대기 | 예약월 유지, resume without approval은 추가 예약/생성 시도 없음 |
| 실패·재시도 | 예약만 해제, 발생한 drafts claim 수는 유지. downstream 단계부터 재개해도 재예약 확인. 한도 거부는 step/run failed로 기록하고 거부 자체는 attempt를 늘리지 않음 |
| 차감 | 현재 명세/개인정보·모든 산출물/의존 해시·owner 승인·manifest/semantic PASS 검증. 완료 트랜잭션에서 terminal 저장 해시 재대조 및 모든 step success 확인 |
| 정상 미납품 | WARN/demo/미검수는 기존 실행상 success 계약을 보존하고 예약을 해제. 손상된 납품 증거는 실패 처리 |
| 재생성·반환 | consumed 재생성은 중복 차감/자동 반환 없음. 명시적 상품 credit 1회, credited 실행의 resume/재생성 금지. 금전 환불과 구분 |
| 과거 실행 | 미설정 가게의 첫 claim은 unmetered 고정. 이 기능 이전의 진행 중 실행도 소급 차감하지 않음 |

## 실행 증거

- 관련 팩/학습/한도 표적: 64 passed in 141.71s. 확장한 한도 표적: 12 passed in 41.85s. 두 Python 프로세스의 같은 run/다른 run 경합, stale lease 재획득, 취소, 월경계, rollback, 상품 credit CLI와 과거 실행을 포함한다.
- 실제 PowerShell 합성 CLI: quota-set→run→owner 승인 대기 시 reserved=1→approve/resume 후 consumed=1→quota-credit 두 번 후 credited=1. drafts claim은 1회다. 검증된 이벤트 순서는 reserved→draft_attempt→consumed→credited다.
- 차감 증거로 저장한 terminal SHA-256과 실제 파일 SHA가 일치했다: `95a3c0aad04f1e752e7416de093b2c623b920bc5a83166c6e7b8bed1f5ac60ef`. 합성 원장·이벤트·상태 파일: 로컬 `artifacts/real-use-review/quota-synthetic/verified-smoke.json`.
- 전체 회귀: **515 passed, 1 skipped in 312.17s**. skip은 Windows 호스트의 실제 파일 심볼릭 링크 생성 권한 제한이다. 한도·별도 프로세스 동시 실행은 건너뛰지 않았다.
- 독립 검사: 한도 표적 **12 passed in 39.24s**, 한도·취소·원자적 저장·팩·납품 manifest **71 passed in 89.35s**, 전체 **515 passed, 1 skipped in 294.48s**. Ruff PASS, basedpyright **0 errors / 0 warnings**, diff PASS. 최종 독립 문서/구현 판정은 **PASS**, 필수 수정 사항 없음. 리뷰는 로컬 `artifacts/real-use-review/product-quotas-review.md`에 보존한다.

## 지원 한계

한도는 한 SQLite DB를 공유하는 협조적인 로컬 운영자와 local-store-pack에 적용한다. 계정 권한·실제 가게 소유권·서버별 분산 제한·요금제 계약·금전 환불은 포함하지 않는다. 로컬 CLI에서 DB를 바꾸거나 직접 편집하는 권한을 가진 운영자를 막는 장치가 아니다.

drafts claim은 공급자 호출 수나 실제 토큰/금전 청구비가 아니다. claim 이후 검증 실패나 중단도 보수적으로 시도로 남기며, 리뷰/형식 복구/SDK 내부 재시도는 이 상한으로 집계하지 않는다. 예상비용 unavailable과 기존 usage 관측은 그대로 구분한다. 공급자 사용량·가격·청구 대사와 실제 호출 검증이 없어 G09 전체는 OPEN이다. G02도 OPEN이다.

## 다음 단계

1. 개발자와 reviewer는 PR의 구현 증거와 남은 G09 범위를 대조한다.
2. 운영자는 [사용 안내](../../PRODUCT_QUOTAS.md)에 따라 새 관리 실행 전에 한도를 설정하고 실제 상품 범위와 대조한다.
