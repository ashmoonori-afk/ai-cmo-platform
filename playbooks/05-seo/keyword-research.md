# keyword-research

## 목적

시드 키워드에서 출발하여 SERP 분석 → 검색의도 분류 → 클러스터링 → 콘텐츠 로드맵을 생성한다.
브랜드의 SEO 전략적 기반이 되는 키워드 포트폴리오를 구축한다.

## 에이전트 조합

```
seo-specialist
```

단일 에이전트. SERP 분석은 WebSearch 도구 활용.

## 입력

```
BRAND: {client}               # 브랜드명 (예: sample-client-a)
SEED_KEYWORDS: {keywords}    # 시드 키워드 목록 (쉼표 구분, 예: 기업화환, 축하화환, 꽃배달)
INDUSTRY: {industry}         # 업종 (예: 꽃배달, B2B 선물)
TARGET_REGION: {region}      # 지역 (예: 서울, 전국)
LANGUAGE: ko                 # 검색 언어 (기본값: ko)
```

## 참조 문서

- `clients/{client}/config.md` — ICP, 경쟁사 정보
- `knowledge-base/{client}/insights.md` — 기존 SEO 인사이트
- `playbooks/05-seo/content-brief.md` — 클러스터별 브리프 생성 시 연계

## 프레임워크

### Phase 1: 시드 키워드 확장 (Seed Expansion)

```
1. 시드 키워드 목록 수집 (사용자 입력)
2. 연관 키워드 생성 규칙:
   - 브랜드 키워드: [브랜드명] + [제품/서비스]
   - 카테고리 키워드: 상위 범주 + 하위 범주
   - 롱테일 키워드: [지역] + [상황] + [제품]
   - 경쟁사 키워드: 경쟁사명 + 대안/비교
3. WebSearch로 자동완성 패턴 수집:
   - "[시드키워드] 추천"
   - "[시드키워드] 가격"
   - "[시드키워드] 후기"
   - "best [시드키워드]"
```

### Phase 2: SERP 분석 (SERP Analysis)

각 키워드에 대해 WebSearch 실행 후 분석:

```
분석 항목:
- 상위 10개 결과 URL + 도메인
- 콘텐츠 유형 (블로그/상품페이지/리스트/뉴스)
- 경쟁 강도 (도메인 다양성, 전문 SEO 여부)
- SERP 특수 피처 (AI 오버뷰/쇼핑/지식패널/이미지팩)
- 예상 검색량 (상대적: 高/中/低)

AI 표면 확인 (2026-07 추가 — 근거: docs/research/2026-07-02-seo-geo-research.md):
- 네이버 스마트블록 구성: 해당 키워드 검색 시 생성되는 블록 주제 기록
  (블록 세부 주제에 맞춘 콘텐츠가 공략법)
- 네이버 AI 브리핑 트리거 여부 (통합검색 쿼리 20%+에 적용, 2025-12 기준)
- 구글 AI Overviews / AI 모드 트리거 여부
  (AIO 존재 시 1위 CTR −58% — 클릭 기대치 하향, 대신 "인용 노출" 목표로 전환)
```

### Phase 3: 검색의도 분류 (Intent Classification)

```
정보성 (Informational):
  - 패턴: "~란", "~방법", "~이유", "추천", "비교"
  - 목적: 블로그 포스트, 가이드, FAQ

탐색성 (Navigational):
  - 패턴: 브랜드명, 사이트명, 특정 페이지
  - 목적: 브랜드 페이지, 랜딩 페이지

거래성 (Transactional):
  - 패턴: "구매", "주문", "가격", "배달", "예약"
  - 목적: 상품 페이지, 구매 CTA 강화

상업적 조사 (Commercial Investigation):
  - 패턴: "후기", "비교", "vs", "순위", "추천"
  - 목적: 비교 페이지, 리뷰 콘텐츠

AI 질문형 (AI-Conversational) — 2026-07 추가:
  - 패턴: 자연어 질문 ("~는 어떻게 해야 하나요", "~와 ~중 뭐가 나을까")
  - 목적: AI 검색(ChatGPT/Perplexity/AI 브리핑) 인용 타깃 콘텐츠
  - 구조: 직답 문단 + 통계·인용문·출처 (prompts/shared/geo-checklist.md 적용)
```

### Phase 4: 클러스터링 (Keyword Clustering)

```
클러스터 기준:
1. 주제 유사성 (같은 페이지로 타겟팅 가능)
2. 검색의도 일치성
3. 경쟁 강도 그룹 (진입 가능 vs 고경쟁)

클러스터 구조:
- Pillar 키워드 (클러스터 대표, 검색량 高)
- Supporting 키워드 (세부 지원, 롱테일)
- LSI 키워드 (의미적 연관어, 본문 삽입용)
```

### Phase 5: 우선순위 스코어링 (Priority Scoring)

```
점수 산정 (총 100점):
- 검색량 (40점): 高=40, 中=25, 低=10
- 경쟁 강도 (30점): 낮음=30, 보통=20, 높음=10
- 비즈니스 관련성 (20점): 핵심=20, 연관=10, 주변=5
- 전환 가능성 (10점): 거래성=10, 상업적조사=7, 정보성=3

감점 요인 (2026-07 추가):
- 제로클릭 리스크: AI 오버뷰/AI 브리핑이 강하게 뜨는 정보성 키워드는 −5~10점
  (클릭 유입 기대치 하락 — 단, 브랜드 인용 노출 목표면 감점 대신 "GEO 타깃" 태그)
```

### Phase 6: 콘텐츠 로드맵 매핑

```
월별 배포 계획:
- 1개월차: 전환성 높은 거래성 키워드 (Quick Win)
- 2개월차: 상업적 조사 키워드 (중간 퍼널)
- 3개월차: 정보성 키워드 (인지도 확장)
- 이후: 고경쟁 Pillar 키워드 (장기 투자)
```

## 출력 템플릿

```markdown
# 키워드 리서치 리포트 — {client}
**작성일**: {date}
**담당자**: seo-specialist

---

## 1. 키워드 클러스터 테이블

| 클러스터명 | Pillar 키워드 | Supporting 키워드 | 검색의도 | 검색량 | 경쟁도 | 우선순위 점수 |
|-----------|--------------|------------------|---------|-------|-------|------------|
| {cluster} | {pillar_kw}  | {supporting_kws} | {intent}| {vol} | {comp}| {score}/100|

---

## 2. SERP 경쟁 분석

### {클러스터명}
- **Pillar 키워드**: {keyword}
- **상위 결과 유형**: {content_types}
- **주요 경쟁 도메인**: {domains}
- **SERP 피처**: {features}
- **공략 전략**: {strategy}

---

## 3. 콘텐츠 매핑

| 페이지 타입 | 타겟 키워드 | 검색의도 | 권장 포맷 | 예상 분량 |
|-----------|-----------|---------|---------|---------|
| {page_type}| {keywords}| {intent}| {format}| {length}|

---

## 4. 우선순위 콘텐츠 로드맵

### 1개월차 (Quick Win — 거래성)
- [ ] {content_1}: {target_keyword}
- [ ] {content_2}: {target_keyword}

### 2개월차 (중간 퍼널 — 상업적 조사)
- [ ] {content_3}: {target_keyword}
- [ ] {content_4}: {target_keyword}

### 3개월차 (인지도 — 정보성)
- [ ] {content_5}: {target_keyword}
- [ ] {content_6}: {target_keyword}

### 4개월차 이후 (장기 투자 — Pillar)
- [ ] {pillar_content}: {pillar_keyword}

---

## 5. LSI 키워드 뱅크

| 주제 | LSI 키워드 목록 |
|-----|--------------|
| {topic} | {lsi_keywords} |
```

## 출력 경로

```
outputs/{client}/seo/{YYYYMMDD}_keyword-research.md
```
