# 유료 운영 범위·권리·공급자 결정 기록

## 한 장 요약

2026-09-05 확인 결과, AI CMO Platform 루트에는 `LICENSE`가 없다. 일반적인 코드 재배포·수정·판매 권리를 제3자에게 준 증거가 없으므로, 루트 라이선스와 기여 권리를 확인하기 전에 저장소 사본을 판매하거나 외부에 재배포하지 않는다.

권장 상품 경계는 **코드 자체 판매**가 아니라 **호스팅, 온보딩, 산출물 검수, 월간 운영 지원**이다. 단, 이 경계는 운영자 확정과 법률·세무 검토 전의 **[제안]**이다. 유료 판매·결제·공개 배포는 아래 D1–D6가 확정될 때까지 보류한다.

## 현재 저장소 권리 점검

| 대상 | 확인 결과 | 운영 의미 |
|---|---|---|
| 루트 코드·문서 | `LICENSE` 없음 | 재배포·서브라이선스 조건이 미확정 |
| Git 기여자 | 이메일 별칭 포함 4개 표시 | 동일인 여부와 상업 이용 동의 **[미확인]** |
| upstream 참조 자료 | `references/upstream/ai-marketing-skills/` 내 MIT 전문·NOTICE·provenance 있음 | 해당 참조 자료를 배포할 때 저작권·허가 고지 유지 |
| Birkin skills | 파일 front matter에 MIT 표시 | 원출처·전문 충분성을 배포 전 별도 확인 |
| README | 종전 '누구나 가져다 쓰고 고침' 주장 | 루트 라이선스와 충돌해 현재 상태로 수정 |

## 공급자 검토

| 후보 | 공식 근거 | 판단 |
|---|---|---|
| Anthropic API | [Commercial Terms](https://www.anthropic.com/legal/commercial-terms)는 고객 제품·서비스에 API를 사용할 수 있고, 입력 권리는 고객에게 남으며 출력은 고객 소유로 정함. 출력의 정확성·적합성·사람 검토는 고객 책임 | 현재 native adapter가 있으므로 1차 후보. consumer 계정이 아닌 상업 API 계약을 사용 |
| Anthropic 데이터 | [2026-07-01 보관 정책](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)은 API 입·출력을 기본 30일 이내 삭제하되 정책 위반·법적 필요 등 예외를 명시 | 고객 정책에 '공급자 예외'를 정확히 고지. ZDR은 별도 승인·계약 후만 주장 |
| OpenAI API | [Services Agreement](https://openai.com/policies/services-agreement/)는 API를 고객 application에 통합할 권리, 입력 권리 유지, 출력 소유, 정확성·적합성 평가의 고객 책임을 명시 | 보조 공급자 후보. 공식 API 사업 계약으로 제한 |
| OpenAI 데이터 | [API data controls](https://developers.openai.com/api/docs/guides/your-data)는 기본 비학습, abuse log 최대 30일, endpoint별 application state, 승인형 ZDR/MAM을 구분 | 사용 endpoint와 `store` 정책을 배포 전 고정. ZDR 자격을 추정하지 않음 |
| 로컬 CLI preset | 현재 `claude -p`, `codex exec`에 prompt를 전달 | 개발자 로컬 실험용. 계정 종류·상업 이용 조건·데이터 보관이 런타임에서 입증되지 않으므로 유료 hosted 경로에서 사용하지 않음 |

출력 소유 조항은 입력에 대한 제3자 권리 문제, 유사 출력, 상표·초상·개인정보 위반을 자동 해결하지 않는다. 모든 고객 납품물은 권리·정확성 검토를 거친다.

## 국내 판매·개인정보 검토 기준

- [전자상거래법 현행 본문](https://www.law.go.kr/lsInfoP.do?ancYnChk=0&lsId=009318)과 [제18조 환급 효과](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029561355)를 기준으로 청약철회 가능 대상·기간, 디지털콘텐츠/용역 개시 후 예외 표시, 환급 기한을 약관과 결제 화면에 반영해야 한다. B2B 소상공인 계약에 각 조항이 어떻게 적용되는지는 법률 검토로 확정한다.
- [2026 개인정보 처리방침 작성지침](https://www.privacy.go.kr/front/bbs/bbsList.do?bbsNo=BBSMSTR_000000000049)(2026-04-24 게시)에 따라 처리 목적, 항목, 보유기간, 제3자 제공·위탁, 파기, 이용자 권리, 안전조치, 문의처를 공개한다.
- 고객이 제공한 리뷰·CRM·매출 자료는 G07의 모델 전송 전 최소화·익명화가 적용되기 전까지 유료 운영에 사용하지 않는다.

## 운영자 확정 필요

| ID | 추천안 | 선택지 | 상태 |
|---|---|---|---|
| D1 상품 경계 | 코어 운영체계와 호스팅·온보딩·검수·지원을 분리 | 관리형 서비스 / 코드 라이선스 판매 / 둘 다 | **[미확인]** |
| D2 루트 라이선스 | 공개 코드를 유지하려면 Apache-2.0 등을 별도 검토, 코드 독점 판매를 원하면 소유권 보류 | proprietary / permissive OSS / source-available | **[미확인]** |
| D3 공급자 | Anthropic 상업 API를 1차, OpenAI API를 후속 보조로 검토 | Anthropic / OpenAI / 복수 | **[미확인]** |
| D4 데이터 보관 | raw 입력 30일, 산출물 90일, 해지 후 30일 내 파기 **[제안]** | 기간 확정 + 법정 보존 분리 | **[미확인]** |
| D5 해지·환불 | 다음 갱신 전 해지, 미납품/중대 하자는 재수행 또는 환불, 법정 권리 우선 **[제안]** | 일할/월할/신청 기간·예외 확정 | **[미확인]** |
| D6 계약 책임 | 고객은 입력 권리를 보증, 운영자는 개인정보 처리·산출물 검수·재수행 기준을 약속 | 약관·DPA·SLA 검토 담당자 지정 | **[미확인]** |

추가 확인: Git의 `lg@example.com`, Gmail, Naver 이메일로 표시된 기여가 모두 같은 권리자의 작업인지, 외부 기여가 있다면 상업 이용·재라이선스 동의를 받았는지 확인한다.

## 출시 전 게이트

- D1–D6 운영자 서면 확정
- 기여 권리 확인 후 루트 `LICENSE` 또는 명시적 proprietary notice 추가
- 이용약관·개인정보 처리방침·환불 정책의 법률 검토와 공개
- 선택 API 상업 계정, DPA, 지역·보관 옵션의 실제 계약 확인
- G04·G07·G13·G17·G22가 정의한 납품, 개인정보, 결제, tenant 격리 게이트 통과

## 다음 단계

1. 운영자가 D1–D6과 기여 권리를 확정한다.
2. 확정값을 반영해 루트 라이선스, 약관, 개인정보, 환불 문서를 작성한다.
3. 이 결정이 대기 중이어도 외부 판매를 제외한 G03–G07 로컬 개발을 계속한다.
