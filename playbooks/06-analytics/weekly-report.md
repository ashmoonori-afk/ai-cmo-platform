# weekly-report

## 목적

outputs/ 폴더를 스캔하여 해당 주의 모듈별 활동을 요약하고, 핵심 발견 사항과 다음 주 추천 액션을 포함한 주간 리포트를 생성한다. 생성된 인사이트는 KB(Knowledge Base)에 자동 축적된다.

## 에이전트 조합

```
reporter
```

단일 에이전트. outputs/ 폴더 파일 스캔 및 요약 특화.

## 입력

```
BRAND: {brand}           # 브랜드명
WEEK: {YYYY-WNN}         # 주차 (예: 2026-W12)
WEEK_START: {YYYY-MM-DD} # 주 시작일 (월요일)
WEEK_END: {YYYY-MM-DD}   # 주 종료일 (일요일)
SCAN_PATH: outputs/{brand}/ # 스캔 대상 경로
```

## 참조 문서

- `clients/{brand}/config.md` — 브랜드 KPI, 목표
- `knowledge-base/{brand}/insights.md` — 이전 주간 리포트 인사이트
- `knowledge-base/{brand}/lessons-learned.md` — 축적된 교훈

## 프레임워크

### Phase 1: outputs/ 폴더 스캔

```
스캔 경로: outputs/{brand}/
스캔 대상: {WEEK_START} ~ {WEEK_END} 사이 생성/수정된 파일

파일 분류:
- strategy/: 전략 문서
- intelligence/: 시장/경쟁사 인텔리전스
- content/: 콘텐츠 초안 및 캘린더
- sales/: 영업 자료
- seo/: SEO 감사, 키워드 리서치, 콘텐츠 브리프
- analytics/: 분석 리포트
- operations/: 운영 문서

각 파일에서 추출:
- 파일명 + 생성 날짜
- 핵심 결론 / 권고사항 (파일 내 "## 결론" 또는 "## 추천" 섹션)
- 완료된 액션 아이템
```

### Phase 2: 모듈별 활동 요약

```
모듈별 활동 정리 기준:
- 생성된 산출물 수
- 완료된 액션 아이템
- 진행 중인 작업
- 블로킹 이슈

활동 상태 분류:
- 완료 (Completed)
- 진행 중 (In Progress)
- 지연 (Delayed)
- 신규 (New)
```

### Phase 3: 핵심 발견 도출

```
핵심 발견 기준:
- 수치 변화 ±20% 이상인 항목
- 새로운 기회 또는 위협 신호
- 반복 등장하는 패턴
- 이전 주 대비 진전/퇴보 항목

발견 유형:
- Win: 성과 / 긍정적 진전
- Risk: 위험 신호 / 부정적 변화
- Opportunity: 새로운 기회
- Learning: 이번 주 배운 교훈
```

### Phase 4: 다음 주 추천 (Next Week Recommendations)

```
추천 생성 기준:
- 이번 주 미완료 액션 아이템 → 이월
- 핵심 발견에서 도출된 추가 액션
- 중장기 로드맵 기준 다음 단계

추천 형식:
- Must Do: 반드시 해야 하는 항목 (최대 3개)
- Should Do: 하면 좋은 항목 (최대 3개)
- Nice to Have: 여유 시 실행 (최대 2개)
```

### Phase 5: KB 업데이트

```
자동 업데이트 대상:
- knowledge-base/{brand}/insights.md
  → 이번 주 핵심 인사이트 추가 (날짜 태그 포함)

- knowledge-base/{brand}/lessons-learned.md
  → Learning 유형 발견 사항 추가
```

## 출력 템플릿

```markdown
# 주간 리포트 — {brand} {YYYY-WNN}
**기간**: {WEEK_START} ~ {WEEK_END}
**작성일**: {date} | **담당**: reporter

---

## 이번 주 요약 (Executive Summary)

> {1-2문장으로 이번 주 전체 활동의 핵심 요약}

---

## 모듈별 활동 요약

### Strategy
| 산출물 | 상태 | 주요 내용 |
|-------|-----|---------|
| {file} | {status} | {summary} |

### Intelligence
| 산출물 | 상태 | 주요 내용 |
|-------|-----|---------|
| {file} | {status} | {summary} |

### Content
| 산출물 | 상태 | 주요 내용 |
|-------|-----|---------|
| {file} | {status} | {summary} |

### SEO
| 산출물 | 상태 | 주요 내용 |
|-------|-----|---------|
| {file} | {status} | {summary} |

### Analytics
| 산출물 | 상태 | 주요 내용 |
|-------|-----|---------|
| {file} | {status} | {summary} |

### Operations
| 산출물 | 상태 | 주요 내용 |
|-------|-----|---------|
| {file} | {status} | {summary} |

---

## 핵심 발견 (Key Findings)

### Win
- {win_1}
- {win_2}

### Risk
- {risk_1}

### Opportunity
- {opportunity_1}
- {opportunity_2}

### Learning
- {learning_1}

---

## 완료된 액션 아이템

| 항목 | 담당 | 완료일 |
|-----|-----|------|
| {item} | {owner} | {date} |

---

## 미완료 / 이월 항목

| 항목 | 담당 | 원래 기한 | 이월 사유 |
|-----|-----|---------|---------|
| {item} | {owner} | {date} | {reason} |

---

## 다음 주 추천 ({next_week_start} ~ {next_week_end})

### Must Do (최우선)
1. **{action_1}**: {description} — 담당: {owner}
2. **{action_2}**: {description} — 담당: {owner}
3. **{action_3}**: {description} — 담당: {owner}

### Should Do
1. **{action_4}**: {description}
2. **{action_5}**: {description}

### Nice to Have
1. **{action_6}**: {description}

---

## KB 업데이트 내역

- `knowledge-base/{brand}/insights.md` → {n}개 인사이트 추가
- `knowledge-base/{brand}/lessons-learned.md` → {n}개 교훈 추가
```

## 출력 경로

```
outputs/{brand}/analytics/weekly-report-{YYYY-WNN}.md
```

KB 자동 업데이트:
```
knowledge-base/{brand}/insights.md        (append)
knowledge-base/{brand}/lessons-learned.md (append)
```
