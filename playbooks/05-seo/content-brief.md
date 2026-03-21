# content-brief

## 목적

타겟 키워드를 기반으로 SERP 상위 10개를 분석하고 콘텐츠 갭을 도출하여, copywriter 에이전트가 바로 실행 가능한 수준의 콘텐츠 브리프를 생성한다.

## 에이전트 조합

```
seo-specialist → copywriter
```

- `seo-specialist`: SERP 분석, 콘텐츠 갭 도출, 브리프 초안 작성
- `copywriter`: 브리프 검토 및 실제 콘텐츠 작성 시 활용

## 입력

```
BRAND: {client}              # 브랜드명
TARGET_KEYWORD: {keyword}   # 타겟 키워드 (예: 기업 화환 배달 서울)
CONTENT_TYPE: {type}        # 콘텐츠 유형 (blog/product-page/landing-page/faq)
TARGET_WORD_COUNT: {count}  # 목표 글자 수 (예: 2000, 기본값: SERP 평균 +20%)
BRAND_VOICE: {voice}        # 브랜드 톤앤매너 (clients/{client}/brand-guidelines.md 참조)
```

## 참조 문서

- `clients/{client}/brand-guidelines.md` — 브랜드 보이스, 금지어
- `clients/{client}/config.md` — ICP, 타겟 페르소나
- `knowledge-base/{client}/winning-copy.md` — 성과 낸 카피 패턴
- `playbooks/05-seo/keyword-research.md` — 연계 클러스터 키워드

## 프레임워크

### Phase 1: SERP 상위 10개 분석

```
WebSearch("{target_keyword}") 실행 후 상위 10개 결과 분석:

각 결과에 대해:
1. URL + 도메인
2. 페이지 제목 (title)
3. 콘텐츠 유형 (블로그/상품페이지/가이드/리스트클)
4. 예상 분량 (짧음<800자 / 보통 800-2000자 / 긺>2000자)
5. 주요 H2 소제목 (목차 구조)
6. 특이점 (독자 후기, FAQ, 인포그래픽 등)
```

### Phase 2: 콘텐츠 갭 분석 (Content Gap)

```
갭 유형:
A. 주제 갭 (Topic Gap):
   - 경쟁 상위 콘텐츠들이 다루지 않는 주제
   - 독자 댓글/Q&A에서 반복되는 미답변 질문

B. 깊이 갭 (Depth Gap):
   - 경쟁 콘텐츠가 표면적으로만 다루는 항목
   - 수치/사례/비교 없이 설명만 하는 항목

C. 포맷 갭 (Format Gap):
   - 상위 결과에 없는 콘텐츠 형식 (테이블/체크리스트/계산기)

D. 최신성 갭 (Freshness Gap):
   - 오래된 정보 (2년 이상) 업데이트 필요 항목

갭 우선순위: A > B > C > D
```

### Phase 3: 검색의도 정렬

```
해당 키워드의 검색의도 확인:
- 정보성: "X를 알고 싶다" → 교육적 내용 중심
- 상업적 조사: "X를 비교하고 싶다" → 비교표, 추천 이유 중심
- 거래성: "X를 구매하고 싶다" → CTA, 가격, 절차 중심

검색의도에 맞는 CTA 설계:
- 정보성 → 뉴스레터 구독, 관련 글 보기
- 상업적 조사 → 무료 상담, 견적 요청
- 거래성 → 바로 구매, 오늘 주문하기
```

### Phase 4: 브리프 구조 설계

```
필수 포함 요소:
1. 제안 제목 (3개 옵션)
2. 메타 설명 초안
3. H1 (페이지 헤딩)
4. H2 목차 구조 (섹션별 설명)
5. 필수 포함 주제 (MUST-HAVE)
6. 차별화 포인트 (경쟁 대비)
7. 타겟 키워드 + LSI 키워드 삽입 가이드
8. 참조 URL (벤치마크 3-5개)
9. 목표 분량
10. CTA 설계
```

## 출력 템플릿

```markdown
# 콘텐츠 브리프 — {target_keyword}
**작성일**: {date}
**브랜드**: {client}
**담당**: seo-specialist → copywriter

---

## 1. 개요

| 항목 | 내용 |
|-----|-----|
| 타겟 키워드 | {target_keyword} |
| 검색의도 | {intent} |
| 콘텐츠 유형 | {content_type} |
| 목표 분량 | {word_count}자 |
| 발행 목표일 | {publish_date} |

---

## 2. 제안 제목 (3개 옵션)

1. {title_option_1}
2. {title_option_2}
3. {title_option_3}

**추천**: {recommended_title} — 이유: {reason}

---

## 3. 메타 설명 초안

```
{meta_description} (현재 {n}자 / 목표 120-160자)
```

---

## 4. H1 헤딩

```
{h1_heading}
```

---

## 5. H2 목차 구조

| # | H2 소제목 | 다룰 내용 | 필수 포함 요소 | 예상 분량 |
|--|---------|---------|------------|---------|
| 1 | {h2_1} | {content} | {must_include} | {length} |
| 2 | {h2_2} | {content} | {must_include} | {length} |
| 3 | {h2_3} | {content} | {must_include} | {length} |
| 4 | {h2_4} | {content} | {must_include} | {length} |
| 5 | {h2_5} | {content} | {must_include} | {length} |

---

## 6. 콘텐츠 갭 — 차별화 포인트 (MUST-HAVE)

경쟁 상위 콘텐츠에 없는 내용으로 반드시 포함:

1. **{gap_1}**: {description}
2. **{gap_2}**: {description}
3. **{gap_3}**: {description}

---

## 7. 키워드 삽입 가이드

| 키워드 | 삽입 위치 | 빈도 |
|-------|---------|-----|
| {target_keyword} | 제목, H1, 첫 단락, 마지막 단락 | 3-5회 |
| {lsi_kw_1} | H2, 본문 자연스럽게 | 2-3회 |
| {lsi_kw_2} | 본문 | 1-2회 |

---

## 8. 참조 URL (벤치마크)

1. {url_1} — {reason_why_reference}
2. {url_2} — {reason_why_reference}
3. {url_3} — {reason_why_reference}

---

## 9. CTA 설계

- **주요 CTA**: {main_cta_text} → {destination_url}
- **보조 CTA**: {secondary_cta_text} → {destination_url}
- **CTA 위치**: {위치 설명 — 예: 본문 중간 + 하단}

---

## 10. 작성 유의사항

- 브랜드 보이스: {brand_voice}
- 금지 표현: {prohibited_words}
- 필수 포함 사실: {required_facts}
- 이미지 권장: {image_suggestions}
```

## 출력 경로

```
outputs/{client}/seo/content-brief-{slug}-{YYYYMMDD}.md
```
