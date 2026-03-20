# client-onboarding

## 목적

신규 클라이언트 설정을 완전 자동화한다. 기본 정보 수집부터 config.md 생성, 브랜드 가이드라인 초안, 경쟁사 초기 분석, ICP 정의, KB 초기화, 3개월 액션 플랜까지 한 번에 처리한다.

최소 입력: 회사명 + 웹사이트 URL

## 에이전트 조합

```
researcher + competitor (병렬) → strategist → reporter
```

- `researcher`: 브랜드 분석, ICP 도출, 시장 조사
- `competitor`: 경쟁사 분석 (WebSearch 기반)
- `strategist`: 3개월 액션 플랜 수립
- `reporter`: 모든 산출물 취합 및 정리

## 입력

```
COMPANY_NAME: {name}         # 회사명 (필수)
WEBSITE_URL: {url}           # 웹사이트 URL (필수)
INDUSTRY: {industry}         # 업종 (선택, 없으면 WebSearch로 자동 파악)
MAIN_PRODUCT: {product}      # 주요 제품/서비스 (선택)
TARGET_MARKET: {market}      # 타겟 시장 B2B/B2C (선택)
COMPETITORS: {competitors}   # 알고 있는 경쟁사 (선택, 쉼표 구분)
GOALS: {goals}               # 마케팅 목표 (선택)
BUDGET: {budget}             # 월 마케팅 예산 범위 (선택)
```

## 참조 문서

- `playbooks/01-strategy/positioning.md` — ICP 정의 프레임워크
- `playbooks/02-intelligence/competitor-analysis.md` — 경쟁사 분석 방법론
- `clients/template/config.md` — config.md 작성 템플릿 (존재하는 경우)

## 프레임워크

### Step 0: 클라이언트 인터뷰 (사용자 입력)

자동 리서치 전에 사용자에게 5개 핵심 질문을 묻습니다. 사용자 답변이 있으면 리서치 정확도가 대폭 향상됩니다.

> **CMO가 사용자에게 묻는 질문:**
>
> 1. **핵심 제품/서비스**: "주력 제품이나 서비스가 뭔가요? 한 줄로 설명해주세요."
> 2. **타겟 고객**: "주요 고객은 누구인가요? (B2B면 업종/규모, B2C면 연령/관심사)"
> 3. **경쟁사**: "경쟁사 3개를 꼽자면? (직접 경쟁 + 간접 경쟁 포함)"
> 4. **마케팅 과제**: "현재 마케팅에서 가장 큰 과제나 고민이 뭔가요?"
> 5. **톤앤매너**: "브랜드 톤을 한 줄로 표현하면? (예: '전문적이지만 친근한', '젊고 캐주얼한')"
>
> **선택 추가 질문** (사용자가 원하면):
> 6. "현재 사용 중인 마케팅 채널은?"
> 7. "이번 분기 가장 중요한 목표는?"
> 8. "월 마케팅 예산 범위는?"

**답변 처리:**
- 사용자가 모든 질문에 답변 → 답변을 기반으로 config.md 초안 작성 + WebSearch로 보완
- 사용자가 일부만 답변 → 답변된 부분은 확정, 나머지는 WebSearch로 자동 수집
- 사용자가 "스킵" → 전부 WebSearch로 자동 수집 (기존 방식)

### Step 1: 기본 정보 수집 (researcher)

```
자동 수집 항목 (WebSearch + 사이트 분석):
1. 회사 개요 (설립연도, 규모, 위치)
2. 주요 제품/서비스 라인업
3. 가격대 (노출된 경우)
4. 타겟 고객층 (사이트 카피 분석)
5. 브랜드 보이스 (어조, 스타일)
6. SNS 채널 현황 (Instagram/YouTube/블로그 등)
7. 현재 마케팅 채널 (SEO/광고/콘텐츠)
8. 수상 내역 / 언론 보도

사용자 입력값 우선 적용, 없는 항목만 WebSearch로 보완.
```

### Step 2: config.md 생성 (researcher)

```
인터뷰 답변이 있으면 해당 내용을 최우선으로 반영하고, WebSearch 결과는 보완/검증용으로 사용

clients/{brand}/ 폴더 생성 후 config.md 작성:

포함 섹션:
- 회사 기본 정보 (이름, URL, 업종, 규모)
- 비즈니스 목표 (단기 3개월 / 중기 1년)
- 타겟 시장 (B2B/B2C, 지역)
- KPI 정의 (핵심 성과 지표)
- 마케팅 예산 범위
- 현재 마케팅 채널 현황
- 팀 구성 및 연락처
- 경쟁사 목록 (초기)
- 금지사항 / 주의사항
```

### Step 3: brand-guidelines.md 초안 (researcher)

```
WebSearch로 기존 브랜드 분석:
- 사이트 컬러 팔레트 추출 (Visual 분석)
- 폰트 스타일 (헤딩/본문)
- 로고 사용 규칙 (노출된 가이드라인)
- 브랜드 보이스 (어조: 공식적/친근한/전문적)
- 자주 사용하는 카피 패턴
- 금기어 / 피해야 할 표현

초안 명시: "AI 분석 초안 — 클라이언트 검토 필요"
```

### Step 4: 경쟁사 초기 분석 (competitor)

```
분석 대상: 상위 3-5개 경쟁사
(사용자 제공 + WebSearch "{company_name} 경쟁사" 로 추가 발굴)

각 경쟁사 분석:
- 포지셔닝 (어떤 가치를 강조하는가)
- 주요 채널 (SEO/광고/SNS 비중)
- 강점 / 약점
- 가격 포지션
- 콘텐츠 전략 (블로그/SNS 운영 현황)

차별화 기회:
- 경쟁사 모두 놓치고 있는 포인트
- 우리 브랜드가 우월한 영역
```

### Step 5: ICP 초기 정의 (researcher)

```
ICP (Ideal Customer Profile) 정의:

B2C인 경우:
- 연령대, 성별, 지역
- 관심사, 라이프스타일
- 구매 트리거 (언제 구매를 결정하는가)
- 구매 채널 (어디서 정보를 얻는가)
- 평균 구매 주기 / 객단가

B2B인 경우:
- 타겟 기업 규모 (직원 수, 매출)
- 업종 카테고리
- 의사결정자 직책
- 구매 사이클 (단기/장기)
- 페인 포인트 (어떤 문제를 해결하고 싶은가)

페르소나 3개 정의:
- Primary (핵심 고객)
- Secondary (부수 고객)
- Negative (피해야 할 고객)
```

### Step 6: KB 폴더 초기화 (reporter)

```
생성 파일:
knowledge-base/{brand}/insights.md
  → 헤더 + 날짜별 인사이트 템플릿 초기화
  → 온보딩 분석 결과 첫 번째 인사이트로 기록

knowledge-base/{brand}/winning-copy.md
  → 헤더 + 카피 패턴 템플릿 초기화
  → 브랜드 사이트의 성과 카피 초기 수집

knowledge-base/{brand}/lessons-learned.md
  → 헤더 + 교훈 기록 템플릿 초기화
```

### Step 7: 3개월 액션 플랜 (strategist)

```
플랜 구성 원칙:
- 1개월차: 기반 다지기 (설정/감사/리서치)
- 2개월차: 실행 시작 (콘텐츠/캠페인 런칭)
- 3개월차: 최적화 (데이터 기반 개선)

월별 테마 + 주차별 액션 아이템
예산 배분 제안
예상 KPI (보수적/목표/최적)
```

## 출력 템플릿

### 7-1. clients/{brand}/config.md

```markdown
# {brand} 클라이언트 설정
**온보딩 날짜**: {date}
**담당 에이전트**: researcher

## 회사 정보
- **회사명**: {company_name}
- **웹사이트**: {url}
- **업종**: {industry}
- **규모**: {size}
- **위치**: {location}

## 비즈니스 목표
- **3개월 목표**: {short_term_goal}
- **1년 목표**: {long_term_goal}

## 타겟 시장
- **B2B/B2C**: {type}
- **타겟 지역**: {region}
- **타겟 언어**: {language}

## KPI
| 지표 | 현재 | 3개월 목표 | 1년 목표 |
|-----|-----|---------|---------|
| {metric_1} | {current} | {target_3m} | {target_1y} |

## 마케팅 예산
- **월 예산**: {budget}
- **채널 배분**: {allocation}

## 현재 채널 현황
| 채널 | 현황 | 우선순위 |
|-----|-----|---------|
| SEO | {status} | {priority} |
| GA4 | {status} | {priority} |
| SNS | {status} | {priority} |

## 경쟁사
| 경쟁사 | URL | 주요 강점 |
|-------|-----|---------|
| {competitor_1} | {url} | {strength} |

## 팀 & 연락처
- **주요 담당자**: {contact_name} ({contact_email})
- **결재 담당**: {approver}

## 주의사항
- {note_1}
- {note_2}
```

### 7-2. 온보딩 완료 리포트

```markdown
# 클라이언트 온보딩 완료 리포트 — {brand}
**완료일**: {date}
**담당**: researcher + competitor + strategist + reporter

---

## 생성된 파일 목록

| 파일 | 경로 | 상태 |
|-----|-----|-----|
| config.md | clients/{brand}/config.md | 완료 |
| brand-guidelines.md | clients/{brand}/brand-guidelines.md | 초안 (검토 필요) |
| insights.md | knowledge-base/{brand}/insights.md | 초기화 완료 |
| winning-copy.md | knowledge-base/{brand}/winning-copy.md | 초기화 완료 |
| lessons-learned.md | knowledge-base/{brand}/lessons-learned.md | 초기화 완료 |

---

## 브랜드 개요 요약

- **회사**: {company_name}
- **업종**: {industry}
- **타겟**: {target_summary}
- **핵심 강점**: {strengths}
- **현재 마케팅 성숙도**: {maturity_level}/5

---

## 경쟁사 분석 요약

| 경쟁사 | 포지션 | 주요 채널 | 우리와 차별점 |
|-------|-------|---------|------------|
| {comp_1} | {position} | {channels} | {diff} |

**차별화 기회**: {opportunity}

---

## ICP 요약

### Primary 페르소나
- **이름**: {persona_name}
- **특징**: {description}
- **구매 트리거**: {trigger}
- **주요 채널**: {channels}

---

## 3개월 액션 플랜

### 1개월차: 기반 다지기 ({month1})
| 주차 | 액션 | 담당 | 예상 산출물 |
|-----|-----|-----|---------|
| 1주 | GA4 감사 + 설정 | data-analyst | ga-audit.md |
| 2주 | SEO 감사 | seo-specialist | seo-audit.md |
| 3주 | 키워드 리서치 | seo-specialist | keyword-research.md |
| 4주 | 콘텐츠 캘린더 초안 | copywriter | content-calendar.md |

### 2개월차: 실행 시작 ({month2})
| 주차 | 액션 | 담당 | 예상 산출물 |
|-----|-----|-----|---------|
| 1주 | 콘텐츠 #1 발행 | copywriter | blog-post.md |
| 2주 | GA4 이벤트 설정 | data-analyst | ga-setup-log.md |
| 3주 | 첫 성과 리포트 | data-analyst | performance-report.md |
| 4주 | 콘텐츠 #2-3 발행 | copywriter | blog-posts.md |

### 3개월차: 최적화 ({month3})
| 주차 | 액션 | 담당 | 예상 산출물 |
|-----|-----|-----|---------|
| 1주 | A/B 테스트 설계 | strategist | ab-test-plan.md |
| 2주 | 성과 분석 + 개선 | data-analyst | insights.md |
| 3주 | 다음 분기 전략 | strategist | quarterly-plan.md |
| 4주 | 분기 리뷰 미팅 | reporter | meeting-notes.md |

---

## 예상 KPI (3개월)

| 지표 | 현재 | 보수적 목표 | 달성 목표 | 최적 시나리오 |
|-----|-----|---------|---------|-----------|
| {kpi_1} | {current} | {conservative} | {target} | {optimistic} |
| {kpi_2} | {current} | {conservative} | {target} | {optimistic} |

---

## 다음 액션 (이번 주)

1. **config.md 검토 요청**: {contact_name}에게 공유 — 기한: {date}
2. **GA4 접근 권한 요청**: GA4 Admin 편집 권한 — 기한: {date}
3. **브랜드 가이드라인 확인**: brand-guidelines.md 초안 검토 — 기한: {date}
```

## 출력 경로

```
clients/{brand}/config.md                              (설정 파일)
clients/{brand}/brand-guidelines.md                   (브랜드 가이드라인 초안)
knowledge-base/{brand}/insights.md                    (KB — 인사이트)
knowledge-base/{brand}/winning-copy.md                (KB — 카피 패턴)
knowledge-base/{brand}/lessons-learned.md             (KB — 교훈)
outputs/{brand}/operations/onboarding-report-{YYYYMMDD}.md  (온보딩 완료 리포트)
```
