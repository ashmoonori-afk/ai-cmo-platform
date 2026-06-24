# Knowledge Base 기록 규칙

> Reporter가 작업 완료 후 durable KB records를 남길 때 이 규칙을 따릅니다.

---

## 반영 대상

| KB 파일 | 반영 후보 트리거 | 추가할 내용 |
|---------|---------------|-----------|
| insights.md | researcher, competitor, data-analyst 실행 후 | 핵심 발견 요약 (3줄 이내) |
| winning-copy.md | 사용자가 "좋다" 피드백 시 | 해당 카피 + 왜 좋았는지 |
| lessons-learned.md | 전략 리뷰/회고 시 | 성공/실패 교훈 |
| agent-feedback.md | reviewer WARN/FAIL 후 | 반복 실패 패턴 + 수정 지시 |
| quality-scores.md | reviewer 검증 완료 후 | 구조/내용/브랜드 점수 + 판정 |

## Canonical Writer Rule

Reporter is the canonical writer for durable KB records and follow-up queue
creation. Other roles produce durable-learning candidates and evidence paths in
their outputs, then hand them to Reporter.

Reviewer records PASS/WARN/FAIL and correction instructions. Recurring reviewer
patterns and score candidates are handed to Reporter for `agent-feedback.md` and
`quality-scores.md`; Reporter is the canonical durable KB writer for this
workflow.

## Follow-up Queue 규칙

후속 실행 항목은 KB 본문에 섞지 않습니다. reporter는 최종 리포트 또는
onboarding report 안에 별도 `Follow-up Queue` 표를 만들고, 각 항목에
owner, due date, evidence path, status를 기록합니다.

Morpheus-style maintenance note가 필요한 경우 다음 3개 필드만 남깁니다:

```
learned:
saved:
proposed:
```

`proposed`는 자동 실행이 아니라 다음 리뷰 때 승인할 개선 후보입니다.

## 형식 규칙

Reporter는 모든 KB 항목을 아래 형식으로 뒤에 추가:

```
### [YYYY-MM-DD / {워크플로우명}]

{내용}

---
```

## 제약 조건

- **기존 기록 보존**: 기존 내용 수정/삭제 금지, 새 항목만 뒤에 추가
- 각 항목은 날짜 + 출처 워크플로우 태그 필수
- 분기별 정리 시에만 구조 변경 허용 (reporter 에이전트가 수행)
- 항목당 최대 500자
