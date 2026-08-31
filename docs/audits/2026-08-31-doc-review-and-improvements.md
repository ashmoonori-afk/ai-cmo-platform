# 리뷰 & 개선점 도출 — 2026-08-31

> 방법: 문서 3개 레인(사용자-facing / CLAUDE.md / system·product docs)을 실제 코드·파일 트리·git 이력과 대조.
> 검증 기준 실측값: **테스트 115개 통과** (`uv run pytest -q`, 2026-08-31), **에이전트 11개**, **플레이북 68개**,
> **자연어 매핑 64행** (CLAUDE.md §3, 1~64 연속), **launch-pack 13 steps**, 버전 **0.2.0** (pyproject.toml:3).

## 1. 이번에 최신화한 항목 (완료)

| 문서 | 낡은 내용 | 실제 | 조치 |
|------|----------|------|------|
| README.md:26,168 | 100 tests | 115 tests | 수정 |
| README.md:293,490 | 91 passed | 115 passed | 수정 |
| README.md:29 | launch-pack 12 steps | 13 steps (workflows/launch-pack.workflow.yaml) | 수정 |
| README.md:57 | `docs/research/` 존재 주장 | gitignore된 로컬 전용 레이어 | 명시 |
| AI-CMO-Platform-사용설명서.md:65,555 | v1.0 / 10 Agents / 7 Modules / 33 Playbooks | v0.2.0 / 11 / 12 / 68 | 수정 |
| AI-CMO-Platform-사용설명서.md:147,466,468 | outputs만 기술, 43 매핑, 10 agents | artifacts/{run_id}/ 병기, 64 매핑, 11 agents | 수정 |
| AI-CMO-Platform-카톡공유용.md:6,9,40,41 | 10 agents / 33 playbooks | 11 / 68 | 수정 |
| docs/사용설명서.md:69 | outputs/만 기술 | artifacts/{run_id}/ 병기 | 수정 |
| CLAUDE.md:85-87 | 클라이언트 매핑 a,b만 | a~e 5개 존재 (clients/) | 추가 |
| CLAUDE.md:131,158,181 | Strategy 6 / Content 8 / SEO 3 | 7 / 11 / 4 | 수정 |
| CLAUDE.md:475-485 | KB에 _engine-improvements 누락 | src/aicmo/feedback.py:21-24가 기록 | 추가 |
| CLAUDE.md:636-637,653 | 클라이언트 트리 a,b만 / outputs만 | a~e / artifacts 병기 | 수정 |
| docs/system/baseline-inventory.md:11-15 | 10 agents / 33 core / 4 chains / 43 rows / 3 prompts | 11 / 38 / 5 / 64 / 6 | 갱신 + 날짜 명시 |
| docs/product/content-engine-plan.md:12,35,40,82,91-93 | 출시 완료 기능이 미래형으로 기술 | P0·P1·P2 구현 완료 (2026-07-07, 헤더 명시) | 완료 표기 |

## 2. 개선점 (미해결)

### P0 — 즉시

1. ** stray 파일 `NUL` 삭제 + .gitignore 추가**
   - 근거: `git status`에 `?? NUL`. POSIX 셸에서 `> NUL` 리다이렉트가 만든 산출물(Windows 예약어라 일반 삭제가 안 됨 — `del \\.\C:\...\NUL` 또는 git-bash `rm NUL`).
2. **문서 수치 드리프트 재발 방지 — 카운트 단일 소스화**
   - 근거: 이번 리뷰에서만 테스트 수가 README에 100/91 두 버전, 사용설명서에 10/11 agents, 33/68 playbooks가 혼재. 사람이 손으로 고치는 숫자는 반드시 다시 낡는다.
   - 제안: `uv run python scripts/doc_counts.py`(신규)가 agents/playbooks/tests/매핑 행 수를 출력하고, 문서에는 절대값 대신 "scripts/doc_counts.py 참조" 또는 생성 마커(`<!-- counts:auto -->`)를 두는 방식. 최소한 README의 테스트 수 주석은 제거하고 `uv run pytest -q` 결과로 확인하도록 유도.
3. **`output/`(단수) stray 디렉터리 정리**
   - 근거: `output/pdf/2026-07-21-ultrawork-code-audit-improvement-plan.ko.pdf` 1건만 존재, gitignore는 `outputs/`(복수)만 커버. PDF를 docs/audits/로 이동하고 `output/` 삭제 또는 gitignore 추가.

### P1 — 단기

4. **루트↔docs/ 문서 쌍 정리**
   - 근거: `AI-CMO-Platform-사용설명서.md`(19KB) vs `docs/사용설명서.md`(4KB), `AI-CMO-Platform-카톡공유용.md`(1.5KB) vs `docs/카톡공유용.md`(0.9KB) — 이름이 같고 내용은 다른 문서가 두 위치에 존재. 이번에 루트 카톡공유용이 낡은 채 발견됨.
   - 제안: 한쪽을 canonical로 지정하고 다른 쪽은 링크 한 줄로 대체.
5. **docs/system/pipeline-audit-and-roadmap-2026-06-25.md 읽기 안전장치 강화**
   - 근거: line 3에 historical 표기는 있으나 본문(13-18, 46-53, 87-92)이 현재형("리뷰어 게이트가 가짜", "evaluation/mockup/web 없음")으로 읽힘 — 해당 기능 전부 구현됨(src/aicmo/gate.py:22-89, evaluate.py, mockup.py, web.py). line 196의 "71 tests"도 당시 스냅샷.
   - 제안: 문서 상단에 "2026-06-25 시점 스냅샷 — 현재 상태는 docs/system/workflow-engine.md 참조" 배너 + 파일명을 `archive/`로 이동.
6. **content-engine 인제스트 스케줄링 결정**
   - 근거: `aicmo ingest` CLI는 출시됐으나 cron/스케줄 자동 스캔은 미구현(docs/product/content-engine-plan.md:82에만 언급). 수동 실행이 원칙인지, 스케줄러를 붙일지 결정이 필요.
7. **CLAUDE.md 섹션 번호 체계 정리**
   - 근거: `### 7.0`/`7.1`/`7.1.1`/`7.1.2` 혼용 후 `7.2`로 복귀(CLAUDE.md:461-507), 부록(598-685)이 번호 없이 폴더 구조·최종 판정 등 주요 섹션을 포함.

### P2 — 중기

8. **cli.py 분할 검토**
   - 근거: src/aicmo/cli.py 566행에 명령 14개(run/ingest/resume/status/list-runs/approve/reject/retry/onboard/serve/mockup/evaluate/kb-flush)가 집중. 명령 추가 시마다 비대해지는 구조. 명령군별 모듈(run·gate·inspect·tool) 분할 후보.
9. **dogfooding 문서의 수치 표기 규칙**
   - 근거: docs/dogfooding/2026-06-26-full-sop-dogfooding.md:90의 "91 passed"는 당시 기록으로 정당하나, 이후 리뷰어가 현재값으로 오독할 수 있음. "당시 N개" 표기 규칙을 docs/system/dogfooding-procedure.md에 추가.
10. **`outputs/`(대화형) vs `artifacts/`(엔진) 이원 규칙의 단일 문서화**
    - 근거: 이번에 README·사용설명서·CLAUDE.md 3곳에 같은 주의를 병기함. 규칙 원천은 docs/system/user-pipeline.md 한 곳에 두고 나머지는 링크로.

## 3. 처리 결과 (2026-08-31 실행)

플랜 `.omo/plans/2026-08-31-audit-improvements.md`(교차 모델 리뷰 3라운드 승인)에 따라 실행.

| 항목 | 상태 | 비고 |
|------|------|------|
| P0-1 NUL 삭제 | ✅ 완료 | 삭제 + .gitignore에 `NUL` 추가 |
| P0-2 카운트 단일 소스 | ✅ 완료 | `scripts/doc_counts.py` 신설(출력 실측 일치), README 절대값 제거 |
| P0-3 output/ 정리 | ✅ 완료 | PDF → docs/audits/, `output/` 제거 + gitignore |
| P1-4 문서 쌍 정리 | ✅ 완료 | 루트 카톡공유용 → docs/ 포인터화, 사용설명서 쌍 역할 명시 |
| P1-5 historical 배너 | ✅ 완료 | 스냅샷 배너 + "71 tests (당시)" |
| P1-6 인제스트 스케줄링 | ✅ 결정 | cron 미도입 — 수동 `aicmo ingest` 원칙 문서화 |
| P1-7 CLAUDE.md 번호 | ✅ 완료 | 7.x 연속 재번호, 부록 → 9 |
| P2-8 cli.py 분할 | ✅ 완료 | `src/aicmo/cli/` 패키지(6모듈), move-verbatim + help PIN diff 0 + 런타임 스모크 13명령 + 115 tests green |
| P2-9 수치 표기 규칙 | ✅ 완료 | dogfooding-procedure에 "당시 N개" 규칙 |
| P2-10 저장 규칙 원천화 | ✅ 완료 | user-pipeline.md 원천 섹션 + 각 문서 링크 |

### 신규 발견 (P1 추가)

11. **린터 버전 드리프트로 인한 pre-existing 위반 16건**
    - 근거: HEAD(762882e) 자체가 최신 ruff에서 11건(`src/aicmo/step_state.py` FLY002·S608, `tests/test_accept_edits.py` PT018 외, cli 이전분 B006·C901·EM102·FBT003·PLR0912·TRY003), basedpyright 5건(`runner.py:99-102`, `step_executor.py:167-172`, `test_accept_edits.py:106`) 실패 — 과거 "clean" 기록은 당시 린터 버전 기준. 이번 변경은 신규 위반 0(HEAD 동수·동일 코드 확인).
    - 제안: 별도 커밋으로 16건을 정식 수정(억제 금지), lockfile에 린터 버전 고정 검토.
