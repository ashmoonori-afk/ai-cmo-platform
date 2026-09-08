# geo-visibility-monitor

## 목적

클라이언트 브랜드가 AI 검색 답변(ChatGPT, Google AI Overviews, Perplexity, Claude)에 실제로 인용되는지 모니터링하고, 인용 격차를 메우는 콘텐츠 액션을 제안한다. Okara GEO Agent에 해당하는 기능.

> 기존 자산과의 관계: `prompts/shared/geo-checklist.md`는 콘텐츠 **작성** 기준이고, 이 플레이북은 **노출 측정**이다. seo-audit의 GEO 섹션은 사이트 진단, 이 플레이북은 외부 AI 답변 추적.

## 에이전트 조합

```
seo-specialist → reviewer
```

## 입력

```
BRAND: {client}           # 브랜드명
QUERIES: {queries}        # 추적할 구매의도 쿼리 목록 (예: "서울 개업화환 추천") (선택 — 없으면 keyword-research 결과에서 도출)
COMPETITORS: {competitors} # 비교할 경쟁사 (선택, 기본: config.md의 경쟁사)
ENGINES: {engines}        # 대상 AI 엔진 (기본: chatgpt,perplexity,google-aio,claude)
```

## 참조 문서

- `clients/{client}/config.md` — 브랜드, 경쟁사
- `prompts/shared/geo-checklist.md` — 인용 최적화 기준 (액션 제안 시 근거)
- `outputs/{client}/seo/` — 이전 키워드 리서치/감사 결과
- `knowledge-base/{client}/insights.md` — 이전 가시성 스냅샷 (변화 추적)

## 절차

### 1단계: 추적 쿼리 세트 확정
- QUERIES 미지정 시: keyword-research 결과 + ICP 구매 여정에서 구매의도 쿼리 10-20개 도출
- 쿼리 유형 분류: 추천형("~추천"), 비교형("~vs~"), 정의형("~란"), 절차형("~하는 법")

### 2단계: AI 엔진별 가시성 프로브
- 각 쿼리를 대상 AI 엔진에 질의 (WebSearch/WebFetch로 접근 가능한 범위 + 실제 엔진 질의 결과는 사용자 제공 스크린샷/텍스트로 보완)
- 기록 항목:
  | 항목 | 내용 |
  |------|------|
  | 인용 여부 | 브랜드가 답변에 등장하는가 (Y/N) |
  | 인용 형태 | 출처 링크 / 이름 언급 / 없음 |
  | 인용된 경쟁사 | 대신 등장한 브랜드 |
  | 인용 출처 | AI가 참조한 페이지 (Reddit, 위키, 블로그 등) |
- 접근 불가한 엔진은 [미확인 — 수동 프로브 필요]로 표기하고 수동 체크리스트 제공

### 3단계: GEO 가시성 스코어카드
- 쿼리 × 엔진 매트릭스로 인용률 산출 (예: 20쿼리 × 4엔진 = 80셀 중 인용 N셀)
- 경쟁사 대비 상대 가시성 (Share of AI Voice) [추정]
- 이전 스냅샷 대비 변화 (KB에 이전 결과가 있을 때)

### 4단계: 격차 → 액션 매핑
- 인용 실패 쿼리별 원인 분류:
  | 원인 | 액션 |
  |------|------|
  | 해당 주제 콘텐츠 부재 | content-brief → blog-article로 연결 (GEO 체크리스트 적용) |
  | 콘텐츠는 있으나 인용 구조 아님 | geo-checklist 10항목 리라이트 지시 |
  | 외부 플랫폼 존재감 부재 (Reddit/위키/유튜브) | reddit-engagement, UGC 등 채널 액션 연결 |
  | AI 크롤러 차단 | technical-seo-fix로 robots.txt 수정 연결 |

## 출력

`outputs/{client}/seo/{YYYYMMDD}_geo-visibility-monitor.md`

```markdown
# GEO 가시성 리포트 — {client} {date}
## 스코어카드 (쿼리 × 엔진 인용 매트릭스)
## Share of AI Voice (경쟁사 비교) [추정]
## 인용 실패 TOP 5 쿼리 + 원인 + 액션
## 수동 프로브 체크리스트 (접근 불가 엔진)
## 이전 대비 변화
```

## KB 업데이트

- `knowledge-base/{client}/insights.md`에 스냅샷 요약 append (다음 실행 시 변화 추적 기준)

## 금지 사항

- 접근하지 못한 엔진의 결과를 지어내지 말 것 — [미확인] 태그 필수
- 인용률 수치는 프로브 시점 스냅샷임을 명시 (AI 답변은 비결정적)
