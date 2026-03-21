# 공통 컨텍스트 (Boilerplate)

> 모든 에이전트가 작업 시작 전 이 규칙에 따라 클라이언트 컨텍스트를 로드합니다.

---

## 클라이언트 컨텍스트 로딩

1. `clients/{client}/config.md` → 회사 정보, ICP, 경쟁사, 업종 로드
2. `clients/{client}/brand-guidelines.md` → 톤앤매너, 브랜드 보이스 로드
3. `clients/{client}/copy-patterns.md` → 카피 패턴 로드 (콘텐츠/세일즈 작업 시)
4. `clients/{client}/pricing-rules.md` → 가격 정책 로드 (전략/세일즈 작업 시)

### 로딩 규칙
- 파일이 없으면: "⚠️ {파일명} 파일이 없습니다. 먼저 클라이언트 온보딩을 실행하세요." 출력
- 빈 섹션이 있으면: 해당 항목 건너뛰고 경고
- 작업에 필요한 참조만 선택적으로 로드 (토큰 절약)

### 작업별 필수 참조

| 작업 유형 | 필수 로드 | 선택 로드 |
|----------|----------|----------|
| 전략 기획 | config.md | pricing-rules.md |
| 리서치 | config.md | - |
| 콘텐츠 작성 | config.md, brand-guidelines.md | copy-patterns.md |
| 세일즈 | config.md, brand-guidelines.md | pricing-rules.md |
| SEO | config.md | - |
| 분석/리포트 | config.md | - |
| 디자인 | config.md, brand-guidelines.md | - |

---

## Knowledge Base 참조

작업 시작 전 해당 클라이언트의 KB도 확인:
- `knowledge-base/{client}/insights.md` → 이전 리서치 인사이트
- `knowledge-base/{client}/winning-copy.md` → 검증된 카피 패턴
- `knowledge-base/{client}/lessons-learned.md` → 전략적 교훈

KB 파일이 없거나 비어있으면 건너뛴다 (신규 클라이언트).
