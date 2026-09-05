# G02 한국·미국 현행 기준 재검토 근거

## 한 장 요약

확인일은 **2026-09-06 KST**다. 한국 법령, 미국 연방 기준과 캘리포니아 주요 규정, 공급자 공식 문서를 재검토했다. G02는 **OPEN**이다. 이 문서는 제품 설계의 근거이며, 실제 사업 조건에 대한 적용 판단이나 계약 체결의 증거는 아니다. 오늘 할 일은 [실행 TODO](../product/2026-09-06-g02-kr-us-review-todolist.ko.md)의 T01 적용 범위 표를 준비하는 것이다.

판매 주·계약 주체·고객 유형·실제 데이터 흐름은 **[미확인]**이다. 미국 50개 주 검토 완료를 의미하지 않는다. 아래의 법률, 하위 규정, 기관 안내, 계약 정책을 서로 구분한다. 시행일과 열람일도 구분하며, 예정·제안 규정을 시행 중 규정으로 취급하지 않는다. 클라이언트 납품물이 아닌 플랫폼 연구이므로 고객 config·브랜드 기준은 적용하지 않는다.

## 한국 기준

| ID | 공식 근거·버전 | 확인 내용과 적용 한계 | 연결 |
|---|---|---|---|
| KR01 | [전자상거래법 제3조](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1027062979), 현행 법률 시행 2026-07-21 | 상행위 목적의 사업자 구매는 원칙적으로 적용 제외지만, 사실상 소비자와 같은 지위·거래조건인 경우 예외가 있다. 소상공인/B2B 표시만으로 일괄 제외할 수 없다. | T01, T10 |
| KR02 | [전자상거래법 시행령 제6조](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=63460), 현행 시행령 시행 2026-07-21 | 적용 대상의 표시·광고 기록 6개월, 계약·청약철회 기록 5년, 대금결제·공급 기록 5년, 불만·분쟁 기록 3년. 이 기간을 모든 고객 원문/AI 산출물의 보관기간으로 확장하지 않는다. | T06, T10 |
| KR03 | [개인정보 보호법 제28조의8 제1항](https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1029331979), 현행 법률 시행 2025-10-02 | 국외 제공·조회·위탁·보관을 포함한다. 별도 동의 외에도 법률, 정보주체 계약에 필요한 위탁·보관과 공개/통지 등 조건부 근거가 있다. 사업주와의 계약이 그 가게 고객 정보의 이전 근거까지 자동 충족하지 않는다. 구체적 고지 항목·위탁 계약·안전조치는 T04에서 함께 확정한다. | T03–T07 |
| KR04 | [AI 기본법 제31조 제1항](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1031809549) 및 [제2항](https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1031810729), 현행 법률 시행 2026-07-21 | 해당 사업자의 고영향/생성형 AI 기반 제품·서비스 사전 고지와 생성형 AI 결과물 표시 의무를 검토해야 한다. 적용 주체·콘텐츠 종류·제공 방식 판단이 필요하다. 모든 마케팅 문구에 동일한 워터마크를 붙이라는 결론은 도출하지 않았다. | T08 |
| KR05 | [정보통신망법 제50조 제1항](https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1030434423), 현행 법률 시행 2026-07-07 | 전자적 전송매체의 영리 목적 광고성 정보는 명시적 사전 동의가 원칙이며 조문상 예외가 있다. 일반 약관 동의나 공개 연락처를 광고 수신 동의로 대체하지 않는다. 매체·시간·예외·수신거부의 세부 요건은 T12에서 확인한다. | T12 |

추가 원문 검증이 필요한 항목: [AI 기본법 시행령](https://www.law.go.kr/LSW/lsInfoP.do?ancYnChk=0&chrClsCd=010202&efYd=20260820&lsiSeq=288781&urlMode=lsInfoP)은 현행판 시행일 2026-08-20까지 확인했으나 도구가 본문 조항을 반환하지 않았다. [추천·보증 표시·광고 심사지침](https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000280130&chrClsCd=010201)도 현재 연결 페이지의 본문·개정일을 충분히 확보하지 못했다. 세부 표시 방법·예외는 **[미확인]**, T08/T09에 남긴다. 계도기간은 법 시행의 부재를 의미하지 않는다.

## 미국 기준

| ID | 공식 근거·버전 | 확인 내용과 적용 한계 | 연결 |
|---|---|---|---|
| US01 | [연방 규제 현황: Negative Option Rule](https://www.reginfo.gov/public/do/eAgendaViewRule?RIN=3084-AB84&pubId=202510), 2026-02-12 최종 규칙 및 2026-03-13 ANPRM 기록 | 2024년 개정 규칙의 법원 취소를 반영해 이전 규칙 문구로 복귀했다. 새 ANPRM은 제안 절차다. 2024년 click-to-cancel을 현행 미국 전역 의무로 인용하지 않는다. | T10, T11 |
| US02 | [FTC ROSCA 설명](https://www.ftc.gov/business-guidance/blog/2018/07/time-rosca-recap-ftc-says-risk-free-trial-was-risky-not-free), 2018-07; [15 USC 8403 현행 본문](https://uscode.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title15-section8403), 2026-09-03 반영본 | 온라인 소비자 반복청구의 중요 조건 사전 공개, 명시적 informed consent, 간단한 반복청구 중단 수단. US01의 규칙 취소와 별개 법률이다. 최초 열람 timeout 후 독립 reviewer가 House의 현행 본문 전체를 확인했다. | T10, T11 |
| US03 | [California AG 자동갱신법 안내](https://oag.ca.gov/news/press-releases/attorney-general-bonta-issues-consumer-alert-california%E2%80%99s-automatic-renewal-law), 2025-09-04; 개정 시행 2025-07-01 | 소비자 자동갱신에 명시적 동의, 온라인 가입의 온라인 해지, 연간 알림, 기간·체험·요금 변경별 조건부 통지가 있다. 캘리포니아 소비자 규정을 모든 미국 B2B 계약에 일괄 적용하지 않는다. | T01, T11 |
| US04 | [CCPA 정의 조항 1798.140](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=1798.140.&lawCode=CIV), 현행; [CPPA 조정 금액](https://cppa.ca.gov/regulations/cpi_adjustment.html), 2025-01-01 시행 | 해당 영리 사업자 판단에서 매출 기준은 조정 후 **$26,625,000 초과**다. 별도로 연간 10만 소비자/가구 정보의 매입·판매·공유, 매출 50% 이상 판매·공유 등 경로가 있다. 관계회사·계약상 service provider 지위도 별도 확인한다. 단순 방문자 10만 명 기준이 아니다. | T01, T07 |
| US05 | [California AG CCPA FAQ](https://oag.ca.gov/privacy/ccpa), 페이지 갱신 2026-08-28 | B2B 개인정보의 일시적 예외는 2022-12-31 종료. FAQ의 종전 $25m 표기는 US04의 법정 물가 조정 금액으로 보완한다. 권리 요청·판매/공유 거부·GPC의 실제 의무는 사업자 지위와 처리 방식별로 판단한다. | T07 |
| US06 | [FTC 후기·추천 규칙 Q&A](https://www.ftc.gov/business-guidance/resources/consumer-reviews-testimonials-rule-questions-answers), 규칙 시행 2024-10-21 | 실제 경험을 허위로 표시하는 AI 후기, 특정 긍정/부정 평가를 조건으로 매수하는 후기 등 금지 유형이 있다. AI 사용이나 대가를 공개해도 가짜 경험 자체가 정당화되지 않는다. 실제 후기 답글과 신규 가짜 후기 생성을 구분한다. | T09 |
| US07 | [FTC CAN-SPAM 사업자 안내](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business), 2023-08 안내/2024-01 편집 표기 | B2B 상업 이메일도 대상이다. 정확한 발신·제목, 광고 식별, 유효한 우편주소, 쉬운 거부 절차와 10영업일 내 처리 등이 필요하다. 거래성 이메일은 주된 목적에 따라 구분한다. SMS/TCPA 규정까지 검증한 것은 아니다. | T12 |
| US08 | [미국 저작권청 AI 보고서 Part 2 발표](https://www.copyright.gov/newsnet/2025/1060.html?loclr=licop), 2025-01-29 | 인간의 창작 기여에 따라 보호 가능성을 판단하며 프롬프트 제공만으로 충분하지 않다. 공급자 약관상 출력 소유와 저작권 성립·독점성은 다르다. | T02, T09 |
| US09 | [미 법무부 웹 접근성 안내](https://www.ada.gov/resources/web-guidance/), 2022-03-18 안내 | 장애인이 웹 서비스를 이용할 수 있도록 해야 하는 대상과 예시를 제시한다. 공공기관 Title II의 기술 기준·기한을 민간 SaaS의 일률적 법정 기한으로 옮기지 않는다. 키보드·폼 오류·대비·보조기술은 제품 기본 검증으로 채택한다. | T15 |

## 공급자 기준

| ID | 공식 근거·버전 | 확인 내용과 적용 한계 | 연결 |
|---|---|---|---|
| V01 | [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms), 시행 2025-06-17 | API의 고객 제품 통합 조건과 입·출력 권리 조항을 확인했다. 실제 계정·계약·입력 권리·허용 용도와 별개로 무조건적 상업 이용 보장을 하지 않는다. | T02, T03 |
| V02 | [Anthropic 조직 데이터 보관](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), 갱신 2026-07-01 | 일반 API 입·출력은 기본 30일 이내 삭제. Files, 별도 계약, 정책 집행, 법률, Covered Models 등의 예외가 있다. 서비스 전체를 '30일 뒤 모두 삭제' 또는 'ZDR'로 홍보할 근거가 아니다. | T03, T06 |
| V03 | [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data), 열람 2026-09-06; 페이지 고정 개정일 미표시 | 기본 비학습과 보관은 별개다. abuse monitoring logs, endpoint별 application state, Files 및 승인형 ZDR/MAM을 구분한다. Responses의 저장 상태와 store 설정, 파일 삭제 등 실제 사용 기능별 표가 필요하다. API 자료를 개인용 ChatGPT/Codex 계정 정책으로 일반화하지 않는다. | T03, T06 |

OpenAI 상업 계약·DPA의 실제 적용 버전과 계정은 T03에서 다시 확인한다. 과거 결정 기록의 Services Agreement 링크만으로 새 계약의 유효성까지 검증했다고 하지 않는다. 국내 세무·통신판매 신고, 미국 판매 주별 세금·AI·개인정보·자동갱신 추가 규정은 아직 적용 판단 전이며 T01/T14에 포함한다.

## 다음 단계

1. 제품·운영 담당은 다음 G02 작업 착수 시 판매 국가/주와 데이터 처리 역할을 T01 표로 정리한다.
2. 개발 담당은 정책 확정 전에도 T05의 합성 데이터 재현과 수정 설계를 준비한다.
3. 담당 검토자는 계약·출시 직전에 적용 법령 및 공급자 버전을 다시 확인하고 T16에 증거를 남긴다.
