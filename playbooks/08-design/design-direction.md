# 디자인 디렉션 플레이북

## 목적

제품/서비스 브리프를 기반으로 스타일 프리셋, 컬러 팔레트, 타이포그래피, 레이아웃 패턴, 모션 디렉션을 정의한다. 랜딩페이지/상세페이지 제작 전 디자인 방향을 확정하는 사전 단계.

## 에이전트 조합

```
strategist → designer
```

| 순서 | 에이전트 | 역할 | 모델 |
|------|---------|------|------|
| 1 | strategist | 포지셔닝/타겟/메시지 전략 제공 | opus |
| 2 | designer | 전략 기반 디자인 디렉션 수립 | sonnet |

## 입력

| 항목 | 설명 | 필수 여부 |
|------|------|---------|
| `client` | 클라이언트 폴더명 | 필수 |
| `product_name` | 제품/서비스명 | 필수 |
| `industry` | 업종 | 필수 |
| `target_audience` | 타겟 고객 | 필수 |
| `brand_mood` | 브랜드 분위기 (선택: 모던/따뜻한/고급/활기찬) | 선택 |

## 참조 문서

- `clients/{client}/config.md` — 업종, ICP
- `clients/{client}/brand-guidelines.md` — 기존 브랜드 가이드 (있으면)

## 프레임워크

### Step 1: 스타일 프리셋 결정

업종/타겟 기반 자동 추천:

| 업종 | 추천 프리셋 | 이유 |
|------|----------|------|
| SaaS / 테크 | Minimal | 클린, 신뢰, 전문성 |
| 이커머스 / 프로모션 | Sales | 긴급성, 행동 유도 |
| 금융 / 컨설팅 / 럭셔리 | Premium | 고급감, 신뢰 |
| 교육 / 커뮤니티 / 헬스 | Community | 따뜻함, 소속감 |

### Step 2: 컬러 팔레트 정의

- brand-guidelines.md에 기존 컬러가 있으면 우선 사용
- 없으면 프리셋 기본 팔레트 적용
- 1 액센트 컬러 원칙 준수

### Step 3: 타이포그래피 정의

- 한국어: Pretendard (비협상)
- 영문: 프리셋별 추천 (Minimal→Geist, Premium→Satoshi 등)
- 크기 스케일: 헤드라인/서브/본문/캡션

### Step 4: 레이아웃 패턴 추천

- Hero 변형 추천 (Split/Full-bleed/Minimal/Typewriter)
- Feature 변형 추천 (Bento/Zig-Zag/Strip/Comparison)
- CTA 변형 추천 (Full-bleed/Sticky)

### Step 5: 모션 디렉션

- 모션 강도 결정 (1-10, 업종 기반)
- 이징 함수 지정
- 주요 애니메이션 패턴 선택

## 출력 경로

```
outputs/{client}/design/{YYYYMMDD}_design-direction.md
```
