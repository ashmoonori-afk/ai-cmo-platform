# meeting-notes

## 목적

미팅 원시 메모를 구조화된 회의록으로 변환한다. 참석자 / 안건별 요약 / 결정 사항 / 액션 아이템 / 다음 미팅 안건을 포함한다.
참조: VST OPS-02 패턴.

## 에이전트 조합

```
reporter
```

단일 에이전트. 사용자가 제공한 원시 메모(음성 전사, 메모 텍스트, 또는 키워드)를 정제.

## 입력

```
BRAND: {brand}              # 브랜드명
MEETING_TYPE: {type}        # 미팅 유형 (weekly-sync/client/strategy/retrospective/onboarding)
MEETING_DATE: {YYYY-MM-DD}  # 미팅 날짜
RAW_NOTES: {notes}          # 원시 메모 (음성 전사 / 텍스트 / 키워드 목록)
ATTENDEES: {attendees}      # 참석자 목록 (이름, 역할, 선택)
AGENDA: {agenda}            # 사전 안건 목록 (선택)
```

## 참조 문서

- `clients/{brand}/config.md` — 브랜드 컨텍스트, 팀 구성
- `knowledge-base/{brand}/insights.md` — 이전 미팅 결정 사항 (연속성 확인)

## 프레임워크

### Phase 1: 원시 메모 분석

```
원시 메모에서 추출할 요소:
1. 참석자 (명시되지 않은 경우 문맥에서 추론)
2. 논의 주제 블록 (주제 전환 포인트 식별)
3. 결정 사항 ("하기로 했다", "결정했다", "확정" 키워드)
4. 액션 아이템 ("담당", "해줘", "처리", "확인", "공유" 키워드)
5. 미결 사항 ("추후 논의", "다음에", "확인 필요" 키워드)
6. 다음 미팅 관련 언급
```

### Phase 2: 안건별 요약 구조화

```
안건 요약 원칙:
- 각 안건: 논의 배경 → 주요 논의 내용 → 결론/결정
- 중립적 사실 기술 (의견이 아닌 사실 위주)
- 수치/날짜/이름 등 구체적 정보 보존
- 논의되었으나 결론 없는 항목 → 미결 사항으로 분리
```

### Phase 3: 액션 아이템 추출

```
액션 아이템 필수 요소:
- 내용 (What): 구체적 할 일
- 담당자 (Who): 명확한 한 명
- 기한 (When): 날짜 또는 다음 미팅 전
- 우선순위 (Priority): High/Medium/Low

담당자 불명확한 경우: [담당자 미정 — 확인 필요] 표시
기한 불명확한 경우: [기한 미정 — 다음 미팅 전] 기본값
```

### Phase 4: 다음 미팅 준비

```
자동 생성:
- 이번 미팅 미결 사항 → 다음 미팅 안건 후보
- 액션 아이템 진척 공유 → 다음 미팅 정례 안건
- 사용자가 언급한 다음 미팅 주제
```

## 출력 템플릿

```markdown
# 회의록 — {brand} {MEETING_TYPE}
**날짜**: {MEETING_DATE}
**시간**: {start_time} ~ {end_time} ({duration}분)
**장소/채널**: {location}
**작성자**: reporter

---

## 참석자

| 이름 | 역할 | 참석 형태 |
|-----|-----|---------|
| {name} | {role} | 대면/온라인 |

---

## 안건 요약

### 1. {agenda_item_1}

**배경**: {context}

**논의 내용**:
- {discussion_point_1}
- {discussion_point_2}

**결정 사항**: {decision}

---

### 2. {agenda_item_2}

**배경**: {context}

**논의 내용**:
- {discussion_point_1}

**결정 사항**: {decision}

---

## 결정 사항 요약

| # | 결정 내용 | 관련 안건 |
|--|---------|---------|
| 1 | {decision_1} | {agenda_ref} |
| 2 | {decision_2} | {agenda_ref} |

---

## 액션 아이템

| # | 내용 | 담당 | 기한 | 우선순위 |
|--|-----|-----|-----|---------|
| 1 | {action_1} | {owner} | {deadline} | High |
| 2 | {action_2} | {owner} | {deadline} | Medium |
| 3 | {action_3} | {owner} | {deadline} | Low |

---

## 미결 사항

| 사항 | 상태 | 다음 단계 |
|-----|-----|---------|
| {open_item_1} | 논의 예정 | {next_step} |

---

## 다음 미팅

**예정일**: {next_meeting_date}
**형식**: {format}

**다음 미팅 안건 후보**:
1. {next_agenda_1} (이번 미결 사항 이월)
2. {next_agenda_2} (액션 아이템 진척 공유)
3. {next_agenda_3}
```

## 출력 경로

```
outputs/{brand}/operations/meeting-notes-{YYYY-MM-DD}-{meeting-type}.md
```
