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

- `playbooks/01-strategy/positioning-map.md` — ICP 정의 프레임워크
- `playbooks/02-intelligence/competitor-monitoring.md` — 경쟁사 분석 방법론
- `clients/_template/config.md` — config.md 작성 템플릿

## 프레임워크

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
clients/{client}/ 폴더 생성 후 config.md 작성:

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

### Step 2.5: 클라이언트 인터뷰 (config.md 보완)

온라인 리서치로 채울 수 없는 필드를 클라이언트에게 확인한다:

**필수 질문 (반드시 확인):**
1. 월 마케팅 예산 범위는? (₩)
2. 현재 마케팅 팀 규모는? (인원 수, 담당자 이름/이메일)
3. 핵심 KPI와 현재 수치는? (월 매출, 방문자, 전환율 등)
4. 3개월/1년 비즈니스 목표는?
5. 가격 정책의 공개 범위는? (웹 공개 / 문의 시 안내 / 미팅 시만)

**B2C 추가 질문:**
6. 주요 판매 채널은? (자사몰, 스마트스토어, 쿠팡 등 비중)
7. 주요 고객 연령대/성별은?
8. 평균 객단가와 재구매 주기는?
9. 시즌별 매출 변동이 있는가? (S/S, F/W 등)

**B2B 추가 질문:**
6. 평균 계약 규모(ACV)와 영업 주기는?
7. 의사결정 구조는? (단독/위원회/승인 필요)
8. 현재 CRM을 사용하는가? (도구명)

인터뷰 결과로 config.md의 [미확인] 필드를 채운다.

### Step 3: brand-guidelines.md 초안 생성 (researcher) — 강화

반드시 아래 섹션을 모두 채워서 생성한다 (빈 섹션 금지):

1. **브랜드 미션**: 웹사이트 About/소개 페이지에서 추출 (1문장)
2. **톤앤매너**: 사이트 카피 분석으로 판별
   - 격식 수준: 격식체/반격식체/비격식체
   - 브랜드 성격: 3개 키워드 (예: "감성적, 따뜻한, 미니멀")
   - 문장 예시: 실제 사이트에서 추출한 대표 문장 3개
3. **선호/금지 표현**: 사이트 카피에서 반복 사용되는 표현 → 선호, 사용하지 않는 표현 → 금지
4. **핵심 가치 제안**: 메인 메시지 + 서브 메시지 3개
5. **비주얼 아이덴티티**: 메인 컬러(hex), 서브 컬러(hex) — 사이트에서 추출
6. **언어 혼용 규칙** (해당 시): 영문 브랜드명/카피와 한국어 설명의 혼용 방식

"[AI 분석 초안 — 클라이언트 검토 필요]" 워터마크 필수.

```
참고 — 기존 분석 항목 (위 섹션에 통합):
- 사이트 컬러 팔레트 추출 (Visual 분석) → 비주얼 아이덴티티
- 폰트 스타일 (헤딩/본문) → 비주얼 아이덴티티
- 로고 사용 규칙 (노출된 가이드라인) → 비주얼 아이덴티티
- 브랜드 보이스 (어조: 공식적/친근한/전문적) → 톤앤매너
- 자주 사용하는 카피 패턴 → 선호 표현
- 금기어 / 피해야 할 표현 → 금지 표현
```

### Step 3.5: copy-patterns.md 초안 생성 (researcher)

brand-guidelines.md의 톤앤매너를 기반으로 카피 패턴 문서를 생성한다.

```
포함 섹션:
1. 헤드라인 패턴: 사이트에서 추출한 대표 헤드라인 구조 (3-5개)
2. CTA 패턴: 버튼/링크에서 사용하는 행동 유도 문구 모음
3. 제품 설명 패턴: 제품/서비스 소개 시 반복되는 구조
4. SNS 카피 패턴: 기존 SNS 게시물에서 추출 (있는 경우)
5. 금지 패턴: 브랜드에 맞지 않는 카피 스타일

"[AI 분석 초안 — 클라이언트 검토 필요]" 워터마크 필수.
저장 경로: clients/{client}/copy-patterns.md
```

### Step 3.6: pricing-rules.md 초안 생성 (researcher)

웹사이트 및 공개 자료에서 가격 정책을 추출하여 문서화한다.

```
포함 섹션:
1. 가격 공개 수준: 웹 공개 / 문의 시 안내 / 미팅 시만
2. 가격 체계: 구독형 / 일회성 / 프로젝트 기반 / 혼합
3. 공개된 가격 정보: (웹사이트에서 확인 가능한 경우)
4. 할인/프로모션 정책: (확인 가능한 경우)
5. 경쟁사 대비 가격 포지션: 프리미엄 / 중간 / 가성비

비공개 가격인 경우 [미확인 — 인터뷰 필요] 태그 사용.
"[AI 분석 초안 — 클라이언트 검토 필요]" 워터마크 필수.
저장 경로: clients/{client}/pricing-rules.md
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
knowledge-base/{client}/insights.md
  → 헤더 + 날짜별 인사이트 템플릿 초기화
  → 온보딩 분석 결과 첫 번째 인사이트로 기록

knowledge-base/{client}/winning-copy.md
  → 헤더 + 카피 패턴 템플릿 초기화
  → 브랜드 사이트의 성과 카피 초기 수집

knowledge-base/{client}/lessons-learned.md
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

### 7-1. clients/{client}/config.md

```markdown
# {client} 클라이언트 설정
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
# 클라이언트 온보딩 완료 리포트 — {client}
**완료일**: {date}
**담당**: researcher + competitor + strategist + reporter

---

## 생성된 파일 목록

| 파일 | 경로 | 상태 |
|-----|-----|-----|
| config.md | clients/{client}/config.md | 완료 |
| brand-guidelines.md | clients/{client}/brand-guidelines.md | 초안 (검토 필요) |
| copy-patterns.md | clients/{client}/copy-patterns.md | 초안 (검토 필요) |
| pricing-rules.md | clients/{client}/pricing-rules.md | 초안 (검토 필요) |
| insights.md | knowledge-base/{client}/insights.md | 초기화 완료 |
| winning-copy.md | knowledge-base/{client}/winning-copy.md | 초기화 완료 |
| lessons-learned.md | knowledge-base/{client}/lessons-learned.md | 초기화 완료 |

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
clients/{client}/config.md                              (설정 파일)
clients/{client}/brand-guidelines.md                   (브랜드 가이드라인 초안)
clients/{client}/copy-patterns.md                      (카피 패턴 초안)
clients/{client}/pricing-rules.md                      (가격 정책 초안)
knowledge-base/{client}/insights.md                    (KB — 인사이트)
knowledge-base/{client}/winning-copy.md                (KB — 카피 패턴)
knowledge-base/{client}/lessons-learned.md             (KB — 교훈)
outputs/{client}/operations/onboarding-report-{YYYYMMDD}.md  (온보딩 완료 리포트)
```
