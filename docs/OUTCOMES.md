# 가게 수기 성과와 주간 보고서

## 한 장 요약

게시·문의·예약·쿠폰 사용 건수를 일별로 기록하고 주간 보고서를 만든다.
외부 계정을 연결하지 않으며 고객 이름·전화번호·주문 원문을 받지 않는다.
숫자는 관측한 건수이고 이 기능만으로 AI의 매출 기여를 판단하지 않는다.

## 1. 숫자 파일 준비

온보딩한 가게의 `clients/<slug>/config.md`와 브랜드 문서를 먼저 준비한다.
`examples/manual-outcomes.csv`는 합성 예시이며 실제 실적이 아니다. 날짜와 숫자를 실제 관측값으로 바꾼다.

```csv
date,channel,posts,inquiries,reservations,coupon_redemptions
2026-08-31,naver,1,0,,0
```

| 열 | 의미 |
|---|---|
| date | Asia/Seoul 기준 날짜 YYYY-MM-DD, 2000~2099년 중 오늘까지 |
| channel | naver / google-business / instagram / offline 중 자료를 관측한 채널 |
| posts | 실제로 게시한 건수. 생성·복사한 문안 수와 구분 |
| inquiries | 확인한 문의 건수 |
| reservations | 확인한 예약 건수 |
| coupon_redemptions | 확인한 쿠폰 사용 건수 |

빈칸은 **미입력**, `0`은 **확인한 0건**이다. 0~1,000,000 범위의 정수만 받으며
소수·음수·수식·고객 메모는 거부한다. 같은 문의나 예약을 여러 채널에 중복 기록하지 않는다.
현재 모든 날짜 경계는 Asia/Seoul이며 다른 시간대 자료를 변환 없이 혼합하지 않는다.
파일은 한 채널·월요일부터 일요일까지 한 주·최대 7행·32 KiB 이하다.
UTF-8 또는 UTF-8 BOM의 쉼표 CSV를 사용하고, 열 이름과 순서를 그대로 유지한다.
CP949·Excel 통합문서·다른 구분자는 지원하지 않으며 인코딩을 추측해 가져오지 않는다.

## 2. 미리 보고 저장

PowerShell에서 가게 slug와 파일을 지정한다. 기본 실행은 미리보기이며 실적을 저장하지 않는다.

```powershell
uv run aicmo outcomes --client shop --week-start 2026-08-31 --from counts.csv
```

화면의 기간·채널·인코딩·기존값·입력값을 대조한다. `confirmation_sha256` 값을 복사해 저장한다.

```powershell
uv run aicmo outcomes --client shop --week-start 2026-08-31 --from counts.csv --confirm-sha COPIED_SHA
```

`COPIED_SHA`는 출력에서 복사한 실제 64자리 값으로 바꾼다. 자동 도구에서는 `--json` 미리보기를 사용할 수 있다.
파일 또는 해당 주의 저장값이 바뀌면 다시 미리 봐야 한다. 같은 저장 요청을 재실행해도 중복 합산하지 않는다.
기존 숫자를 정정하려면 새 미리보기 후 저장 명령에 `--replace`를 추가한다.
**정정은 CSV에 포함한 날짜의 행 전체를 바꾼다. 빈칸도 미입력으로 정정하므로 기존값을 지울지 확인한다.**
CSV에 없는 날짜와 다른 채널·가게·주차는 보존한다. 동시 저장은 SQLite 트랜잭션으로 직렬화한다.

## 3. 주간 보고서 검토

```powershell
uv run aicmo run weekly-report --client shop --input week_start=2026-08-31 --input channel=naver --run-id shop-week-1 --review claude
```

운영자가 설정한 reviewer CLI를 사용하며 해당 도구의 사용량이 발생할 수 있다.
집계 자체는 모델 없이 계산한다. `--review`를 생략하면 검토 전 자료이며 납품 가능 상태가 아니다.
`aicmo status shop-week-1`과 `artifacts/shop-week-1/delivery-review.json`의
`deliverable`을 확인하고, PASS인 `artifacts/shop-week-1/weekly-report.md`를 전달한다.
리포트 파일 존재만으로 검토 완료라고 판단하지 않는다.

지표마다 관측 부분합과 N/7일을 표시한다. 두 주 모두 7일 입력되었고 지난주 합계가 0보다 클 때만
증감률을 표시한다. 채널별 자료를 합산하거나 비어 있는 날을 0으로 채우지 않는다.
보고서에는 두 주의 일별값과 CSV SHA, 행 수정번호, 집계 스냅샷 SHA가 포함된다.
같은 run의 resume는 기존 보고서를 보존한다. 자료를 정정했으면 새로운 run ID로 다시 생성·검토한다.
이 로컬 CLI는 가게별 웹 인증이나 실제 사용자 검증의 증거가 아니며 G02는 OPEN이다.

## 다음 단계

1. 사장님은 매주 관측한 날짜·채널·숫자를 준비하고 빈칸을 0으로 채우지 않는다.
2. 운영자는 저장 전 미리보기를 확인하고 정정 후 새 보고서를 생성한다.
3. reviewer는 전달 전에 기간·출처·미입력 범위·계산을 검토한다.
