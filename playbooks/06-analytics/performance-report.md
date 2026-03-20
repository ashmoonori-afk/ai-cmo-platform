# performance-report

## 목적

채널별 성과를 트래픽 / 전환 / 비용 / ROI 기준으로 분석하여 전월 대비 변화 인사이트와 최적화 제안을 포함한 채널 성과 대시보드를 생성한다.

## 에이전트 조합

```
data-analyst
```

단일 에이전트. GA4 Data API 또는 사용자 제공 CSV 데이터 기반.

## 입력

```
BRAND: {brand}             # 브랜드명
PERIOD: {YYYY-MM}          # 분석 기간 (예: 2026-03)
PREV_PERIOD: {YYYY-MM}     # 비교 기간 (기본: 전월)
DATA_SOURCE: {source}      # 데이터 출처 (ga4/csv/manual)
DATA_FILE: {filepath}      # CSV 파일 경로 (data_source=csv인 경우)
CHANNELS: {channels}       # 분석 채널 (기본: organic/paid/social/email/direct/referral)
CURRENCY: KRW              # 통화 (기본: KRW)
```

## 참조 문서

- `clients/{brand}/config.md` — KPI 목표, 비즈니스 컨텍스트
- `knowledge-base/{brand}/insights.md` — 이전 리포트 인사이트
- `ga-optimizer/CLAUDE.md` — GA4 데이터 해석 기준

## 프레임워크

### Phase 1: 데이터 수집 및 정제

```
GA4 기준 수집 메트릭:
- 트래픽: Sessions, Users, New Users, Engaged Sessions
- 행동: Engagement Rate, Avg Engagement Time, Pages/Session
- 전환: Conversions, Conversion Rate, Goal Completions
- 비용: Ad Spend (Google Ads / Meta Ads / 기타)
- 수익: Revenue, ROAS, CPA, CPC

채널 분류 기준 (GA4 Default Channel Grouping):
- Organic Search: Google/Naver SEO
- Paid Search: Google Ads / Naver SA
- Organic Social: Instagram/Facebook/YouTube 자연 유입
- Paid Social: Meta Ads / 카카오 광고
- Email: 이메일 캠페인
- Direct: 직접 방문
- Referral: 외부 링크 유입
```

### Phase 2: 채널별 성과 분석

```
각 채널 분석 기준:
1. 절대값 (당월 수치)
2. 전월 대비 변화율 (MoM %)
3. 기여도 (전체 대비 채널 비중 %)
4. 효율성 지표 (CPA, ROAS, Conversion Rate)

이상값 감지:
- MoM 변화율 ±30% 이상 → 원인 분석 필수
- 전환율이 업계 평균 대비 50% 이하 → 경고 표시
```

### Phase 3: 인사이트 도출

```
인사이트 구조 (각 인사이트):
What: 무슨 일이 일어났는가 (수치)
Why: 왜 일어났는가 (추정 원인)
So What: 비즈니스에 어떤 의미인가
Action: 다음 액션은 무엇인가

필수 인사이트 3개:
1. 최고 성과 채널 (Top Performer)
2. 개선 필요 채널 (Underperformer)
3. 기회 포착 (Opportunity)
```

### Phase 4: 최적화 제안

```
제안 우선순위 기준:
- Impact Score = (예상 성과 향상 %) × (구현 용이성) / 필요 비용
- High Impact + Low Effort → 즉시 실행
- High Impact + High Effort → 계획 수립
- Low Impact + Low Effort → 여유 시 실행
- Low Impact + High Effort → 보류
```

## 출력 템플릿

```markdown
# 채널 성과 리포트 — {brand}
**분석 기간**: {period} | **비교 기간**: {prev_period}
**작성일**: {date} | **담당**: data-analyst

---

## 종합 요약

| 지표 | {period} | {prev_period} | MoM 변화 | 평가 |
|-----|---------|--------------|---------|-----|
| 총 세션 | {sessions} | {prev_sessions} | {pct}% | {emoji} |
| 총 전환 | {conversions} | {prev} | {pct}% | {emoji} |
| 전환율 | {cvr}% | {prev}% | {diff}pp | {emoji} |
| 총 광고비 | ₩{spend} | ₩{prev} | {pct}% | {emoji} |
| 전체 ROAS | {roas}x | {prev}x | {diff}x | {emoji} |
| 총 매출 | ₩{revenue} | ₩{prev} | {pct}% | {emoji} |

---

## 채널별 성과 대시보드

| 채널 | 세션 | MoM | 전환 | MoM | 전환율 | 광고비 | ROAS | CPA |
|-----|-----|-----|-----|-----|------|------|-----|-----|
| Organic Search | {n} | {pct}% | {n} | {pct}% | {rate}% | - | - | - |
| Paid Search | {n} | {pct}% | {n} | {pct}% | {rate}% | ₩{spend} | {roas}x | ₩{cpa} |
| Organic Social | {n} | {pct}% | {n} | {pct}% | {rate}% | - | - | - |
| Paid Social | {n} | {pct}% | {n} | {pct}% | {rate}% | ₩{spend} | {roas}x | ₩{cpa} |
| Email | {n} | {pct}% | {n} | {pct}% | {rate}% | - | - | - |
| Direct | {n} | {pct}% | {n} | {pct}% | {rate}% | - | - | - |
| Referral | {n} | {pct}% | {n} | {pct}% | {rate}% | - | - | - |
| **합계** | **{total}** | **{pct}%** | **{total}** | **{pct}%** | **{rate}%** | **₩{total}** | **{roas}x** | **₩{cpa}** |

---

## 핵심 인사이트

### Insight 1: {insight_title} (Top Performer)
- **What**: {채널}의 {metric}이 {period}에 {value}를 기록, 전월 대비 {pct}% 증가
- **Why**: {추정 원인}
- **So What**: {비즈니스 의미}
- **Action**: {다음 액션}

### Insight 2: {insight_title} (Underperformer)
- **What**: {채널}의 {metric}이 {value}로 전월 대비 {pct}% 하락
- **Why**: {추정 원인}
- **So What**: {비즈니스 의미}
- **Action**: {다음 액션}

### Insight 3: {insight_title} (Opportunity)
- **What**: {관찰 내용}
- **Why**: {배경}
- **So What**: {기회}
- **Action**: {다음 액션}

---

## 최적화 제안 (액션 아이템)

| # | 채널 | 제안 내용 | 예상 효과 | 우선순위 | 담당 | 기한 |
|--|-----|---------|---------|---------|-----|-----|
| 1 | {channel} | {action} | {expected_impact} | High | {owner} | {date} |
| 2 | {channel} | {action} | {expected_impact} | Medium | {owner} | {date} |
| 3 | {channel} | {action} | {expected_impact} | Low | {owner} | {date} |

---

## 다음 달 목표

| 지표 | 현재 ({period}) | 목표 ({next_period}) | 달성 전략 |
|-----|--------------|-------------------|---------|
| 총 세션 | {current} | {target} | {strategy} |
| 전환율 | {current}% | {target}% | {strategy} |
| ROAS | {current}x | {target}x | {strategy} |
```

## 출력 경로

```
outputs/{brand}/analytics/performance-report-{YYYYMM}.md
```
