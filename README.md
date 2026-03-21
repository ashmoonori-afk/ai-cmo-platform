# AI CMO Platform

> 이 폴더에서 Claude Code를 열고 자연어로 명령하면 됩니다.

---

## 사용법

```bash
cd "ai-cmo-platform"
# Claude Code 실행 후 자연어로 명령

"플라워플러스 GTM 전략 짜줘"
"아이리스 경쟁사 분석해줘"
"플라워플러스 블로그 써줘 — 주제: 기업 꽃 구독의 장점"
"랜딩페이지 만들어줘"
"새 클라이언트 온보딩: {회사명}"
"플라워플러스 주간 리포트"
```

## 구조

```
ai-cmo-platform/
├── CLAUDE.md              ← 시스템 두뇌 (자연어→워크플로우 매핑 48패턴)
├── agents/                ← 서브에이전트 11개
├── clients/               ← 클라이언트별 설정 (config, 브랜드, 카피, 가격)
│   ├── _template/         ← 신규 클라이언트 템플릿
│   ├── flowerplus/
│   └── iris/
├── playbooks/             ← 실행 가능한 SOP 33개
│   ├── 01-strategy/       (6) GTM, 포지셔닝, 캠페인, 채널, 가격, 퍼널
│   ├── 02-intelligence/   (5) 경쟁사, 트렌드, 기업리서치, ICP, 피드백
│   ├── 03-content/        (8) 블로그, SNS, 뉴스레터, 케이스스터디, 리드마그넷, 리퍼포징, 캘린더, AB카피
│   ├── 04-sales/          (5) 아웃바운드, 콜프렙, 제안서, 미팅후처리, 피칭덱
│   ├── 05-seo/            (3) 키워드, SEO감사, 콘텐츠브리프
│   ├── 06-analytics/      (3) 성과리포트, 주간리포트, GA감사
│   └── 07-operations/     (3) 회의록, 데이터정리, 클라이언트온보딩
├── knowledge-base/        ← 축적형 자산 (쓸수록 똑똑해짐)
├── outputs/               ← 생성물 저장
├── prompts/shared/        ← 공통 프롬프트
└── references/            ← 기존 전략 문서 아카이브
```

## 에이전트 (11개)

| 에이전트 | 역할 | 모델 |
|---------|------|------|
| researcher | 시장/업종/기업 리서치 | opus |
| competitor | 경쟁사 분석 | opus |
| strategist | 전략 프레임워크 적용 | opus |
| copywriter | 콘텐츠 작성 | sonnet |
| **designer** | **랜딩페이지/상세페이지 디자인, 디자인 감사** | **sonnet** |
| repurposer | 1→4 포맷 변환 | haiku |
| seo-specialist | 키워드/SEO/GEO 최적화 | sonnet |
| data-analyst | 데이터 분석 | opus |
| sales-writer | 세일즈 카피 | sonnet |
| reporter | 주간 리포트 + KB 관리 | sonnet |
| reviewer | 품질 검증 게이트 | sonnet |

## 새 클라이언트 추가

```
"새 클라이언트 온보딩: {회사명}, 웹사이트: {URL}"
```

자동으로 config, 브랜드 가이드, 경쟁사 분석, ICP, 3개월 로드맵이 생성됩니다.
