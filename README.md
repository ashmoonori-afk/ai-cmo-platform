# AI CMO Platform

> Claude Code에서 실행하는 판매용 AI CMO 운영체계입니다. 자연어 요청을
> intake, triage, role SOP, reviewer gate, knowledge-base record로 연결합니다.

---

## 핵심 업그레이드

- 10개 역할 에이전트와 33개 core playbook은 그대로 유지합니다.
- `docs/role-sop/README.md`에 역할별 SOP, gate matrix, KB handoff, 원장/대표 비교표를 추가했습니다.
- `docs/system/`과 `docs/product/`에 판매용 운영 표준, 사용자 파이프라인, 포지셔닝, 데모 시나리오를 분리했습니다.
- `docs/system/dogfooding-procedure.md`와 `docs/dogfooding/`에 파이프라인 dogfooding 절차와 실행 리포트를 추가했습니다.
- `playbooks/00-chains/ai-cmo-operating-system.md`에 사용자 파이프라인을 추가했습니다.
- `playbooks/08-role-sops/`에 10개 역할별 SOP 플레이북을 추가했습니다.
- `integrations/birkin/`에 Neurosis, Odyssey, Morpheus, codex-image-gen handoff 계약을 추가했습니다.
- Birkin 패턴을 적절한 위치에 배치했습니다: Neurosis(명확화), Odyssey(복합 실행), codex-image-gen(콘텐츠 시각화), Morpheus(운영 개선).
- `handoff/`에 Hermes Agent와 OpenClaw 전달용 패키지 파일을 추가했습니다.

---

## 사용법

```bash
cd "ai-cmo-platform"
# Claude Code 실행 후 자연어로 명령

"플라워플러스 GTM 전략 짜줘"
"아이리스 경쟁사 분석해줘"
"플라워플러스 블로그 써줘 — 주제: 기업 꽃 구독의 장점"
"새 클라이언트 온보딩: {회사명}"
"플라워플러스 주간 리포트"
"AI CMO 운영체계로 정리해줘"
```

## 구조

```
ai-cmo-platform/
├── CLAUDE.md              ← 시스템 두뇌 (자연어→워크플로우 매핑 43패턴)
├── agents/                ← 서브에이전트 10개
├── clients/               ← 클라이언트별 설정 (config, 브랜드, 카피, 가격)
│   ├── _template/         ← 신규 클라이언트 템플릿
│   ├── flowerplus/
│   └── iris/
├── docs/role-sop/         ← 역할별 SOP와 판매용 운영 표준
├── docs/system/           ← baseline, role SOP standard, user pipeline, dogfooding procedure
├── docs/dogfooding/       ← 실제 파이프라인 실행 리포트
├── docs/product/          ← sellable positioning, owner/director comparison, demos
├── integrations/birkin/   ← Neurosis, Odyssey, Morpheus, codex-image-gen handoff
├── handoff/               ← Hermes Agent / OpenClaw 전달 패키지
├── playbooks/             ← 실행 가능한 core SOP 33개 + 운영 chain
│   ├── 01-strategy/       (6) GTM, 포지셔닝, 캠페인, 채널, 가격, 퍼널
│   ├── 02-intelligence/   (5) 경쟁사, 트렌드, 기업리서치, ICP, 피드백
│   ├── 03-content/        (8) 블로그, SNS, 뉴스레터, 케이스스터디, 리드마그넷, 리퍼포징, 캘린더, AB카피
│   ├── 04-sales/          (5) 아웃바운드, 콜프렙, 제안서, 미팅후처리, 피칭덱
│   ├── 05-seo/            (3) 키워드, SEO감사, 콘텐츠브리프
│   ├── 06-analytics/      (3) 성과리포트, 주간리포트, GA감사
│   ├── 07-operations/     (3) 회의록, 데이터정리, 클라이언트온보딩
│   └── 08-role-sops/      (10) 역할별 실행 SOP
├── knowledge-base/        ← 축적형 자산 (쓸수록 똑똑해짐)
├── outputs/               ← 생성물 저장
├── prompts/shared/        ← 공통 프롬프트
└── references/            ← 기존 전략 문서 아카이브
```

## 에이전트 (10개)

| 에이전트 | 역할 | 모델 |
|---------|------|------|
| researcher | 시장/업종/기업 리서치 | opus |
| competitor | 경쟁사 분석 | opus |
| strategist | 전략 프레임워크 적용 | opus |
| copywriter | 콘텐츠 작성 | sonnet |
| repurposer | 1→4 포맷 변환 | haiku |
| seo-specialist | 키워드/SEO 최적화 | sonnet |
| data-analyst | 데이터 분석 | opus |
| sales-writer | 세일즈 카피 | sonnet |
| reporter | 주간 리포트 + KB 관리 | sonnet |
| reviewer | 품질 검증 게이트 | sonnet |

## 새 클라이언트 추가

```
"새 클라이언트 온보딩: {회사명}, 웹사이트: {URL}"
```

승인·검증 기반으로 config, 브랜드 가이드 초안, 경쟁사 분석, ICP, 3개월 로드맵 초안을 생성합니다.
