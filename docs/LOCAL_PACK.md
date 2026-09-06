# 국내 가게 실행팩 사용

## 한 장 요약

이 기능은 확인된 가게 사실로 네이버 소식·리뷰 답글·주간 실행 카드를 만들고,
사장님 승인과 최종 reviewer PASS 뒤 복사할 텍스트와 안내서를 ZIP으로 저장한다.
먼저 기존 온보딩으로 `clients/<slug>/`의 가게·브랜드·가격·카피 정보를 준비한다.
제공한 JPEG/PNG는 검증 후 사진 파일로 첨부할 수 있다. 이미지 생성·외부 게시 기능은 없으며 G02는 OPEN이다.

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
20분 미만이거나 실제 첨부 사진이 없으면 소식 1건으로 줄인다. 20분 미만이면 답글도 앞의 최대 2개만 작성한다.
그 외에는 소식 최대 2건과 제공 리뷰 최대 5개다. 이는 제품 한도이며 공식 게시 권장 빈도가 아니다.
`photo_available`은 이전 입력 호환용이며 실제 보유 판정에는 사용하지 않는다.

## 사진 첨부

다음 JSON을 사진과 같은 로컬 폴더의 `photos.json`으로 저장한다. 경로는 이 폴더 안의 상대 경로만 허용한다.
`news_index`는 0부터 시작하는 소식 번호다. 소식당 1개, 전체 최대 2개이며 팩의 소식 수를 넘길 수 없다.
`privacy_reviewed=true`는 사장님이 픽셀 안의 잔여 개인정보를 확인했다는 선언이다.
`rights_basis`는 직접 촬영 `own_photo` 또는 사용 허락을 받은 `permission_received` 중 하나다.

```json
{"schema_version":"aicmo.photo-upload.v1","photos":[{"path":"store.jpg","news_index":0,"caption":"이번 주 가게 사진","rights_basis":"own_photo","privacy_reviewed":true}]}
```

```powershell
uv run aicmo run local-store-pack --client shop --run-id shop-photo-week-1 --brief-file examples/local-pack-brief.json --photos-file photos.json --executor claude --review claude
uv run aicmo photo-preview shop-photo-week-1
```

출력된 HTML 경로를 브라우저로 열고 정규화된 실제 사진을 확인한다.
JPEG/PNG의 실제 디코딩, 파일당 20 MiB·2,400만 픽셀·단일 프레임 한도를 검사한다.
EXIF 방향을 반영하고 긴 변을 최대 2,048픽셀로 축소한 PNG에서 EXIF/GPS/ICC/댓글/텍스트 메타데이터를 제거한다.
이 수치는 프로그램의 처리 한도이며 네이버 공식 권장 규격이 아니다. 투명도는 유지하지만 ICC 제거로 색 표현이 달라질 수 있다.
HEIC/GIF/WebP·애니메이션은 지원하지 않는다. 지원 형식으로 사용자가 변환하고 결과를 확인해야 한다.
원본을 덮어쓰거나 별도로 복사해 보관하지 않는다. 원본 경로·파일명과 별도 `source_sha256` 필드는 실행 입력·모델 요청·납품 ZIP에 넣지 않는다.
이미 정규화된 PNG를 입력하면 원본과 저장 PNG의 바이트 및 해시가 같을 수 있다.
정규화된 PNG는 `.aicmo/photos/<가게 해시>/<PNG 해시>.png`에 남고 로컬 미리보기가 이를 참조한다.
자동 보관 기한·삭제 서비스는 아직 없으므로 원본 폴더와 로컬 저장소의 접근·백업·삭제는 운영자가 관리한다.

## 검토·수정·승인

실행은 `owner_gate`에서 대기한다. `artifacts/shop-week-1/local-pack.json`의
제목·본문·CTA·기간·사진 안내·리뷰 번호를 확인한다. JSON 구조를 유지해 문안을 수정할 수 있다.

```powershell
uv run aicmo approve shop-week-1 owner_gate --reviewer owner --notes "가격·기간·문안 확인" --accept-edits
uv run aicmo resume shop-week-1 --executor claude --review claude
uv run aicmo export-local-pack shop-week-1
```

사진을 첨부한 실행에서는 `approve shop-photo-week-1 owner_gate --photos-reviewed`처럼 확인 옵션이 필수다.
이 옵션은 사진을 보았다는 사람의 선언이며 픽셀 자동 분석이나 권리 인증이 아니다.
`--accept-edits`로 인정하는 파일은 `local-pack.json`뿐이다. 사진/사진 목록 수정·삭제는 새 실행과 승인이 필요하다.
사진 manifest와 실제 PNG 버전은 승인·재개·최종 검토·완료·내보내기에서 다시 확인한다.

최종 reviewer는 사장님이 수정한 버전을 검토한다. WARN·검토 미설정·데모·취소·미승인·누락 파일이면 내보내지 않는다.
승인 이후 파일이 바뀌면 내보내기가 차단된다. 재개 중 재생성된 문안은 다시 사장님 승인을 받아야 한다.
검토가 실패했다면 `aicmo status`의 실패 원인을 확인하고 기존 retry/resume 절차를 사용한다.
실행 정책이나 프롬프트가 바뀐 경우 기존 실행을 조용히 재사용하지 않으며 안내에 따라 새 run을 만든다.

## 실제 파일

`artifacts/<run_id>/exports/local-pack-<hash>.zip` 안에 다음 파일이 들어 있다.

- `news-N.txt`: 제목·본문·CTA 복사용 UTF-8 텍스트
- `reply-N.txt`: 제공 리뷰 번호에 대응하는 답글 텍스트
- `guide.md`: 한 장 요약·기간·출처·소식별 사진 첨부/부재·주간 카드·직접 게시 안내
- `photos/news-N.png`: 제공되고 승인된 정규화 사진. 없는 소식의 파일은 만들지 않음
- `photos.json`: PNG 형식·크기·SHA-256·소식 번호·설명·사용권/개인정보 확인 선언
- `manifest.json`: 승인된 문안·사진 목록·묶음 SHA-256, 각 파일 SHA-256, 검토·게시·사진 상태

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
