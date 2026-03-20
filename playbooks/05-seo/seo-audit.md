# seo-audit

## 목적

기술적 SEO + 콘텐츠 SEO + GEO(AI 검색 최적화)를 종합 진단하여 100점 스코어카드와 우선순위 개선 로드맵을 생성한다.
참조: `플라워플러스-GEO-실행가이드.md` 패턴 활용.

## 에이전트 조합

```
seo-specialist
```

단일 에이전트. WebSearch 및 페이지 분석 도구 활용.

## 입력

```
BRAND: {brand}          # 브랜드명
SITE_URL: {url}         # 감사 대상 사이트 URL (예: https://flowerplus.co.kr)
PAGES_TO_AUDIT: {pages} # 감사할 주요 페이지 목록 (선택, 기본: 홈+상위 5개)
FOCUS: {focus}          # 중점 영역 (technical/content/geo/all, 기본: all)
```

## 참조 문서

- `플라워플러스-GEO-실행가이드.md` — GEO 감사 항목 및 채점 기준
- `clients/{brand}/config.md` — 브랜드 컨텍스트, ICP
- `knowledge-base/{brand}/insights.md` — 이전 감사 기록

## 프레임워크

### 영역 1: 기술적 SEO (Technical SEO) — 35점

```
1-1. HTML 기초 (10점)
  [ ] HTML lang 속성 존재 (2점)
  [ ] 모든 페이지 meta description 유무 (2점)
  [ ] meta description 길이 120-160자 (1점)
  [ ] title 태그 최적화 (브랜드+키워드, 50-60자) (2점)
  [ ] canonical 태그 설정 (1점)
  [ ] Open Graph / Twitter Card 메타 (2점)

1-2. 구조적 마크업 (8점)
  [ ] H1 태그 단일 사용 (2점)
  [ ] H2~H6 논리적 계층 구조 (2점)
  [ ] Schema.org 구조화 데이터 (Organization/Product/FAQ) (4점)

1-3. 크롤링 & 인덱싱 (8점)
  [ ] sitemap.xml 존재 및 제출 여부 (2점)
  [ ] robots.txt 적절한 설정 (2점)
  [ ] 404/301 오류 페이지 처리 (2점)
  [ ] 중복 콘텐츠 여부 (www/non-www, http/https) (2점)

1-4. 성능 & 모바일 (9점)
  [ ] 페이지 로딩 속도 (Core Web Vitals: LCP < 2.5s) (3점)
  [ ] 모바일 친화성 (Google Mobile-Friendly Test) (3점)
  [ ] HTTPS 적용 여부 (2점)
  [ ] 이미지 alt 텍스트 (1점)
```

### 영역 2: 콘텐츠 SEO (Content SEO) — 35점

```
2-1. 키워드 최적화 (12점)
  [ ] 주요 키워드 URL 포함 (2점)
  [ ] 키워드 title/H1 자연스러운 포함 (3점)
  [ ] 본문 내 키워드 밀도 (1-2%, 과도하지 않게) (3점)
  [ ] LSI 키워드 / 동의어 활용 (2점)
  [ ] 롱테일 키워드 커버리지 (2점)

2-2. 콘텐츠 품질 (13점)
  [ ] 콘텐츠 분량 (경쟁 대비 충분한 깊이) (3점)
  [ ] 독자 질문에 직접 답변하는 구조 (3점)
  [ ] 최신성 (업데이트 날짜 표시) (2점)
  [ ] 이미지/비디오 등 멀티미디어 활용 (2점)
  [ ] FAQ 섹션 존재 (3점)

2-3. 내부 링크 구조 (10점)
  [ ] Pillar → Supporting 페이지 내부 링크 (4점)
  [ ] 앵커 텍스트 키워드 포함 (3점)
  [ ] 고아 페이지 (orphan pages) 없음 (3점)
```

### 영역 3: GEO — AI 검색 최적화 (30점)

```
3-1. AI 인용 가능성 구조 (10점)
  [ ] 명확한 주제 문장 (첫 단락에 핵심 답변) (3점)
  [ ] Q&A 형식 콘텐츠 (AI가 직접 인용하기 쉬운 구조) (3점)
  [ ] 정의/설명 문단 존재 ("X란 Y이다" 형식) (2점)
  [ ] 통계/수치 데이터 포함 (출처 명시) (2점)

3-2. E-E-A-T 신호 (10점)
  [ ] About 페이지 상세 정보 (브랜드 스토리, 팀) (2점)
  [ ] 리뷰/후기 집계 페이지 (2점)
  [ ] 수상 내역 / 인증 / 언론 보도 (2점)
  [ ] 저자 정보 (전문성 증명) (2점)
  [ ] NAP (Name/Address/Phone) 일관성 (2점)

3-3. 기술적 GEO (10점)
  [ ] JSON-LD Schema (Organization, LocalBusiness, Product) (4점)
  [ ] 사이트맵 Hreflang (다국어인 경우) (2점)
  [ ] 브랜드 언급 모니터링 체계 (2점)
  [ ] AI 크롤러 차단 여부 확인 (robots.txt) (2점)
```

### 점수 산정 및 등급

```
90-100점: 최적화 완료 (Excellent)
75-89점:  양호 (Good) — 소규모 개선 필요
60-74점:  보통 (Fair) — 중요 항목 개선 필요
40-59점:  미흡 (Poor) — 즉각 개선 필요
0-39점:   위험 (Critical) — 전면 재설계 필요
```

### 개선 우선순위 프레임워크

```
Priority 1 (즉시 — 1주 이내):
  - 0점 항목 중 구현 난이도 낮음 (HTML 수정 수준)

Priority 2 (단기 — 1개월 이내):
  - 0점 항목 중 구현 난이도 중간 (콘텐츠 작성/Schema 추가)

Priority 3 (중기 — 3개월 이내):
  - 부분 점수 항목 완전 충족
  - 구현 난이도 높음 (사이트 구조 변경)
```

## 출력 템플릿

```markdown
# SEO 감사 리포트 — {brand}
**감사 일자**: {date}
**대상 URL**: {site_url}
**담당자**: seo-specialist

---

## 종합 스코어카드

| 영역 | 만점 | 획득 | 비율 | 등급 |
|-----|-----|-----|-----|-----|
| 기술적 SEO | 35 | {score} | {pct}% | {grade} |
| 콘텐츠 SEO | 35 | {score} | {pct}% | {grade} |
| GEO | 30 | {score} | {pct}% | {grade} |
| **합계** | **100** | **{total}** | **{pct}%** | **{grade}** |

> **현재 상태**: {total}점 / 100점 — {grade_label}

---

## 영역별 상세 감사

### 기술적 SEO ({score}/35)

| 항목 | 점수 | 상태 | 메모 |
|-----|-----|-----|-----|
| HTML lang 속성 | {s}/2 | {status} | {note} |
| meta description | {s}/2 | {status} | {note} |
| ... | | | |

### 콘텐츠 SEO ({score}/35)

| 항목 | 점수 | 상태 | 메모 |
|-----|-----|-----|-----|
| 키워드 최적화 | {s}/12 | {status} | {note} |
| ... | | | |

### GEO ({score}/30)

| 항목 | 점수 | 상태 | 메모 |
|-----|-----|-----|-----|
| AI 인용 가능성 | {s}/10 | {status} | {note} |
| ... | | | |

---

## 우선순위 개선 로드맵

### Priority 1 — 즉시 실행 (1주 이내)
1. **{task}**: {description}
   - 예상 점수 향상: +{pts}점
   - 구현 방법: {how_to}

### Priority 2 — 단기 실행 (1개월)
1. **{task}**: {description}
   - 예상 점수 향상: +{pts}점

### Priority 3 — 중기 실행 (3개월)
1. **{task}**: {description}
   - 예상 점수 향상: +{pts}점

---

## 개선 후 예상 점수

| 시점 | 예상 점수 | 등급 |
|-----|---------|-----|
| 현재 | {current}/100 | {grade} |
| 1주 후 | {w1}/100 | {grade} |
| 1개월 후 | {m1}/100 | {grade} |
| 3개월 후 | {m3}/100 | {grade} |
```

## 출력 경로

```
outputs/{brand}/seo/seo-audit-{YYYYMMDD}.md
```
