# AI CMO Platform 사용설명서

> 10개 AI 에이전트 + 33개 플레이북으로 마케팅 반복 업무를 표준화하는 노코드 AI 마케팅 운영체계

---

## 목차

1. [플랫폼 소개](#1-플랫폼-소개)
2. [시작하기 (Setup)](#2-시작하기-setup)
3. [기본 사용법](#3-기본-사용법)
4. [에이전트 구성 (10개)](#4-에이전트-구성-10개)
5. [SOP/플레이북 전체 목록 (33개)](#5-sop플레이북-전체-목록-33개)
6. [클라이언트 관리](#6-클라이언트-관리)
7. [Knowledge Base — 쓸수록 똑똑해지는 구조](#7-knowledge-base--쓸수록-똑똑해지는-구조)
8. [실전 사용 예시](#8-실전-사용-예시)
9. [폴더 구조 상세](#9-폴더-구조-상세)
10. [FAQ / 트러블슈팅](#10-faq--트러블슈팅)

---

## 1. 플랫폼 소개

### 이 플랫폼이 뭔가요?

Claude Code를 열고 자연어로 마케팅 업무를 지시하면, AI가 전략 기획부터 콘텐츠 작성, 세일즈 지원, SEO, 분석까지 전부 처리하는 시스템입니다.

### 기존 마케팅팀 vs AI CMO Platform

| 역할 | 기존 인력 | AI CMO Platform |
|------|---------|----------------|
| 마케팅 전략가 | 월 400-600만원 | strategist 에이전트 |
| 콘텐츠 마케터 | 월 300-500만원 | copywriter + repurposer 에이전트 |
| SEO 담당자 | 월 300-500만원 | seo-specialist 에이전트 |
| 리서치 담당 | 월 300-400만원 | researcher + competitor 에이전트 |
| 세일즈 지원 | 월 300-500만원 | sales-writer 에이전트 |
| 데이터 분석가 | 월 400-600만원 | data-analyst 에이전트 |
| **합계** | **월 1,800-3,500만원** | **Claude Code 구독료만** |

### 핵심 특징

- **노코드**: 코딩 없이 자연어로만 조작
- **10개 전문 에이전트**: 각 영역의 전문가 역할 수행
- **33개 플레이북(SOP)**: 검증된 마케팅 프레임워크 내장
- **병렬 실행**: 여러 에이전트가 동시에 작업하여 시간 절약
- **Reviewer 품질 검증**: reviewer 에이전트가 최종 산출물을 검수
- **지식 축적**: Reporter가 검증된 인사이트를 클라이언트별로 누적
- **범용**: 클라이언트 설정만 바꾸면 어떤 사업에든 적용

---

## 2. 시작하기 (Setup)

### 필요한 것

- **Claude Code** (Anthropic CLI) 설치 완료
- **Claude Pro/Team 구독** (에이전트 실행에 필요)

### 설치 (3단계)

**Step 1: 압축 해제**
```
ai-cmo-platform-v1.0.zip 압축 해제 → 원하는 위치에 배치
```

**Step 2: 첫 클라이언트 등록**
```bash
cd ai-cmo-platform
claude   # Claude Code 실행
```

Claude Code에서 입력:
```
"새 클라이언트 온보딩: {회사명}, 웹사이트: {URL}"
```

이 명령 하나로 초안 생성 후 검증되는 것:
- `clients/{회사명}/config.md` — 회사 정보, ICP, 경쟁사
- `clients/{회사명}/brand-guidelines.md` — 톤앤매너 초안
- `clients/{회사명}/copy-patterns.md` — 카피 패턴
- `clients/{회사명}/pricing-rules.md` — 가격 정책
- `knowledge-base/{회사명}/` — 지식 축적 폴더
- 초기 경쟁사 분석 + ICP 정의 + 3개월 액션 플랜

**Step 3: 바로 사용 시작**
```
"GTM 전략 짜줘"
"블로그 써줘 — 주제: ..."
"경쟁사 분석해줘"
```

### 추가 클라이언트 등록

여러 사업/클라이언트를 관리할 수 있습니다:
```
"새 클라이언트 온보딩: {다른 회사명}, 웹사이트: {URL}"
```

작업 시 클라이언트명만 지정하면 해당 설정이 자동 로드됩니다:
```
"플라워플러스 블로그 써줘"    ← 플라워플러스 설정 로드
"아이리스 경쟁사 분석해줘"    ← 아이리스 설정 로드
```

---

## 3. 기본 사용법

### 사용 패턴

```
{클라이언트명} + {하고 싶은 일}
```

예시:
```
"플라워플러스 GTM 전략 짜줘"
"아이리스 콜드메일 시퀀스 만들어줘 — 타겟: 대형 장례식장"
"블로그 써줘 — 주제: AI 마케팅 자동화의 미래"
```

### 어떻게 작동하는가

```
당신의 명령
    ↓
[CLAUDE.md] 43개 패턴에서 매칭
    ↓
[CMO 에이전트] 작업 분해
    ↓
    ├── researcher (시장 조사)     ← 병렬 실행
    ├── competitor (경쟁사 분석)   ← 병렬 실행
    ↓
[strategist] 전략 수립 (리서치 결과 종합)
    ↓
[reviewer] 품질 검증
    ↓
outputs/{클라이언트}/에 결과물 저장
    ↓
Reporter가 knowledge-base 반영 후보 정리
```

### 결과물은 어디에?

모든 산출물은 `outputs/{클라이언트명}/{모듈}/` 폴더에 저장합니다.

```
outputs/
└── flowerplus/
    ├── strategy/     ← 전략 산출물
    ├── intelligence/  ← 리서치/분석 결과
    ├── content/       ← 블로그, SNS, 뉴스레터
    ├── sales/         ← 제안서, 이메일, 피칭덱
    ├── seo/           ← 키워드 분석, SEO 감사
    ├── analytics/     ← 성과 리포트
    └── operations/    ← 회의록, 데이터 정리
```

파일명 규칙: `{YYYYMMDD}_{제목}.md`
예: `20260318_gtm-motion-analysis.md`

---

## 4. 에이전트 구성 (10개)

### 전략/리서치 에이전트

| 에이전트 | 역할 | 하는 일 | 모델 |
|---------|------|--------|------|
| **Researcher** | 리서치 전문가 | 시장 동향, 업종 분석, 타겟 기업 조사. WebSearch로 실시간 정보 수집 | opus |
| **Competitor** | 경쟁사 분석가 | 경쟁사 제품/가격/포지셔닝/채널 비교. 차별화 기회 도출 | opus |
| **Strategist** | 마케팅 전략가 | 리서치 결과를 바탕으로 GTM, 포지셔닝, 퍼널 등 전략 수립 | opus |

### 콘텐츠 에이전트

| 에이전트 | 역할 | 하는 일 | 모델 |
|---------|------|--------|------|
| **Copywriter** | 카피라이터 | 블로그, SNS, 뉴스레터, 케이스스터디 등 콘텐츠 작성 | sonnet |
| **Repurposer** | 콘텐츠 변환기 | 하나의 콘텐츠를 LinkedIn, Twitter, 뉴스레터, 카드뉴스 4개 포맷으로 변환 | haiku |
| **SEO Specialist** | SEO 전문가 | 키워드 리서치, SEO 감사, 콘텐츠 최적화 제안 | sonnet |

### 세일즈/분석 에이전트

| 에이전트 | 역할 | 하는 일 | 모델 |
|---------|------|--------|------|
| **Sales Writer** | 세일즈 라이터 | 콜드메일 시퀀스, 제안서, 미팅 브리프, 피칭덱 작성 | sonnet |
| **Data Analyst** | 데이터 분석가 | 매출/성과 데이터 분석, 인사이트 추출 | opus |

### 시스템 에이전트

| 에이전트 | 역할 | 하는 일 | 모델 |
|---------|------|--------|------|
| **Reviewer** | 품질 검증자 | 모든 산출물의 브랜드 일관성, 내용 정확성 검증 | sonnet |
| **Reporter** | 리포터 | 주간/월간 리포트 생성 + knowledge-base 반영 관리 | sonnet |

### 병렬 실행으로 시간 절약

에이전트들은 독립적인 작업을 동시에 수행합니다:

| 작업 | 병렬 에이전트 | 순차 에이전트 | 시간 절약 |
|------|-------------|-------------|----------|
| GTM 전략 | researcher + competitor 동시 | → strategist → reviewer | ~50% |
| 블로그 + SNS | copywriter 작성 후 | → repurposer 4포맷 동시 | ~60% |
| 콜드 아웃바운드 | researcher 조사 후 | → sales-writer 3통 동시 | ~55% |
| SEO 콘텐츠 | seo-specialist + researcher 동시 | → copywriter → reviewer | ~40% |

---

## 5. SOP/플레이북 전체 목록 (33개)

### 모듈 01: Strategy (전략 기획) — 6개

| # | 플레이북 | 명령어 예시 | 에이전트 조합 | 산출물 |
|---|---------|-----------|-------------|--------|
| 1 | **GTM Motion Analysis** | "GTM 전략 짜줘" | researcher + competitor → strategist → reviewer | 7가지 GTM 모션 스코어카드 (10점 척도) + 채널 우선순위 + 90일 로드맵 |
| 2 | **Positioning Map** | "포지셔닝 분석해줘" | competitor → strategist → reviewer | 2x2 포지셔닝 맵 + 포지셔닝 스테이트먼트 + 메시지 프레임워크 |
| 3 | **Campaign Planning** | "캠페인 기획해줘" | strategist → reviewer | SMART 목표 + 채널 믹스 + 월간 캘린더 + KPI 대시보드 |
| 4 | **Channel Strategy** | "채널 전략 짜줘" | researcher → strategist → reviewer | 채널 매트릭스 (목적/콘텐츠/빈도/KPI) + 채널 간 시너지 맵 |
| 5 | **Pricing Strategy** | "가격 전략 분석해줘" | competitor + researcher → strategist → reviewer | 경쟁사 가격 비교표 + 가치 기반 분석 + 번들링/티어링 제안 |
| 6 | **Funnel Design** | "퍼널 설계해줘" | strategist → reviewer | 6단계 퍼널 (인지→추천) + 단계별 전술 + 전환 목표 + 콘텐츠 매핑 |

### 모듈 02: Intelligence (인텔리전스) — 5개

| # | 플레이북 | 명령어 예시 | 에이전트 조합 | 산출물 |
|---|---------|-----------|-------------|--------|
| 7 | **Competitor Monitoring** | "경쟁사 분석해줘" | competitor → reviewer | 경쟁사별 변화 감지 (제품/가격/채용/마케팅/뉴스) + 대응 제안 |
| 8 | **Industry Trends** | "업계 트렌드 알려줘" | researcher | 5개 트렌드 × (요약 + 근거 + 시사점 + 추천 액션) |
| 9 | **Account Research** | "{회사명} 조사해줘" | researcher | 기업 프로필 (규모/제품/기술스택/뉴스/의사결정자/페인포인트) |
| 10 | **ICP Analysis** | "ICP 분석해줘" | data-analyst + researcher → strategist | ICP 프로필 카드 (인구통계/행동/심리/구매동기) + 현재 vs 제안 비교 |
| 11 | **Customer Feedback** | "고객 피드백 분석해줘" | data-analyst | 테마별 분류 + 빈도 분석 + 감성 분석 + 우선순위 매트릭스 |

### 모듈 03: Content (콘텐츠) — 8개

| # | 플레이북 | 명령어 예시 | 에이전트 조합 | 산출물 |
|---|---------|-----------|-------------|--------|
| 12 | **Blog Article** | "블로그 써줘" | seo-specialist → copywriter → reviewer | SEO 최적화 블로그 (1500-3000자) + 메타 설명 + 내부 링크 제안 |
| 13 | **Social Post** | "SNS 포스트 만들어줘" | copywriter → reviewer | LinkedIn (300-500자) + Instagram (150자+해시태그) + Twitter (스레드) |
| 14 | **Newsletter** | "뉴스레터 써줘" | copywriter → reviewer | 뉴스레터 원고 (제목 + 인트로 + 3섹션 + CTA) |
| 15 | **Case Study** | "케이스스터디 만들어줘" | researcher → copywriter → reviewer | 고객 사례 (상황→과제→솔루션→결과, 수치 필수) |
| 16 | **Lead Magnet** | "리드마그넷 만들어줘" | strategist → copywriter → reviewer | 체크리스트/가이드/템플릿 원고 (PDF 변환용) |
| 17 | **Repurpose** | "이거 다른 포맷으로 변환해줘" | repurposer (4개 병렬) → reviewer | LinkedIn + Twitter + 뉴스레터 + 카드뉴스 4개 포맷 |
| 18 | **Social Calendar** | "이번달 SNS 일정 짜줘" | strategist → copywriter → reviewer | 월간 캘린더 (주차별 표) + 포스트별 카피 초안 |
| 19 | **A/B Copy** | "카피 변형 만들어줘" | copywriter (2-3개 병렬) → reviewer | 같은 메시지의 3개 버전 (톤/앵글 차이) + 추천 버전 |

### 모듈 04: Sales (세일즈) — 5개

| # | 플레이북 | 명령어 예시 | 에이전트 조합 | 산출물 |
|---|---------|-----------|-------------|--------|
| 20 | **Outbound Sequence** | "콜드메일 시퀀스 만들어줘" | researcher → sales-writer (3통 병렬) → reviewer | 3단계 이메일 (인트로→가치→마지막) + 제목 각 2버전 |
| 21 | **Call Prep** | "미팅 준비해줘" | researcher → sales-writer | 1페이지 미팅 브리프 (기업정보 + 토킹포인트 + 예상 Q&A) |
| 22 | **Proposal Draft** | "제안서 써줘" | researcher + competitor → sales-writer → reviewer | 7섹션 제안서 (현황→과제→솔루션→차별화→ROI→계획→비용) |
| 23 | **Post Meeting** | "미팅 정리해줘" | sales-writer → reviewer | CRM 요약 + 팔로업 이메일 + 내부 공유 메모 (3개 동시) |
| 24 | **Pitch Deck** | "피칭덱 만들어줘" | strategist → sales-writer → reviewer | 15슬라이드 카피 (제목 + 본문 + 스피커 노트) |

### 모듈 05: SEO — 3개

| # | 플레이북 | 명령어 예시 | 에이전트 조합 | 산출물 |
|---|---------|-----------|-------------|--------|
| 25 | **Keyword Research** | "키워드 리서치 해줘" | seo-specialist | 키워드 클러스터 (검색의도별 분류 + 난이도 추정) + 콘텐츠 로드맵 |
| 26 | **SEO Audit** | "SEO 감사해줘" | seo-specialist | 100점 스코어카드 (기술 SEO + 콘텐츠 SEO + GEO) + 개선 로드맵 |
| 27 | **Content Brief** | "콘텐츠 브리프 만들어줘" | seo-specialist → copywriter | SEO 브리프 (타겟 키워드 + H2 구조 + 참조 URL + 타겟 길이) |

### 모듈 06: Analytics (분석) — 3개

| # | 플레이북 | 명령어 예시 | 에이전트 조합 | 산출물 |
|---|---------|-----------|-------------|--------|
| 28 | **Performance Report** | "성과 리포트 만들어줘" | data-analyst | 채널별 성과 대시보드 + 전월 대비 변화 + 인사이트 3개 + 액션 |
| 29 | **Weekly Report** | "주간 리포트 만들어줘" | reporter | 모듈별 활동 요약 + 핵심 발견 + 다음 주 추천 액션 + Reporter KB 반영 후보 |
| 30 | **GA Audit** | "GA 감사해줘" | data-analyst | GA4 100점 감사 (속성/스트림/이벤트/전환/잠재고객) + 개선 순서 |

### 모듈 07: Operations (운영) — 3개

| # | 플레이북 | 명령어 예시 | 에이전트 조합 | 산출물 |
|---|---------|-----------|-------------|--------|
| 31 | **Meeting Notes** | "회의록 정리해줘" | reporter | 참석자 + 안건별 요약 + 결정 사항 + 액션 아이템 (담당자/기한) |
| 32 | **Data Cleanup** | "데이터 정리해줘" | data-analyst | 정리된 데이터 파일 + 변환 로그 + 품질 보고서 |
| 33 | **Client Onboarding** | "새 클라이언트 온보딩" | researcher + competitor → strategist → reporter | config 4개 파일 + KB 초기화 + 3개월 액션 플랜 |

---

## 6. 클라이언트 관리

### 클라이언트별 설정 파일 (4개)

| 파일 | 역할 | 어떤 에이전트가 사용하는가 |
|------|------|----------------------|
| `config.md` | 회사 정보, ICP, 경쟁사, 채널 현황 | 모든 에이전트 |
| `brand-guidelines.md` | 톤앤매너, 브랜드 보이스, 금지 표현 | copywriter, sales-writer, reviewer |
| `copy-patterns.md` | 헤드라인/CTA/이메일 패턴 | copywriter, sales-writer |
| `pricing-rules.md` | 가격 체계, 할인 정책, 커뮤니케이션 규칙 | strategist, sales-writer |

### 새 클라이언트 추가 방법

**방법 1: 검증 기반 온보딩 (추천)**
```
"새 클라이언트 온보딩: {회사명}, 웹사이트: {URL}"
```
→ 웹 검색으로 정보 수집 → 4개 파일 초안 생성 → reviewer 검증과 초기 분석 포함

**방법 2: 수동 생성**
1. `clients/_template/` 폴더를 복사하여 `clients/{회사명}/` 생성
2. 각 파일의 `{회사명}` 부분을 실제 정보로 채우기
3. `knowledge-base/{회사명}/` 폴더 생성 (insights.md, winning-copy.md, lessons-learned.md)

### 클라이언트 전환

작업 중 다른 클라이언트로 전환하려면 이름만 바꾸면 됩니다:
```
"플라워플러스 블로그 써줘"   → 플라워플러스 설정 로드
"아이리스 제안서 만들어줘"   → 아이리스 설정 로드
```

---

## 7. Knowledge Base — 쓸수록 똑똑해지는 구조

### 구조

```
knowledge-base/{클라이언트}/
├── insights.md          ← reporter가 검증된 리서치 인사이트 누적
├── winning-copy.md      ← reporter가 성과 좋은 카피 저장
└── lessons-learned.md   ← 전략적 교훈 누적
```

### 어떻게 축적되는가

| 상황 | reporter 반영 대상 |
|------|-----------------|
| 리서치/경쟁사 분석 실행 후 | `insights.md`에 핵심 발견 추가 |
| 사용자가 "이거 좋다" 피드백 | `winning-copy.md`에 해당 카피 저장 |
| 전략 리뷰/회고 시 | `lessons-learned.md`에 교훈 추가 |

### 어떻게 활용되는가

- **strategist**: 전략 수립 전 기존 인사이트 + 교훈을 먼저 읽음
- **copywriter**: winning-copy에서 검증된 톤/패턴을 재활용
- **reporter**: 분기별 KB 전체를 정리하여 중복 제거

### 결과

첫 번째 사용: 일반적인 결과물
두 번째 사용부터: 이전 인사이트가 반영된 더 정확한 결과물
3개월 후: 해당 클라이언트/업종에 대한 전문 지식이 축적된 고품질 결과물

---

## 8. 실전 사용 예시

### 예시 1: 신규 사업 런칭 (하루 작업)

```
# 오전: 전략 수립
"새 클라이언트 온보딩: ABC주식회사, 웹사이트: abc.com"
"ABC주식회사 GTM 전략 짜줘"
"ABC주식회사 포지셔닝 분석해줘"

# 오후: 콘텐츠 + 세일즈
"ABC주식회사 블로그 써줘 — 주제: {핵심 가치 제안}"
"방금 블로그 LinkedIn, Twitter, 뉴스레터로 변환해줘"
"ABC주식회사 콜드메일 시퀀스 만들어줘 — 타겟: {ICP}"

# 저녁: 정리
"ABC주식회사 주간 리포트 만들어줘"
```

### 예시 2: 주간 마케팅 루틴

```
# 월요일
"경쟁사 분석해줘"         → 이번 주 경쟁사 동향 파악
"업계 트렌드 알려줘"       → 트렌드 기반 콘텐츠 아이디어

# 화~목: 콘텐츠 제작
"블로그 써줘 — 주제: ..."  → SEO 블로그 작성
"이거 다른 포맷으로 변환"   → SNS 4개 포맷
"이번달 SNS 일정 짜줘"     → 월간 캘린더

# 금요일
"주간 리포트 만들어줘"      → 이번 주 성과 정리 + Reporter KB 반영 후보
```

### 예시 3: 영업 미팅 준비

```
# 미팅 전
"{타겟 회사명} 조사해줘"                → 기업 프로필
"미팅 준비해줘 — 타겟: {회사명}"         → 1페이지 브리프
"제안서 써줘 — 타겟: {회사명}"           → 7섹션 제안서

# 미팅 후
"미팅 정리해줘 — {개인정보와 계정정보를 제거한 미팅 메모}"    → CRM 요약 + 팔로업 이메일 초안
```

미팅 메모에는 실명, 전화번호, 이메일, 주민/사업자번호, 계정 ID, 쿠키, 토큰, API 키를 붙여넣지 마세요.
필요한 경우 회사명/역할/요약 수준으로 마스킹한 뒤 사용합니다.

### 예시 4: 복합 명령어

```
"전체 마케팅 전략 세워줘"               → GTM + 포지셔닝 + 채널 + 퍼널 한번에
"블로그 쓰고 SNS도 만들어줘"            → 블로그 + 4포맷 변환
"영업 자료 다 만들어줘"                 → 기업 리서치 + 콜프렙 + 아웃바운드
"경쟁사 분석하고 대응 전략 짜줘"         → 경쟁사 분석 + 포지셔닝 맵
```

---

## 9. 폴더 구조 상세

```
ai-cmo-platform/
│
├── CLAUDE.md                    ← 시스템 두뇌 (건드리지 마세요)
│                                   43개 자연어 매핑, 디스패치 규칙 등
│
├── agents/                      ← AI 에이전트 프롬프트 (10개)
│   ├── researcher.md            ← 리서치 전문가
│   ├── competitor.md            ← 경쟁사 분석가
│   ├── strategist.md            ← 전략가
│   ├── copywriter.md            ← 카피라이터
│   ├── repurposer.md            ← 콘텐츠 변환기
│   ├── seo-specialist.md        ← SEO 전문가
│   ├── data-analyst.md          ← 데이터 분석가
│   ├── reviewer.md              ← 품질 검증자
│   ├── sales-writer.md          ← 세일즈 라이터
│   └── reporter.md              ← 리포터
│
├── clients/                     ← 클라이언트별 설정
│   └── _template/               ← 새 클라이언트용 템플릿
│       ├── config.md            ← 회사 정보, ICP, 경쟁사
│       ├── brand-guidelines.md  ← 톤앤매너
│       ├── copy-patterns.md     ← 카피 패턴
│       └── pricing-rules.md     ← 가격 정책
│
├── playbooks/                   ← 실행 가능한 SOP (33개)
│   ├── 01-strategy/             (6) 전략 기획
│   ├── 02-intelligence/         (5) 리서치/분석
│   ├── 03-content/              (8) 콘텐츠 제작
│   ├── 04-sales/                (5) 세일즈 지원
│   ├── 05-seo/                  (3) SEO
│   ├── 06-analytics/            (3) 성과 분석
│   └── 07-operations/           (3) 운영
│
├── prompts/shared/              ← 에이전트 공통 규칙
│   ├── boilerplate.md           ← 컨텍스트 로딩 규칙
│   ├── gate-check.md            ← 품질 검증 체크리스트
│   └── knowledge-update.md      ← KB 반영 규칙
│
├── outputs/                     ← 생성물 저장 (클라이언트별)
│   └── {클라이언트명}/
│       ├── strategy/
│       ├── intelligence/
│       ├── content/
│       ├── sales/
│       ├── seo/
│       ├── analytics/
│       └── operations/
│
├── knowledge-base/              ← 축적형 지식 자산
│   └── {클라이언트명}/
│       ├── insights.md          ← 리서치 인사이트
│       ├── winning-copy.md      ← 성과 좋은 카피
│       └── lessons-learned.md   ← 전략적 교훈
│
└── references/                  ← 참조 문서 아카이브 (읽기 전용)
```

---

## 10. FAQ / 트러블슈팅

### Q: 클라이언트명을 안 넣으면?
→ "어떤 클라이언트 작업인가요?" 라고 물어봅니다. 클라이언트가 1개만 등록되어 있으면 자동 선택.

### Q: 에이전트가 틀린 내용을 생성하면?
→ reviewer 에이전트가 검증합니다. FAIL 판정 시 최대 2회 재실행. 그래도 안 되면 사용자에게 보고합니다.

### Q: 비공개 데이터(매출, GA)는 어떻게?
→ CSV/Excel 파일은 프로젝트 폴더에 두되, 제공 전 고객명, 전화번호, 이메일, 주민/사업자번호, 계정 ID, 쿠키, 토큰, API 키를 제거하거나 마스킹하세요. GA/CRM/매출 데이터는 가능한 집계 단위로 제공하고, data-analyst는 원본 행을 출력에 붙이지 않고 요약/통계와 안전한 로컬 경로만 보고합니다.

### Q: 영어로도 명령할 수 있나요?
→ 네. CLAUDE.md에 영어 패턴도 포함되어 있습니다 ("GTM strategy", "write a blog", "competitor analysis" 등).

### Q: 플레이북을 커스터마이즈할 수 있나요?
→ 네. `playbooks/` 폴더의 .md 파일을 직접 수정하면 됩니다. 프레임워크, 출력 템플릿 등을 업종에 맞게 조정 가능.

### Q: 에이전트를 추가할 수 있나요?
→ `agents/` 폴더에 새 .md 파일을 추가하고, CLAUDE.md의 매핑 테이블에 등록하면 됩니다.

### Q: 비용은 얼마나 드나요?
→ Claude Code 구독료만. 에이전트 실행 시 Claude API 사용량이 발생할 수 있습니다. 병렬 실행과 haiku 모델 활용으로 비용 최적화되어 있습니다.

### Q: 여러 사람이 같이 쓸 수 있나요?
→ 폴더를 공유하면 가능합니다. 각자 Claude Code를 열고 같은 프로젝트에서 작업할 수 있습니다. 다만 같은 클라이언트를 동시에 작업하면 KB 충돌이 있을 수 있으므로 클라이언트를 나눠서 작업하는 것을 권장합니다.

---

> **AI CMO Platform v1.0** — 10 Agents, 7 Modules, 33 Playbooks
> Built with Claude Code
