# weekly-report

## 한 장 요약

가게의 실제 성과는 저장한 수기 기록으로 집계하고, 생성 문서 수와 구분한다.
`aicmo outcomes`에서 CSV를 먼저 미리 본 뒤 확인한 버전을 저장한다.
엔진 `weekly-report`는 날짜·채널별 관측값을 계산해 사장님용 한 장 요약과 일별 근거를 만들고
최종 reviewer를 거친다. 아래 기존 문서 활동 요약 절차는 대화형 분석용이며 실제 실적의 대용이 아니다.

## 엔진의 수기 성과 계약

- 입력: `client`, 월요일 `week_start=YYYY-MM-DD`, `channel`(기본 naver).
  날짜는 Asia/Seoul 기준이다. google-business/instagram/offline도 수기 기록 분류로 지원하며
  외부 연동을 의미하지 않는다. 다른 시간대 현지 일자는 변환해서 섞지 않는다.
- 원천: `aicmo outcomes --client shop --week-start 2026-08-31 --from counts.csv`로
  미리 본 동일 자료를 `--confirm-sha`로 저장한다. 기존값 정정은 `--replace`가 추가로 필요하다.
- `metrics.report`가 저장한 두 주의 일별 숫자를 계산한다. reporter 역할의 생성 모델 호출로
  숫자를 다시 작성하지 않는다. 최종 reviewer는 기간·수기 출처·미입력·부분합·분모를 검토한다.
- 미입력은 0이 아니다. 지표마다 관측 부분합과 입력 일수 N/7을 표시하며, 두 주 모두 7일이
  입력되고 지난주 합계가 양수인 경우만 증감률을 계산한다. 매출 귀속·인과 효과를 주장하지 않는다.
- 보고서는 생성 당시 스냅샷이다. 재개는 같은 보고서를 유지하고, 원자료 정정 뒤에는 새 run을 만든다.
  원본 CSV SHA·행 수정번호·집계 SHA와 기존 산출물 SHA 검증이 버전을 구분한다.
- reviewer 미설정/WARN/FAIL은 납품 가능으로 표시하지 않는다. 모델 생성 단계가 없는 수기 집계는
  기본 생성 어댑터가 LocalAdapter여도 데모 문안으로 오인하지 않으며 검토는 여전히 필요하다.
- 엔진 경로는 KB에 결과를 자동 축적하지 않는다. 실제 채택·수정 이유와 검토된 인사이트의 연결은
  별도 피드백 절차이며, 단순 저장을 학습 완료라고 보고하지 않는다.

사용 방법과 CSV 열 정의는 `docs/OUTCOMES.md`와 `examples/manual-outcomes.csv`를 따른다.
CSV 읽기/인코딩과 트랜잭션 처리는 Python 공식
[csv](https://docs.python.org/3/library/csv.html),
[sqlite3](https://docs.python.org/3/library/sqlite3.html) 문서(2026-09-06 확인)를 따른다.

## 목적

대화형 분석에서는 outputs/ 폴더의 모듈별 활동과 다음 주 추천 액션을 요약한다.
실제 성과는 수기 원천을 별도로 대조하며, 인사이트는 검토된 후보만 Reporter에 전달한다.

## 에이전트 조합

```
reporter → reviewer
```

단일 에이전트. outputs/ 폴더 파일 스캔 및 요약 특화.

## 입력

```
BRAND: {client}           # 브랜드명
WEEK: {YYYY-WNN}         # 주차 (예: 2026-W12)
WEEK_START: {YYYY-MM-DD} # 주 시작일 (월요일)
WEEK_END: {YYYY-MM-DD}   # 주 종료일 (일요일)
SCAN_PATH: outputs/{client}/ # 스캔 대상 경로
```

## 참조 문서

- `clients/{client}/config.md` — 브랜드 KPI, 목표
- `knowledge-base/{client}/insights.md` — 이전 주간 리포트 인사이트
- `knowledge-base/{client}/lessons-learned.md` — 축적된 교훈

## 프레임워크

### Phase 1: outputs/ 폴더 스캔

```
스캔 경로: outputs/{client}/
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

### Phase 5: KB 후보 검토

```
reviewer가 근거를 확인한 후 Reporter에 전달할 후보:
- knowledge-base/{client}/insights.md
  → 이번 주 핵심 인사이트 후보 (날짜와 수기/문서 출처 포함)

- knowledge-base/{client}/lessons-learned.md
  → Learning 유형 발견 후보
```

## 출력 템플릿

```markdown
# 주간 리포트 — {client} {YYYY-WNN}
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

## KB 후보 및 실제 반영 내역

- `knowledge-base/{client}/insights.md` → 검토된 후보 수와 실제 append 증거를 구분
- `knowledge-base/{client}/lessons-learned.md` → 검토된 후보 수와 실제 append 증거를 구분
```

## 출력 경로

```
outputs/{client}/analytics/weekly-report-{YYYY-WNN}.md
```

검토한 후보의 전달 대상 (엔진 자동 갱신 없음):
```
knowledge-base/{client}/insights.md        (append)
knowledge-base/{client}/lessons-learned.md (append)
```

## 다음 단계

1. 운영자는 주간 보고 전에 수기 관측과 생성 문서 활동을 분리해 자료를 준비한다.
2. reviewer는 전달 전에 기간·출처·미입력 범위와 수치를 검토한다.
3. Reporter는 후보 승인과 실제 append 증거가 있을 때만 KB 반영 완료를 기록한다.
