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

## Mode A — 상담 인테이크 (먼저 실행)

CMO가 **한 번에 하나씩, 쉬운 말로** 묻는다. 전문용어를 쓰지 않는다. 답이 막연하면 예시를 준다.
괄호 안 영문은 어떤 마케팅 항목을 채우는지 표시이며, 사용자에게는 보여주지 않아도 된다.

### 상담 진행 수칙 (50-60대 클라이언트 기준)

1. **워밍업으로 시작**: "질문 10개만 드릴게요. 어려운 말은 하나도 없고, 답하신 내용으로 전략·홈페이지·문안까지 저희가 만들어 드립니다." — 왜 묻는지 먼저 설명한다.
2. **한 번에 한 질문**: 묶어서 묻지 않는다. 답을 기다린다. 서두르지 않는다.
3. **전문용어 금지**: ICP·UVP·채널·퍼널·CTA 같은 단어를 입 밖에 내지 않는다. 아래 질문 문구를 그대로 쓴다.
4. **"모르겠다"는 정상**: 모든 질문에 대비용 예시와 대안이 있다 (각 질문의 └ 참고). 억지로 답을 받아내지 않는다.
5. **확인 루프 (필수)**: 10문항이 끝나면 이해한 내용을 쉬운 말로 요약해서 들려주고 "제가 이해한 게 맞나요?"를 확인받는다. 틀린 부분은 그 자리에서 고친다.
6. **다음 단계 예고**: "이제 저희가 시장 조사부터 홈페이지 시안까지 순서대로 만들어서 보여드릴 겁니다"라고 마무리한다.

### 핵심 질문 7개 (answers.json에 들어가는 항목)

1) 무엇을 파나요? 한 문장으로 알려 주세요. (→ Offer)
   └ 막히면: "손님이 돈을 내고 가져가는 게 뭔가요?"
2) 이걸 가장 반길 손님은 어떤 분인가요? 나이, 하는 일, 요즘 걱정거리 하나를 떠올려 주세요. (→ ICP / answers.json 키: `audience`)
   └ 막히면: "지금까지 온 손님 중 기억나는 한 분을 말씀해 주세요."
3) 그 손님이 당신을 만나기 전에 겪는 가장 큰 불편은 무엇인가요? (→ Problem)
4) 손님이 다른 가게(또는 그냥 안 사는 것) 대신 당신을 골라야 할 이유 하나만 꼽는다면요?
   가격, 품질, 편리함, 정성 — 뭐든 좋습니다. (→ UVP)
   └ 막히면: "단골이 '여기는 이게 달라'라고 말한 적 있나요?"
5) 손님들은 뭘 보고 정보를 얻나요? 예: 네이버 검색, 유튜브, 인스타그램, 동네 소문, 전단지. (→ Channel)
   └ 막히면: "본인이라면 이런 가게를 어떻게 찾으실 것 같으세요?"
6) "이 집 덕 봤다"는 손님 이야기가 있나요? 한 개라도 좋아요. (→ Proof)
   └ 없으면: "괜찮습니다. 그 자리는 저희가 업계 자료로 채우고, 생기는 대로 바꿔 드립니다." — proof에 "아직 없음 — 업계 자료로 대체"라고 적는다. 지어내지 않는다.
7) 처음 온 손님이 딱 하나 했으면 하는 행동은 무엇인가요?
   예: 전화 주기, 매장 방문, 주문 버튼 누르기. (→ CTA)

추가로 **회사명**과 **웹사이트**(있으면)를 받는다. 모르면 비워도 된다.
시장 유형도 쉬운 말로 확인한다: "손님이 일반 개인인가요, 회사인가요, 둘 다인가요?" (b2c / b2b / both)

### 상담 질문 3개 (상담 메모에 기록 — 채널믹스·Lite 판정 입력)

8) 이 일은 몇 명이서 하나요? (혼자 / 가족 / 직원 N명) — 운영 여력 파악
9) 한 달에 마케팅에 쓸 수 있는 돈은 어느 정도인가요? 대략이면 되고, 0원이어도 됩니다. — Lite 모드 판정(월 100만 원 이하)
10) 손님이 주로 오는 곳은 어디인가요 — 가게(오프라인), 온라인, 둘 다? — 채널믹스 입력

8~10번 답은 `answers.json`에 넣지 않고 `clients/{slug}/consultation-notes.md`에 기록한다
(형식 자유, 날짜 + 3문항 답 + 특이사항). 이후 channel-strategy·launch-pack 실행 시 반드시 참조한다.

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

세팅이 끝나면 CMO는 **다음 행동을 쉬운 말로 제안**한다. 사용자가 막막해하지 않도록.

- **신규 사업(또는 "마케팅 전부 해줘")이면 기본 경로는 런치팩**: "이제 전략 → 채널 → 문안 → 브랜드 → 홈페이지 순서로 한 번에 만들어 드릴까요?" (→ `playbooks/00-chains/launch-pack.md`)
- 단일 산출물만 원하면:
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
clients/{slug}/consultation-notes.md                      (Mode A 상담 메모 — 8~10번 답)
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
