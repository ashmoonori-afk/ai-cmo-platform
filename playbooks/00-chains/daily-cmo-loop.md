# daily-cmo-loop

## 목적

Okara AI CMO의 핵심 차별점인 "매일 자동으로 돌아가는 마케팅 루프"를 이 플랫폼의 승인 게이트 철학 안에서 구현한다. 하루 1회 실행으로 (1) 성과 다이제스트 → (2) 기회 스캔 → (3) 채널별 초안 생성 → (4) 검증 → (5) 오너 승인 → (6) KB 축적까지 완결하는 일일 체인.

> Okara와의 차이: Okara는 자동 실행 후 검토, 이 플랫폼은 초안 생성까지 자동 + 게시/발송 전 오너 승인 게이트. 발행·발송·배포는 항상 인간 승인.

## 에이전트 조합

```
data-analyst + seo-specialist + community-manager (병렬) → copywriter → reviewer → [owner gate] → reporter
```

## 입력

```
BRAND: {client}        # 클라이언트명
CHANNELS: {channels}   # 오늘 초안을 만들 채널 (x,linkedin,reddit,hn 중 선택, 기본: x,linkedin)
DATA_DROP: {path}      # 사용자가 올려둔 최신 성과 데이터 (GA/GSC CSV 등, 선택)
SKIP: {skip}           # 오늘 건너뛸 단계 (선택)
```

## 참조 문서

- `clients/{client}/config.md` + `brand-guidelines.md` (필수)
- `knowledge-base/{client}/insights.md` — 어제까지의 인사이트 (중복 제안 방지)
- `knowledge-base/{client}/winning-copy.md` — 검증된 카피 톤

## 체인 절차

### 1단계: 성과 다이제스트 (data-analyst)
- DATA_DROP이 있으면 분석, 없으면 "오늘 데이터 없음" 명시하고 건너뜀
- 이상 징후(급등/급락) + 오늘 주목할 페이지/키워드 1-3개

### 2단계: 기회 스캔 (병렬)
- seo-specialist: 오늘의 키워드/GEO 기회 1-3개 (keyword-research 라이트 모드)
- community-manager: Reddit/HN 참여 기회 1-3개 (scan 모드)

### 3단계: 채널 초안 생성 (copywriter)
- CHANNELS에 지정된 채널별 일일 초안:
  - x → `playbooks/03-content/x-twitter-daily.md` 규칙
  - linkedin → `playbooks/03-content/linkedin-founder-voice.md` 규칙
  - reddit/hn → community-manager 결과를 copywriter가 최종 다듬기
- 1-2단계 인사이트를 소재로 우선 사용 (데이터 기반 콘텐츠)

### 4단계: 품질 게이트 (reviewer)
- `prompts/shared/gate-check.md` + 채널별 플레이북 검증 항목
- FAIL 시 해당 채널만 재실행 (최대 2회)

### 5단계: 오너 승인 게이트
- 일일 피드를 사용자에게 제시: 채널별 초안 + 기회 리스트 + 다이제스트
- 승인/수정/거부를 수집 — 승인 전 어떤 것도 게시하지 않음

### 6단계: 마무리 (reporter)
- 승인 결과 반영 + KB 업데이트 (insights.md에 오늘의 발견 append)
- 내일 추천 액션 1-3개

## 출력

`outputs/{client}/analytics/{YYYYMMDD}_daily-feed.md` (일일 피드 — Okara의 "daily feed"에 해당)

```markdown
# Daily CMO Feed — {client} {date}
## 오늘의 다이제스트 (데이터 기반)
## 오늘의 기회 (SEO/GEO/커뮤니티)
## 오늘의 초안 (채널별, 승인 대기)
## 승인 결과 + 내일 추천 액션
```

## 실행 방법

- 대화형: "데일리 루프 돌려줘" / "오늘 마케팅 뭐해야 해"
- 엔진: `aicmo run daily-cmo-loop --client {client}` (워크플로우: `workflows/daily-cmo-loop.workflow.yaml`)
- 반복 실행은 사용자가 매일 트리거 (cron/스케줄러 연동은 로컬 환경에서 사용자가 설정)

## 금지 사항

- 자동 게시·발송·배포 금지 (오너 게이트 필수)
- 데이터 없을 때 지표를 지어내지 말 것 — "데이터 없음" 명시
- 어제와 동일한 제안 반복 금지 — insights.md 참조해 중복 회피
