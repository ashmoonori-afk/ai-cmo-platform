# 상세페이지 디자인 플레이북

## 목적

제품 상세 설명을 위한 24섹션 풀스크롤 상세페이지의 디자인 디렉션을 생성한다. 6가지 핵심 기능을 Q&A 형식으로 상세 설명하고, 구매 전환까지의 흐름을 설계한다.

## 에이전트 조합

```
copywriter → designer → reviewer
```

| 순서 | 에이전트 | 역할 | 모델 |
|------|---------|------|------|
| 1 | copywriter | 24섹션 카피 작성 (6가지 핵심 기능 정의 포함) | sonnet |
| 2 | designer | 디자인 디렉션 + 섹션별 레이아웃 + 컬러 교차 | sonnet |
| 3 | reviewer | 구조/카피/디자인 품질 검증 | sonnet |

## 입력

| 항목 | 설명 | 필수 여부 |
|------|------|---------|
| `client` | 클라이언트 폴더명 | 필수 |
| `product_name` | 제품명 | 필수 |
| `core_features` | 6가지 핵심 기능 리스트 | 필수 |
| `target_audience` | 타겟 고객 | 필수 |
| `competitors` | 비교 경쟁사 (Comparison 섹션용) | 선택 |
| `price` | 가격 정보 | 선택 |

## 참조 문서

- `clients/{client}/config.md` — 제품 정보, ICP
- `clients/{client}/brand-guidelines.md` — 브랜드 컬러
- `agents/designer.md` — 24섹션 구조, Q&A 패턴, 다크모드 디자인

## 프레임워크

### 24섹션 구조

```
ATTENTION  → 01 Hook, 02 WhatIsThis, 03 BrandName
INTEREST   → 04 SetContents, 05 WhyCore
DESIRE     → 06 PainPoint, 07 Solution, 08 FeaturesOverview
DEEP DIVE  → 09-14 Feature1-6 Detail (Q&A x6)
TRUST      → 15 Tips, 16 Differentiator, 17 Comparison, 18 Safety
SOCIAL     → 19 Target, 20 Reviews
SPECS      → 21 ProductSpec, 22 FAQ
CONVERT    → 23 Warranty, 24 CTA
```

### 기능 상세 (09-14) Q&A 패턴

```
[72px 번호] → [Q. 왜 {기능}인가요?] → [A. {핵심 혜택}]
→ [이미지 760x350] → [혜택 제목] → [혜택 1-3] → [스펙 수치]
```

### 디자인 규칙

- 캔버스: 860px 너비
- 이미지 영역: 760px 너비
- 배경 교차: dark_1(#111111) / dark_2(#1A1A1A) / brand_main 순환
- 텍스트 정렬: 기본 CENTER, 스펙/비교표만 LEFT
- 긴 텍스트: width 760px + \n으로 자연스러운 줄바꿈

## 출력 템플릿

```markdown
# 상세페이지 디자인 디렉션: {제품명}

**클라이언트**: {client}
**날짜**: {YYYY-MM-DD}
**출력 형식**: {html / direction}

---

## 디자인 시스템

### 컬러 팔레트
| 역할 | 컬러 | 용도 |
|------|------|------|

### 타이포그래피
| 요소 | 폰트 | 크기 | 무게 |
|------|------|------|------|

### 배경 교차 패턴
- dark_1: #111111
- dark_2: #1A1A1A
- brand_main: {브랜드 컬러}

---

## 섹션별 디자인 (24섹션)

### ATTENTION
#### 섹션 01: Hook
- **레이아웃**: {레이아웃 설명}
- **감정 목표**: 즉각적 관심 포착

#### 섹션 02: WhatIsThis
#### 섹션 03: BrandName

### INTEREST
#### 섹션 04: SetContents
#### 섹션 05: WhyCore

### DESIRE
#### 섹션 06: PainPoint
#### 섹션 07: Solution
#### 섹션 08: FeaturesOverview

### DEEP DIVE (Q&A 기능 상세)
#### 섹션 09-14: Feature 1-6 Detail
- **Q&A 패턴**: [72px 번호] → [Q. 왜 {기능}인가요?] → [A. {핵심 혜택}]
- **이미지 영역**: 760x350
- **혜택 리스트**: 1-3개
- **스펙 수치**: {관련 수치}

### TRUST
#### 섹션 15: Tips
#### 섹션 16: Differentiator
#### 섹션 17: Comparison
#### 섹션 18: Safety

### SOCIAL
#### 섹션 19: Target
#### 섹션 20: Reviews

### SPECS
#### 섹션 21: ProductSpec
#### 섹션 22: FAQ

### CONVERT
#### 섹션 23: Warranty
#### 섹션 24: CTA

---

## 반응형 노트
- 모바일 변경 사항:
- 태블릿 변경 사항:
```

## 출력 경로

```
outputs/{client}/design/{YYYYMMDD}_detail-page-{product-slug}.md
```
