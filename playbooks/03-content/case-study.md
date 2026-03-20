# 케이스스터디 플레이북

## 목적

실제 고객의 성공 사례를 Situation → Challenge → Solution → Result 구조로 문서화하여, 잠재 고객의 신뢰를 높이고 영업 자료·콘텐츠 마케팅·SEO에 활용한다.

목표 글자 수: **1000–2000자**
핵심 요건: 수치 기반 결과(Result) 포함 필수

---

## 에이전트 조합

```
researcher → copywriter → reviewer
```

| 순서 | 에이전트 | 역할 | 모델 |
|------|---------|------|------|
| 1 | researcher | 고객사 정보·성과 데이터·배경 조사 | opus |
| 2 | copywriter | SCSR 구조 기반 케이스스터디 원고 작성 | sonnet |
| 3 | reviewer | 사실 확인·브랜드·구조 검증 | sonnet |

---

## 입력

| 항목 | 설명 | 필수 여부 |
|------|------|---------|
| `client` | 클라이언트 폴더명 (자사) | 필수 |
| `customer_name` | 고객사명 (공개 여부 확인 필요) | 필수 |
| `customer_industry` | 고객사 업종 | 필수 |
| `result_data` | 핵심 성과 수치 (예: 전환율 40% 향상, 비용 30% 절감) | 필수 |
| `situation` | 도입 전 고객사 상황 설명 | 선택 |
| `challenge` | 고객사가 겪은 구체적 과제 | 선택 |
| `solution` | 자사가 제공한 솔루션 설명 | 선택 |
| `customer_quote` | 고객 인용문 (있는 경우) | 선택 |
| `publish_permission` | 고객사명 공개 여부 (yes/anonymize) | 선택 (기본: anonymize) |

---

## 참조 문서

| 문서 | 경로 | 목적 |
|------|------|------|
| 클라이언트 설정 | `clients/{client}/config.md` | 자사 제품·서비스 파악 |
| 브랜드 가이드라인 | `clients/{client}/brand-guidelines.md` | 톤앤매너, 금지 표현 |
| 카피 패턴 | `clients/{client}/copy-patterns.md` | 케이스스터디 특화 패턴 |
| 우수 카피 KB | `knowledge-base/{client}/winning-copy.md` | 성과 좋은 표현 재활용 |

---

## 프레임워크

### SCSR 구조 (Situation → Challenge → Solution → Result)

```
1. Situation (상황, 150–300자)
   - 고객사의 업종·규모·시장 위치
   - 도입 전 상태 (어떤 방식으로 일하고 있었나)
   - 중립적·사실 중심 서술

2. Challenge (과제, 200–400자)
   - 고객사가 직면한 구체적 문제
   - 왜 기존 방식으로는 해결이 안 됐나
   - 가능하면 정량적 표현 (예: 수작업에 주 15시간 소요)

3. Solution (솔루션, 300–500자)
   - 자사 솔루션을 어떻게 적용했나 (구체적 기능·프로세스)
   - 도입 과정의 주요 단계
   - 맞춤화 또는 특별 지원이 있었다면 포함

4. Result (결과, 200–400자) — 수치 필수
   - 핵심 성과 지표 (KPI) 개선 수치
   - 비교 기준 명시 (예: 도입 전 대비, 업계 평균 대비)
   - 정량 불가 결과는 정성적으로 표현 후 [추정] 태그

5. 고객 인용문 (있는 경우)
   - 실명 또는 직책 표기 (공개 허용 시)
   - 익명 처리 시: "A사 마케팅 팀장"
```

### 공개 수준별 처리

```
publish_permission = yes:
  - 고객사명·담당자명·인용문 그대로 사용

publish_permission = anonymize:
  - 고객사명 → "국내 {업종} 기업 A사"
  - 담당자명 → 직책만 표기
  - 수치는 유지 (수치가 식별 요소가 아닌 경우)
```

---

## 출력 템플릿

```markdown
---
고객사: {고객사명 또는 익명 표기}
업종: {업종}
규모: {기업 규모 — 선택}
핵심 성과: {한 줄 요약 — 예: 리드 전환율 40% 향상}
---

# {고객사명}: {핵심 성과 한 줄}

> **"{고객 인용문 핵심 문장}"**
> — {직책}, {고객사명}

---

## 상황 (Situation)

{고객사 배경·도입 전 상태, 150–300자}

## 과제 (Challenge)

{구체적 문제·기존 방식의 한계, 200–400자}

## 솔루션 (Solution)

{자사 솔루션 적용 방법·과정, 300–500자}

## 결과 (Result)

| 지표 | 도입 전 | 도입 후 | 변화율 |
|------|--------|--------|-------|
| {KPI 1} | {수치} | {수치} | {+XX%} |
| {KPI 2} | {수치} | {수치} | {+XX%} |
| {KPI 3} | {수치} | {수치} | {+XX%} |

{결과 서술 100–200자}

---

> **"{고객 인용문 전문}"**
> — {이름 또는 직책}, {고객사명}

---

**{자사명}과 함께 같은 성과를 만들어보세요.**
[{CTA 버튼 텍스트}]({CTA URL})
```

---

## 출력 경로

```
outputs/{client}/content/{YYYYMMDD}_case-study-{customer-slug}.md
```

예시:
```
outputs/flowerplus/content/20260318_case-study-retail-a.md
```

**Knowledge Base 업데이트:**
- 성과 수치·증거 → `knowledge-base/{client}/insights.md` append
- 효과적인 케이스스터디 구조 → `knowledge-base/{client}/winning-copy.md` append
