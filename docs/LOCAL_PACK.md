# 국내 가게 실행팩 사용

## 한 장 요약

이 기능은 확인된 가게 사실로 네이버 소식·리뷰 답글·주간 실행 카드를 만들고,
사장님 승인과 최종 reviewer PASS 뒤 복사할 텍스트와 안내서를 ZIP으로 저장한다.
먼저 기존 온보딩으로 `clients/<slug>/`의 가게·브랜드·가격·카피 정보를 준비한다.
사진 첨부·이미지 생성·외부 게시 기능은 없으며 G02는 OPEN이다.

## 입력과 실행

`examples/local-pack-brief.json`은 합성 예시다. 실제 작업에서는 로컬 파일에 확인된
가게 사실 1~2개와 필요한 리뷰 최대 5개를 넣고 고객 식별 정보와 불필요한 내용을 지운다.
자동 마스킹은 일부 표기만 인식하므로 자유 서술을 전부 안전하게 바꾸지는 않는다.
리뷰 답글은 제공된 리뷰의 순서 번호에 대응한다. 리뷰가 없으면 답글도 만들지 않는다.

PowerShell에서 `shop`을 준비한 가게 slug로 바꾸고 실행한다. 아래 live 명령은
운영자가 설정하고 권한을 확인한 executor/reviewer를 사용하며 공급자 사용량이 발생할 수 있다.

```powershell
uv run aicmo run local-store-pack --client shop --run-id shop-week-1 --brief-file examples/local-pack-brief.json --executor claude --review claude
```

`--executor`와 `--review`를 생략하면 오프라인 데모다. 데모로 만든 결과는 ZIP 내보내기가 차단된다.
채널은 현재 `naver`만 지원한다. `owner_minutes`는 5~240 정수이며 주간 계획의 합계 상한이다.
20분 미만이거나 `photo_available=false`이면 소식 1건으로 줄인다. 20분 미만이면 답글도 앞의 최대 2개만 작성한다.
그 외에는 소식 최대 2건과 제공 리뷰 최대 5개다. 이는 제품 한도이며 공식 게시 권장 빈도가 아니다.
`photo_available=true`도 이미지 업로드를 뜻하지 않는다. 실제 사진 선택은 게시 화면에서 직접 한다.

## 검토·수정·승인

실행은 `owner_gate`에서 대기한다. `artifacts/shop-week-1/local-pack.json`의
제목·본문·CTA·기간·사진 안내·리뷰 번호를 확인한다. JSON 구조를 유지해 문안을 수정할 수 있다.

```powershell
uv run aicmo approve shop-week-1 owner_gate --reviewer owner --notes "가격·기간·문안 확인" --accept-edits
uv run aicmo resume shop-week-1 --executor claude --review claude
uv run aicmo export-local-pack shop-week-1
```

최종 reviewer는 사장님이 수정한 버전을 검토한다. WARN·검토 미설정·데모·취소·미승인·누락 파일이면 내보내지 않는다.
승인 이후 파일이 바뀌면 내보내기가 차단된다. 재개 중 재생성된 문안은 다시 사장님 승인을 받아야 한다.
검토가 실패했다면 `aicmo status`의 실패 원인을 확인하고 기존 retry/resume 절차를 사용한다.
실행 정책이나 프롬프트가 바뀐 경우 기존 실행을 조용히 재사용하지 않으며 안내에 따라 새 run을 만든다.

## 실제 파일

`artifacts/<run_id>/exports/local-pack-<hash>.zip` 안에 다음 파일이 들어 있다.

- `news-N.txt`: 제목·본문·CTA 복사용 UTF-8 텍스트
- `reply-N.txt`: 제공 리뷰 번호에 대응하는 답글 텍스트
- `guide.md`: 한 장 요약·기간·출처·사진 부재·주간 카드·직접 게시 안내
- `manifest.json`: 승인된 원본 SHA-256, 각 파일 SHA-256, 검토·게시·사진 상태

확장자를 바꾼 HTML/PDF/PNG를 만들지 않는다. 같은 버전의 재내보내기는 동일한 ZIP을 반환하고,
기존 ZIP이 외부에서 바뀌었으면 덮어쓰지 않는다. 이미 가져간 파일은 사후 승인 취소로 회수할 수 없으므로
게시 직전에 최신 버전·가격·기간을 다시 확인한다. ZIP 저장은 외부 게시나 법적 적합성 확인의 증거가 아니다.

사업주 권한과 답글 알림에 관한 근거는
[네이버 공식 답글 안내](https://help.naver.com/service/30026/contents/20493?lang=ko&osType=COMMONOS)
(2026-09-06 확인)이며, 최종 게시 화면은 사장님이 직접 확인한다.

## 호출 기록 확인

```powershell
uv run aicmo usage shop-week-1
```

생성·최종 검토·검토 JSON 형식 복구의 호출을 구분해서 보여준다. 직접 Anthropic 어댑터가
반환한 입력·출력·캐시 토큰 수는 실패한 응답에서도 기록한다. 잘린 응답은 납품 파일로 저장하지 않는다.
CLI executor가 사용량을 제공하지 않거나 과거 실행에 기록이 없으면 `unavailable`이다.
사용량 0과 미확인은 다르다. 이 기록은 논리적 호출 관측이며 공급자 내부 재시도·실제 청구서 합계·
과금 원장·요금제 잔여량을 나타내지 않는다. 호출 시작 뒤 프로세스가 중단되면 `unfinished`로 남는다.

## 다음 단계

1. 사장님은 실행 전에 가게 정보와 최소한의 사실·리뷰를 준비한다.
2. 사장님은 생성 후 최신 문안을 확인하고 승인하며 reviewer 결과를 확인한다.
3. 사장님은 ZIP을 받은 뒤 공식 화면에서 직접 게시하고 실제 결과를 따로 기록한다.
