# 신규 사업 런치팩 체인 (상담 → 5대 산출물)

## 목적

50-60대 예비·초기 사장님과의 **상담 한 번**에서 출발해, 아래 5가지 산출물을 **정해진 순서로 한 번에** 만든다. 분기 없음. 각 단계의 산출물이 다음 단계의 입력이 된다.

| # | 산출물 | 만드는 단계 |
|---|--------|-----------|
| ① | 마케팅 전략 (90일 실행 로드맵) | Phase 2 |
| ② | 마케팅 채널믹스 (집중 채널 최대 3개) | Phase 3 |
| ③ | 후킹문안 리스트 (채널별 문안집) | Phase 4 |
| ④ | 브랜드 에셋 킷 (컬러·글꼴·로고 방향·톤) | Phase 5 |
| ⑤ | 홈페이지 (13섹션 카피 + HTML 시안) | Phase 6 |

## 언제 쓰나

- 신규 클라이언트가 "사업 시작하는데 마케팅 좀 해줘"라고 왔을 때의 **기본 경로**
- 클라이언트가 마케팅 용어를 모를 때 (이 체인의 모든 클라이언트 대면 산출물은 전문용어 없이 작성)
- Lite 모드 조건(3인 이하, 월 예산 100만 원 이하)이어도 실행 가능 — 각 산출물을 핵심만 남긴 축약판으로 만든다

단일 산출물만 필요하면 이 체인 대신 해당 플레이북을 단독 실행한다 (CLAUDE.md §3 매핑).

## 체인 개요

```
Phase 0   상담 인테이크 (client-onboarding Mode A)
   ↓ config.md + brand-guidelines.md + 상담 메모
Phase 0.5 무료 지원 신청 + 사기 방어 (09-local/support-programs)
   ↓ 신청 체크리스트 + 감별표
Phase 1   시장 확인 (researcher + competitor 병렬)
   ↓ 리서치 2종
Phase 2   마케팅 전략 ①
   ↓ 핵심 메시지 + 90일 로드맵
Phase 3   채널믹스 ② (우선순위 공식 + 업종 분기)
   ↓ 집중 채널 최대 3개 + 주간 루틴
Phase 4   후킹문안 리스트 ③
   ↓ 채널별 문안집 (히어로 문안 포함)
Phase 5   브랜드 에셋 킷 ④
   ↓ 컬러·글꼴·로고 방향
Phase 6   홈페이지 ⑤  (Phase 4 문안 + Phase 5 킷 사용)
   ↓ 카피 + HTML
Phase 6.5 채널 실행 팩 (선택 채널의 09-local SOP — 즉시 게시 가능 산출물)
   ↓ 채널별 실행 팩
Phase 7   검증 + 전달 (reviewer 게이트 → 사장님 승인 → 런치팩 리포트)
```

## 실행 순서

### Phase 0: 상담 인테이크

- playbook: `playbooks/07-operations/client-onboarding.md` (Mode A — 상담 진행 수칙 포함)
- 쉬운 말 질문 10개 → `answers.json` → `uv run aicmo onboard --client {slug} --from answers.json`
- 산출: `clients/{slug}/config.md`, `brand-guidelines.md`, KB 3종, 상담 메모
- **게이트**: 사장님에게 요약을 소리 내어 재확인 ("제가 이해한 내용이 맞는지 확인해 주세요") 후에만 다음 단계 진행

### Phase 0.5: 무료 지원 신청 + 사기 방어 (권장)

- playbook: `playbooks/09-local/support-programs.md`
- 돈 쓰기 전에: 신청 가능한 정부·플랫폼 지원(카카오 단골 무상캐시 30만 원, 소진공 온라인판로, 지자체 중장년 디지털 전환 등) 체크리스트 + 대행 사기 감별표 1장
- 근거: 50-60대 소상공인은 대행 사기의 주 타깃 (공정위 기만영업 수사의뢰 18개 업체, 2026) — 이 단계가 신뢰의 출발점

### Phase 1: 시장 확인 (병렬)

- researcher: 업종 트렌드·수요 (`playbooks/02-intelligence/industry-trends.md`)
- competitor: 주변·온라인 경쟁자 3~5곳 (`playbooks/02-intelligence/competitor-monitoring.md`)
- 산출: intelligence 2종 → Phase 2 입력

### Phase 2: 마케팅 전략 → 산출물 ①

- strategist: `playbooks/01-strategy/gtm-motion-analysis.md` 적용, 규모에 맞게 축약
- 출력 형식 규칙: **"무엇을(핵심 메시지 1개) / 누구에게(타겟 고객 1명 묘사) / 90일 동안 주차별로 무엇을 하는지"**
- 문서 맨 앞에 **"사장님용 한 장 요약"** 섹션 필수 (전문용어 금지)

### Phase 3: 채널믹스 → 산출물 ②

- strategist: `playbooks/01-strategy/channel-strategy.md`
- **소상공인 우선순위 공식** (2026-07 리서치 근거 — `docs/research/2026-07-02-local-sop-research.md`):
  전 업종 1순위 = 네이버 스마트플레이스 → 2순위 = 당근 비즈프로필(동네) + 카카오톡 채널(단골) → 음식점은 배달앱(배민+쿠팡이츠) 별도 트랙 → 구글 비즈니스 프로필은 관광 상권 조건부 → 오프라인 인쇄물은 5060 상권 보조 트랙
- **업종 분기** (50대+ 신규 창업 3강 업종별 동선이 다름 — 국세청 2023 생활업종 통계):
  온라인 판매형(통신판매/스마트스토어) = 콘텐츠·상세페이지 중심 / 로컬 매장형(음식점 등) = 플레이스·리뷰·배달앱 중심 / 중개·사무형(부동산 등) = 블로그·지역 키워드 중심
- 출력 규칙: 채널 **최대 3개** (집중), 채널마다 "주 몇 회 / 무엇을 올리는지 / 1회 몇 분 걸리는지"를 명시
- Phase 0의 상담 메모(온라인/오프라인, 팀 규모, 예산)를 반드시 반영 — 혼자 운영하면 채널 2개 이하 권장

### Phase 4: 후킹문안 리스트 → 산출물 ③

- copywriter: `playbooks/03-content/hooking-copy.md`
- 입력: Phase 2 핵심 메시지 (`strategy_ref`) + Phase 3 집중 채널 (`channels`)
- 산출: 채널별 문안집 + Top 5 (Top 1은 Phase 6 히어로에 사용)

### Phase 5: 브랜드 에셋 킷 → 산출물 ④

- designer: `playbooks/08-design/design-direction.md`
- 킷 구성: 컬러 팔레트(메인 1 + 액센트 1) / 글꼴(한글 Pretendard) / 로고 방향 2안(글자형·심볼형, 텍스트 설명) / 목소리 톤 3줄 / "쓰는 법·쓰지 않는 법"
- 로고 실물 PNG가 필요하면 `skills/birkin/codex-image-gen` 프로토콜 (승인 게이트, `visual_asset_status` 규칙 준수 — 생성 못 하면 `unavailable`로 정직하게 표기)

### Phase 6: 홈페이지 → 산출물 ⑤

- copywriter: 13섹션 카피 (`playbooks/08-design/landing-page.md`) — Phase 4 Top 문안을 히어로에 사용 (러너 스텝 `homepage_copy`)
- designer: HTML 시안 — Phase 5 브랜드 킷의 컬러·글꼴 적용 (러너 스텝 `homepage_html`, `artifacts/{run_id}/landing-page.html` 생성)
- 상담 직후 빠른 초안이 먼저 필요하면 answers.json 기반 즉석 시안:
  `uv run aicmo mockup --from answers.json --out outputs/{slug}/design/{YYYYMMDD}_landing-quick.html`

### Phase 6.5: 채널 실행 팩 (선택한 채널만 — "대신 해주는" 단계)

Phase 3에서 고른 채널마다 해당 `09-local` SOP를 실행해 **즉시 붙여넣기 가능한 실행 팩**을 만든다 (Phase 4 후킹문안 + Phase 5 브랜드 킷이 입력):

| 선택 채널 | 실행 SOP | 실행 팩 내용 |
|----------|---------|-------------|
| 네이버 플레이스 | `09-local/naver-place-setup.md` | 설명문·키워드 5·소식 4주분·리뷰 답글 10종 |
| 카카오톡 채널 | `09-local/kakao-channel-setup.md` | 개설 시트·메시지 캘린더·친구모으기 키트 |
| 당근 | `09-local/danggeun-bizprofile.md` | 프로필 시트·소식 4주분·광고 세팅안 |
| 배달앱 (음식점) | `09-local/delivery-app-optimization.md` | 입점 서류·메뉴 문안·적법 리뷰 이벤트 |
| SNS | `09-local/local-sns-routine.md` | 진단표·주간 루틴·소재 12개·스크립트 |
| 오프라인 | `09-local/offline-print-kit.md` | 합법성 체크·전단/현수막 카피·발주 사양 |

모든 실행 팩은 `prompts/shared/deliverable-standard.md` (즉시 게시 가능 상태, 건수·주기 캘린더, 어뷰징 제로) 를 따른다.

### Phase 7: 검증 + 전달

- reviewer: 전 산출물 gate-check (`prompts/shared/gate-check.md` + 3.5단계 실행성 검증) — FAIL 시 해당 Phase 재실행 (최대 2회, 이후 ESCALATE)
- **사장님 승인 게이트**: 산출물을 쉬운 말로 브리핑하고 승인받는다 (CLI 실행 시 `owner_gate`)
- reporter: **런치팩 리포트** 작성 — 사장님용 1장: 만들어진 것 목록 + 파일 위치 + "다음 2주 동안 할 일 3개" + **직접 할 일 vs 플랫폼이 대신 한 일 구분표**
- KB 업데이트: `insights.md` + `lessons-learned.md` append

## 입력

- `client`: 클라이언트 폴더명 (필수)
- Phase 0에서 `answers.json` 생성 — 그 이후 추가 입력 없음

## 출력

```
clients/{client}/config.md, brand-guidelines.md, consultation-notes.md ← Phase 0
outputs/{client}/local/{YYYYMMDD}_support-and-guard.md             ← Phase 0.5
outputs/{client}/intelligence/{YYYYMMDD}_market-research.md        ← Phase 1
outputs/{client}/intelligence/{YYYYMMDD}_competitor-analysis.md    ← Phase 1
outputs/{client}/strategy/{YYYYMMDD}_launch-strategy.md            ← Phase 2 ①
outputs/{client}/strategy/{YYYYMMDD}_channel-mix.md                ← Phase 3 ②
outputs/{client}/content/{YYYYMMDD}_hooking-copy.md                ← Phase 4 ③
outputs/{client}/design/{YYYYMMDD}_brand-asset-kit.md              ← Phase 5 ④
outputs/{client}/design/{YYYYMMDD}_landing-page-copy.md (+.html)   ← Phase 6 ⑤
outputs/{client}/local/{YYYYMMDD}_{channel}-pack.md (채널별)        ← Phase 6.5
outputs/{client}/operations/{YYYYMMDD}_launch-pack-report.md       ← Phase 7
```

## 자동 실행 (CLI)

```powershell
# Phase 0 (상담 후):
uv run aicmo onboard --client {slug} --from answers.json

# Phase 1~7 (러너):
uv run aicmo run launch-pack --client {slug}

# 사장님 승인 게이트 처리:
uv run aicmo approve {run_id} owner_gate --reviewer owner --notes "브리핑 완료, 승인"
```

워크플로우 스펙: `workflows/launch-pack.workflow.yaml`

## 예상 소요 시간

- Phase 0 상담: 30~60분 (사장님 페이스에 맞춘다 — 서두르지 않는 것이 규칙)
- Phase 1~7 실행: ~20분 (검증 재실행 제외)

## 명령어 패턴

"사업 시작 마케팅 전부", "런치팩", "창업 마케팅 풀세트", "홈페이지부터 전략까지 다 해줘", "가게 마케팅 처음부터"
