# asset-evaluation

> 이미 만들어진 마케팅 자산(랜딩페이지·상세페이지·브랜드 카피)을 **객관적이고 냉정하게** 채점하고
> 개선 우선순위를 도출한다. 결정론적 휴리스틱 스코어러이며, 깊은 의미 품질 판단은 LLM 리뷰어(어댑터)에게 맡긴다.

## 입력
- 평가할 자산의 텍스트/마크다운 파일 (랜딩페이지 카피를 .md로 저장)

## 실행

```powershell
uv run aicmo evaluate --from path/to/landing-copy.md --title "client landing page" --out outputs/{client}/design/scorecard.md
```

## 채점 루브릭 (100점)

| 항목 | 배점 | 근거 |
|------|------|------|
| Clarity / headline | 20 | LIFT(Clarity) + 5초 테스트 — 한 줄 약속이 명확한가 |
| Value / differentiation | 20 | April Dunford 포지셔닝 — 대안 대비 고를 이유 |
| CTA strength | 15 | Unbounce CRO — 단 하나의 다음 행동, 상단 노출 |
| Proof / trust | 15 | Unbounce + LIFT(Anxiety) — 숫자·후기·보장 |
| Customer narrative | 10 | StoryBrand — 고객을 주인공으로, 문제 명시 |
| Readability | 10 | 문장 길이 |
| Structure | 10 | 헤드라인+본문+CTA 구성, 충분한 분량 |

**점수대**: PASS 80–100 · WARN 60–79 · FAIL 40–59 · CRITICAL <40

> 루브릭 배점·점수대는 출처 프레임워크(LIFT, Dunford, StoryBrand, 5초 테스트, Unbounce)를 바탕으로 한
> 엔지니어링 합성 결정이다. 실제 전환 데이터(GA/A-B)가 필요한 항목은 별도 표기한다.

## 출력
- 콘솔: 총점 + 점수대 + 항목별 점수
- `--out` 지정 시: 항목별 표 + 낮은 점수 순 개선 우선순위가 담긴 마크다운 스코어카드

## 다음 액션
- CRITICAL/FAIL: 가장 낮은 2–3개 항목부터 카피 재작성 (copywriter) → 재평가
- WARN: 경고 항목 보완 후 배포
