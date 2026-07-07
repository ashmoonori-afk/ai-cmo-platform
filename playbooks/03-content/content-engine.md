# 콘텐츠 엔진 플레이북 (소스 URL → 승인된 채널 포스트)

## 목적

**URL 하나(기사·유튜브·블로그·자사 콘텐츠)를 던지면** 소스 검증 → 소스 리포트 → 채널별 포스트+이미지 → 사장님 승인(수정 가능) → 발행 큐 → **수정 내용 자동 학습(reflection)**까지 한 줄로 처리한다. langchain-ai/social-media-agent 파이프라인의 한국형 이식 (기획: `docs/product/content-engine-plan.md`).

## 에이전트 조합

```
researcher(검증→리포트) → copywriter(포스트) → designer(이미지) → reviewer → [사장님 승인] → reporter(reflection→발행 큐)
```

## 입력

| 항목 | 설명 | 필수 |
|------|------|------|
| `client` | 클라이언트 폴더명 | 필수 |
| `source_url` | 소스 URL (기사/영상/블로그/자사 글) | 필수 |
| `channels` | 대상 채널 (없으면 config.md 채널믹스의 집중 채널) | 선택 |

## 참조 문서

- `clients/{client}/config.md`, `brand-guidelines.md`, `copy-patterns.md`
- `playbooks/03-content/social-post.md` — 채널별 규격·페널티 검사 (중복 정의 금지)
- `playbooks/10-ads/ad-strategy-library.md` 제4부 — 후킹 전략
- `knowledge-base/{client}/winning-copy.md` — 검증 패턴
- `prompts/shared/deliverable-standard.md`

## 프레임워크

### Step 1: 소스 검증 (researcher → source-verdict)

WebFetch로 소스 본문을 추출하고 3중 판정:
1. **가치**: 이 소스가 타깃 고객에게 유용한 정보인가 (단순 광고/저품질이면 REJECT + 사유)
2. **관련성**: config.md의 업종·ICP와 연결점이 있는가 (연결점 1줄 명시)
3. **저작권 게이트 (필수)**: 인용은 출처 표기 + 짧은 발췌만, **전문 복제 금지**. 이미지 무단 사용 금지. 판정 결과에 "인용 가능 범위"를 명시한다.

REJECT 판정이면 사유를 남기고 사용자에게 중단을 권고한다 (게이트가 아닌 권고 — 최종 판단은 운영자).

### Step 2: 소스 리포트 (researcher → source-report)

2단계 생성의 1단계 — 소스를 바로 포스트로 만들지 않고 구조화 리포트를 먼저 만든다 (원본 파이프라인의 generate-report 패턴):
- 핵심 주장 3개 / 수치·데이터 (출처 문장 그대로) / 인용할 문장 1~2개
- **브랜드 연결점**: 이 소스가 우리 가게/제품과 만나는 지점 (사장님 관점 한 줄)
- 채널별 소구 각도 제안 (ad-strategy-library 제3부 앵글 프레임워크)

### Step 3: 채널별 포스트 (copywriter → channel-posts)

`social-post.md` 규격 그대로 (인스타 캡션 첫 줄 검색 키워드 / X 링크는 첫 답글 / Threads 태그 1개 / 페널티 3종 회피). 후킹은 소스 리포트의 인용·수치를 활용 (통계 +31%·인용문 +41% — GEO 논문, 포스트에도 유효한 원리 [추정]).

### Step 4: 이미지 팩 (designer → image-pack)

- 소스 이미지는 저작권상 사용 금지가 기본 — **자체 촬영 지시문** 또는 `skills/birkin/codex-image-gen` 생성 (visual_asset_status 규칙: 실제 파일 없으면 unavailable로 정직 표기)
- 채널별 규격 (인스타 1080×1350 / 스토리·릴스 9:16)

### Step 5: 검증 + 사장님 승인 (수정 흐름)

- reviewer: gate-check + deliverable-standard 3.5단계
- **사장님 수정 흐름**: owner_gate 대기 중 `artifacts/{run_id}/channel-posts.md`를 직접 수정해도 된다. 승인 시:

```powershell
uv run aicmo approve {run_id} owner_gate --reviewer owner --accept-edits
```

`--accept-edits`가 수정본을 보존하고(재생성 방지), 원본은 `artifacts/{run_id}/_pre_edit/`에 남는다.

### Step 6: Reflection — 수정에서 배우기 (reporter → reflection)

원본 파이프라인의 최고 가치 노드. **상세 계약: `prompts/shared/reflection-diff.md`** (중복 정의 금지 — 그 문서가 원본). 요지: `_pre_edit/` 원본 vs 승인 최종본 diff → 4유형 분류(톤/표현/구조/사실 정정) → 사실 정정은 즉시 KB 후보, 패턴은 **2회 이상 반복 시에만** copy-patterns 승격 제안 → KB 직접 쓰기 금지 (kb_queue 경유).

### Step 7: 발행 큐 (reporter → publish-queue)

즉시 붙여넣기 가능한 발행 큐 문서 (API 자동 발행 대신 — 한국형 어댑테이션):

```markdown
# 발행 큐 — {client} / {날짜}
| 발행일시 | 채널 | 문안 (복붙용) | 이미지 | 상태 |
|---------|------|-------------|--------|------|
| 화 11:00 | 인스타 | {최종 문안 전문} | {파일/지시문} | ☐ |
```
- 발행 시각은 social-calendar.md 기본값 (화~수 11-18시 우선, 계정 인사이트로 보정)
- 반응 좋은 포스트는 `repurpose.md`로 4포맷 시리즈 확장 권고 1줄 포함

## 자동 실행 (CLI)

```powershell
# 단건:
uv run aicmo run content-engine --client {slug} --input source_url="{URL}" --executor claude
# 수정 후 승인:
uv run aicmo approve {run_id} owner_gate --reviewer owner --accept-edits
uv run aicmo resume {run_id} --executor claude

# 일괄 (inbox 인제스트): inbox/{slug}/에 URL 파일(.txt/.md, 한 줄에 하나)을 넣고
uv run aicmo ingest --client {slug} --executor claude    # 각 URL이 owner_gate까지 자동 진행
uv run aicmo ingest --client {slug} --dry-run            # 계획만 확인
```

주기 실행은 Claude Code 예약 세션(cron)에서 `aicmo ingest`를 호출하면 된다. 자동 발행(API) 어댑터는 의도적으로 보류 — X API 유료·인스타 앱 심사 등 시니어 온보딩 장벽 대비 실익 검토 후 (기획서 §4).

## 산출물 (묶음)

```
1. 사장님용 한 장 요약 (이 소스로 뭘 만들었고, 언제 뭘 올리면 되는지)
2. 소스 판정 + 소스 리포트 (인용 가능 범위 명시)
3. 채널별 포스트 문안 + 이미지 팩
4. 발행 큐 (복붙용, 체크박스)
5. reflection 로그 (수정 학습 결과)
```

## 출력 경로

```
outputs/{client}/content/{YYYYMMDD}_content-engine-{slug}.md   ← 수동 실행 시 통합본
artifacts/{run_id}/                                            ← CLI 실행 시 스텝별
```

## KB 업데이트

- 2회+ 반복 수정 패턴 → `clients/{client}/copy-patterns.md` (reflection 경유)
- 반응 좋은 포스트 → `knowledge-base/{client}/winning-copy.md`

## 명령어 패턴

"이 링크로 포스트 만들어줘", "이 기사로 SNS 올려줘", "콘텐츠 엔진", "이 영상 우리 채널에 소개해줘"
