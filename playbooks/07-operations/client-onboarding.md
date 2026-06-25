# client-onboarding

> 신규 클라이언트를 0에서 세팅한다. **초보도 7개의 쉬운 질문에 답하면** `config.md`와
> `brand-guidelines.md`가 **먼저 생성**되고, 그다음에 리서치·경쟁사 분석으로 자동 보강한다.

## 핵심 원칙 — 순환 의존성 제거

기존 문제: 거의 모든 에이전트가 `config.md` / `brand-guidelines.md`가 이미 있다고 전제하는데,
정작 그 파일을 만드는 작업이 온보딩이었다 → 신규 클라이언트가 첫 실행에서 가장 불안정한
경로를 만나는 **순환 의존성**.

해결: **7개 평문 질문 답변으로 `config.md`·`brand-guidelines.md`를 먼저 생성**한 뒤에만
researcher·competitor·strategist 같은 다른 에이전트를 호출한다.

```
[Mode A] 7가지 평문 질문 → aicmo onboard → config.md + brand-guidelines.md + KB 생성  (전제조건 충족)
        ↓
[Mode B] researcher + competitor (병렬) → strategist → reporter  (config를 입력으로 보강)
```

---

## Mode A — 초보 위저드 (먼저 실행)

CMO가 **한 번에 하나씩, 쉬운 말로** 묻는다. 전문용어를 쓰지 않는다. 답이 막연하면 예시를 준다.
괄호 안 영문은 어떤 마케팅 항목을 채우는지 표시이며, 사용자에게는 보여주지 않아도 된다.

### 7가지 평문 질문

1) 무엇을 파나요? 한 문장으로 알려 주세요. (→ Offer)
2) 누가 살까요? 가장 살 것 같은 사람 한 명을 묘사해 주세요. (→ ICP, 이상적 고객)
3) 그 사람이 당신을 만나기 전에 겪는 가장 큰 불편은 무엇인가요? (→ Problem)
4) 아무것도 안 하거나 지금 쓰는 것 대신 당신을 골라야 할 이유는요? (→ UVP, 차별점)
5) 그 사람들은 주로 어디서 시간을 보내거나 검색하나요? (→ Channel)
6) 결과를 본 고객 사례가 있나요? 한 개라도 좋아요. (→ Proof)
7) 처음 온 사람이 딱 하나 했으면 하는 행동은 무엇인가요? (→ CTA)

추가로 **회사명**과 **웹사이트**(있으면)를 받는다. 모르면 비워도 된다.
시장 유형(b2c=일반 소비자 / b2b=다른 회사 / both=둘 다)도 한 번 확인한다.

### 답을 파일로 — config.md를 먼저 생성

수집한 답을 `answers.json`으로 저장하고 스캐폴더를 실행한다. 이 단계가 끝나야 다른 작업을 시작한다.

```powershell
uv run aicmo onboard --client {slug} --from answers.json
```

`answers.json` 예시:

```json
{
  "client": "moms-candles",
  "company_name": "엄마의 양초",
  "offer": "작은 집을 위한 손수 부은 콩 왁스 향초",
  "audience": "원룸·작은 아파트에 사는, 그을음 없이 은은한 향을 원하는 사람",
  "problem": "싼 향초는 향이 인공적이고 작은 방을 그을음으로 채운다",
  "differentiator": "저그을음 콩 왁스와 작은 공간에 맞춘 향 배합",
  "channel": "인스타그램과 네이버 스마트스토어",
  "proof": "동네 마켓에서 200개를 팔았고 재구매 고객이 많다",
  "cta": "스마트스토어에서 첫 향초 주문하기",
  "market_type": "b2c"
}
```

생성물 (모두 전문용어 옆에 쉬운 설명이 붙고, 빈 placeholder가 없다):

```
clients/{slug}/config.md
clients/{slug}/brand-guidelines.md        ([AI 초안 — 검토 필요])
knowledge-base/{slug}/insights.md
knowledge-base/{slug}/winning-copy.md
knowledge-base/{slug}/lessons-learned.md
```

> 이미 있는 클라이언트를 덮어쓰려면 `--force`. 안전상 슬러그는 단일 경로 세그먼트만 허용된다.

### 다음에 뭐 할까 — 온보딩 후 안내 (필수)

세팅이 끝나면 CMO는 **다음 행동 2~3개를 쉬운 말로 제안**한다. 사용자가 막막해하지 않도록.

- "블로그 글 1편 써 볼까요?" (→ blog-article)
- "랜딩페이지 시안을 만들어 볼까요?" (→ landing-page)
- "경쟁사 3곳을 분석해 볼까요?" (→ competitor-monitoring)

---

## Mode B — 자동 보강 (config.md 생성 후에만)

`config.md`가 존재하면, 채워지지 않은 항목을 에이전트로 보강한다.

### 에이전트 조합

```
researcher + competitor (병렬) → strategist → reporter
```

- `researcher`: 웹사이트·검색 기반으로 회사 개요, 제품 라인업, 톤앤매너를 보강
- `competitor`: 상위 3~5개 경쟁사 포지셔닝·강약점 분석 (WebSearch)
- `strategist`: 3개월 액션 플랜 수립 (config의 목표·채널 입력)
- `reporter`: 산출물 취합 + KB 첫 인사이트 기록

### 보완 인터뷰 (온라인으로 못 채우는 항목만)

비공개 정보는 클라이언트에게 직접 확인하고, 모르면 `[미확인 — 인터뷰 필요]`로 둔다.

**공통**
- 월 마케팅 예산 범위 (모르면 비중 %만)
- 핵심 성과 지표(KPI)와 현재 수치 (예: 월 주문 수, 방문자, 전환율)
- 3개월 / 1년 목표
- 가격 공개 범위 (웹 공개 / 문의 시 / 미팅 시)

**B2C 추가**: 주요 판매 채널 비중, 객단가, 재구매 주기, 시즌 변동
**B2B 추가**: 평균 계약 규모(ACV)와 영업 주기, 의사결정 구조(단독/위원회/승인)

### 3개월 액션 플랜 (strategist)

- 1개월차: 기반(설정·감사·리서치) / 2개월차: 실행(콘텐츠·캠페인) / 3개월차: 최적화(데이터 개선)
- 월별 테마 + 주차별 액션 + 예상 KPI(보수적/목표/최적)

---

## 출력 경로

```
clients/{slug}/config.md                                  (Mode A 생성)
clients/{slug}/brand-guidelines.md                        (Mode A 생성, 검토 필요)
knowledge-base/{slug}/insights.md                         (Mode A 생성)
knowledge-base/{slug}/winning-copy.md                     (Mode A 생성)
knowledge-base/{slug}/lessons-learned.md                  (Mode A 생성)
clients/{slug}/copy-patterns.md                           (Mode B 보강, 선택)
clients/{slug}/pricing-rules.md                           (Mode B 보강, 선택)
outputs/{slug}/operations/onboarding-report-{YYYYMMDD}.md (Mode B 완료 리포트)
```

## 검증 면제

Mode A(스캐폴딩)는 결정론적 파일 생성이라 reviewer 게이트를 거치지 않는다.
Mode B의 전략·브랜드 산출물은 기존 규칙대로 reviewer 검증을 거친다.
