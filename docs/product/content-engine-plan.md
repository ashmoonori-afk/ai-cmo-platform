# 기획: 콘텐츠 엔진 파이프라인 (langchain-ai/social-media-agent 이식)

> 상태: **P0·P1·P2 구현 완료 (2026-07-07)** — 엔진 `--accept-edits`+`_pre_edit` 스냅샷, `content-engine` 워크플로우·플레이북, `prompts/shared/reflection-diff.md`, `aicmo ingest`(inbox 인제스트, `--dry-run`). API 자동 발행 어댑터는 계획대로 보류 (§4 근거). 구현 중 발견·수정한 기존 결함 1건: 승인 대기 중 resume 시 게이트가 lease 가드로 FAILED 되던 문제 → 멱등 재대기로 수정.
> 작성: 2026-07-07
> 원본: github.com/langchain-ai/social-media-agent (LangGraph/TS — URL 하나로 SNS 포스트를 생성·검수·예약 발행하는 에이전트)

## 한 장 요약

- **이게 뭔지**: "URL 하나 던지면 → 검증 → 소스 리포트 → 채널별 포스트+이미지 → 사장님 승인(수정 가능) → 발행 캘린더 → **수정 내용 자동 학습**"까지 한 줄로 이어지는 콘텐츠 엔진을 우리 워크플로우 러너에 이식한다.
- **왜**: 지금 우리 SNS SOP는 "주제를 주면 잘 쓴다". 이 파이프라인은 "소스가 들어오면 알아서 만든다" — 사장님이 기사·유튜브·자기 블로그 링크만 보내면 콘텐츠가 나오는 구조로 운영 부담을 한 단계 더 낮춘다.
- **핵심 차별 포인트**: reflection(사장님이 고친 문안을 diff해서 KB에 학습)은 우리 자기 개선 루프(winning-copy/copy-patterns)와 정확히 맞물린다 — 원본 레포에서 가장 이식 가치가 높은 부분.
- **오늘 결정할 것 하나**: P0 범위(승인 전 수정 허용을 위한 엔진 소수정 + 워크플로우 1개 + 플레이북 1개)로 시작할지.

## 1. 원본 파이프라인 분석 (소스 트리 확인 기준)

17개 그래프: ingest-data / curate-data / verify-links·verify-tweet·verify-reddit / generate-report / generate-post / generate-thread / find-and-generate-images / curated-post-interrupt(휴먼 인박스) / upload-post / **reflection** / repurposer(+ingest-repurposed-data, repurposer-post-interrupt) / supervisor / shared

실행 흐름:
```
[소스 유입] Slack 채널 URL 수집 (cron 일 1회) 또는 수동 URL
  → [검증] 링크 유효성·콘텐츠 가치 판단 (GitHub/YouTube/FireCrawl로 본문 추출)
  → [리포트] 소스를 구조화된 마케팅 리포트로 요약 (2단계 생성의 1단계)
  → [포스트 생성] 리포트 기반 X/LinkedIn 포스트 (+스레드)
  → [이미지] 소스에서 이미지 선별 또는 생성
  → [휴먼 인박스] Agent Inbox — 승인/수정/일정변경/거부
  → [발행] 예약 시각에 API 게시
  → [reflection] 휴먼 수정본 vs 원본 diff → 스타일 규칙 축적 → 다음 생성에 반영
  → [repurposer] 검증된 콘텐츠를 시리즈로 재활용
```

## 2. 매핑 테이블 — 원본 노드 ↔ 우리 플랫폼

| 원본 | 우리 현황 | 판정 |
|------|----------|------|
| ingest-data (Slack+cron) | 없음 — 사용자가 대화/CLI로 시작 | **신규 (P2, 한국형 대체)** |
| verify-links (소스 가치 판단) | 없음 | **신규 스텝** |
| generate-report (2단계 생성) | 부분 — researcher가 유사 역할 | **신규 스텝** (소스 요약 리포트) |
| generate-post / generate-thread | **있음** — social-post.md (인스타/X/Threads/LinkedIn 규격+페널티 검사) | 재사용 |
| find-and-generate-images | 부분 — designer + codex-image-gen (visual_asset_status 규칙) | 재사용 |
| curated-post-interrupt (Agent Inbox) | **있음** — owner_gate (WAITING_APPROVAL + approve/reject CLI) | 재사용 + **수정 허용 보강 (P0 엔진)** |
| upload-post (API 발행) | 없음 — 승인 후 복붙 팩 | **P2 (선택)** |
| **reflection (수정 학습)** | 부분 — KB 수동 append (winning-copy) | **신규 스텝 (최고 가치)** |
| repurposer | **있음** — repurpose.md (4포맷 병렬) | 재사용 |
| supervisor / curate-data | 부분 — CMO 라우팅이 대행 | 보류 |
| 스케줄링 (예약 발행) | 부분 — social-calendar.md (계획만) | **발행 큐 문서로 대체 (P1)** |

결론: **17개 중 9개는 이미 있거나 재사용** — 실제 신규는 ①소스 검증·리포트 ②수정 허용 승인 ③reflection ④발행 큐 4가지.

## 3. 이식 설계

### 3.1 신규 워크플로우: `workflows/content-engine.workflow.yaml`

```
inputs: client(필수), source_url(필수), channels(선택)
load_context → verify_source(agent: researcher — 소스 본문 추출+가치·관련성 판정,
  브랜드 무관/저품질이면 사유와 함께 중단 권고)
→ source_report(agent: researcher — 소스를 구조화 리포트로: 핵심 주장/수치/인용/브랜드 연결점)
→ posts_generate(agent: copywriter — social-post.md 규격으로 채널별 문안,
  후킹은 ad-strategy-library 제4부 참조)
→ image_pack(agent: designer — 이미지 지시문 또는 codex-image-gen, visual_asset_status 규칙)
→ quality_gate(gate: reviewer — deliverable-standard 3.5 + 페널티 3종)
→ owner_gate(gate: requires_approval — 사장님이 아티팩트 파일을 직접 수정 후 승인 가능)
→ reflection(agent: reporter — 승인 시점의 최종본 vs 생성 원본 diff →
  바뀐 표현·톤을 clients/{client}/copy-patterns.md와 KB winning-copy 후보로 정리)
→ kb_queue(kb.update) → publish_pack(agent: reporter — 발행 큐 문서)
```

### 3.2 엔진 소수정 1건 (P0의 유일한 코드 작업)

**문제**: 현재 resume는 산출물 SHA-256 검증으로 변조를 감지해 스텝을 재실행한다(안전 기능). 사장님이 owner_gate 대기 중에 문안 파일을 고치면 → 재개 시 "변조"로 판정되어 **수정본이 재생성으로 덮인다.**

**해법**: `aicmo approve`에 **--accept-edits 플래그** — 승인 시 성공 스텝 아티팩트의 해시를 재계산해 저장(수정을 "축복"). reflection 스텝을 위해 **게이트가 처음 대기에 들어갈 때**(사람 수정이 시작되기 전) 모든 성공 스텝 산출물을 `artifacts/{run_id}/_pre_edit/`에 경로 미러로 write-once 보존. 축복은 승인 행 삽입 **전에** 수행(동시 resume 레이스 차단 — 검증 라운드에서 발견·수정). 변조 감지 기본 동작은 그대로 유지(플래그 없으면 기존과 동일 — fail-safe).

### 3.3 신규 플레이북: `playbooks/03-content/content-engine.md`

수동(대화형) 실행용 SOP — 위 흐름의 사람 버전 + 산출물 묶음(소스 리포트 / 채널별 문안 / 이미지 지시 / 발행 큐 / reflection 로그). CLAUDE.md 매핑 추가: "이 링크로 포스트 만들어줘", "이 기사로 SNS 올려줘", "콘텐츠 엔진".

### 3.4 한국형 어댑테이션 (원본과 다르게 가는 것)

| 원본 | 우리 선택 | 이유 |
|------|----------|------|
| Slack 채널 인제스트 | **inbox/ 폴더 + 대화 한 줄** ("이 링크로 포스트") → P2에서 Claude Code cron으로 inbox 폴더 스캔 | 카카오톡 개인 수집 API 없음; 시니어 타깃에겐 대화가 더 쉬움 |
| X/LinkedIn API 자동 발행 | **발행 큐 문서**(날짜·채널·복붙 문안·체크박스) 우선, API 발행은 P2 선택 | X API 유료·인스타 그래프 API는 비즈니스 계정+앱 심사 필요 — 시니어 온보딩 장벽. 승인→복붙이 현 단계 최적 [추정] |
| FireCrawl 크롤링 | Claude 내장 WebFetch/WebSearch | 외부 의존성 0 원칙 유지 |
| 채널: X/LinkedIn 중심 | 인스타/Threads/X/네이버 블로그 — 기존 social-post.md 규격 재사용 | 한국 채널 리서치 근거 (2026-07 다이제스트) |

## 4. 로드맵

| 단계 | 내용 | 산출물 | 공수(추정) |
|------|------|--------|-----------|
| **P0** | 엔진 --accept-edits + content-engine 워크플로우 + 플레이북 + CLAUDE.md 매핑 + 스펙 테스트 | 코드 소수정, YAML 1, MD 1 | 반나절 |
| **P1** | reflection 품질 고도화(diff→규칙 추출 프롬프트) + 발행 큐 표준 + repurpose 연결(승자 포스트→시리즈) | 프롬프트/SOP 보강 | 반나절 |
| **P2** | inbox/ 폴더 cron 인제스트 + (선택) Threads/인스타 API 발행 어댑터 | 수집기+어댑터 | 검토 후 |

## 5. 리스크 / 열린 질문

1. **저작권**: 남의 기사·영상을 소스로 쓴 포스트 — verify_source에 "인용+출처 표기, 전문 복제 금지" 게이트 내장 필요 (deliverable-standard 연장).
2. **reflection 오학습**: 일회성 수정을 영구 규칙으로 오인 가능 → 같은 패턴 2회 이상 반복 시에만 copy-patterns 승격 (KB append-only 원칙 유지).
3. API 자동 발행의 실익: 시니어 클라이언트에게 필요한가? — P2 착수 전 실사용 데이터로 판단.
4. 원본 레포 라이선스 MIT — 아이디어 이식이며 코드 복사 아님 (우리는 Python/자체 엔진).

## 다음 단계

1. P0 승인 여부 결정 (사용자)
2. 승인 시: 엔진 수정 → 워크플로우·플레이북 작성 → 스모크 테스트 → 커밋
3. 첫 실전: 사장님 업종 기사 1건으로 end-to-end 시연 → reflection 결과 KB 확인
