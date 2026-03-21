# 랜딩페이지 디자인 플레이북

## 목적

전환 최적화된 랜딩페이지의 디자인 디렉션을 생성한다. 13섹션 구조에 카피를 매핑하고, 스타일 프리셋/컬러/타이포/레이아웃/모션 디렉션을 정의한다.

## 에이전트 조합

```
strategist → copywriter → designer → reviewer
```

| 순서 | 에이전트 | 역할 | 모델 |
|------|---------|------|------|
| 1 | strategist | 타겟/포지셔닝/메시지 전략 | opus |
| 2 | copywriter | 13섹션 카피 작성 | sonnet |
| 3 | designer | 디자인 디렉션 + 섹션별 레이아웃 | sonnet |
| 4 | reviewer | 디자인 + 카피 품질 검증 | sonnet |

## 입력

| 항목 | 설명 | 필수 여부 |
|------|------|---------|
| `client` | 클라이언트 폴더명 | 필수 |
| `product_name` | 제품/서비스명 | 필수 |
| `one_liner` | 한 문장 소개 | 필수 |
| `target_audience` | 타겟 고객 | 필수 |
| `main_problem` | 핵심 문제 | 필수 |
| `key_benefit` | 핵심 혜택 | 필수 |
| `style_preset` | minimal / sales / premium / community | 선택 |
| `price` | 가격 정보 (원가/할인가) | 선택 |

## 참조 문서

- `clients/{client}/config.md` — ICP, 제품 정보
- `clients/{client}/brand-guidelines.md` — 브랜드 컬러, 톤앤매너
- `agents/designer.md` — 13섹션 구조, 스타일 프리셋, 디자인 규칙

## 프레임워크

### 13섹션 감정 여정

```
01 Hero (관심) → 02 Pain (공감) → 03 Problem (이해) → 04 Story (희망)
→ 05 Solution Intro (명확함) → 06 How It Works (실현) → 07 Social Proof (신뢰)
→ 08 Authority (자격) → 09 Benefits+Bonus (가치) → 10 Risk Removal (안심)
→ 11 Comparison (FOMO) → 12 Target Filter (확신) → 13 Final CTA (행동)
```

### 디자인 프로세스

1. 클라이언트 브리프 + config.md 분석
2. 스타일 프리셋 결정 (업종 기반 또는 사용자 지정)
3. 컬러 팔레트 + 타이포그래피 + 모션 디렉션 정의
4. copywriter의 13섹션 카피를 수신
5. 섹션별 레이아웃 변형 선택 (인접 섹션 다른 패턴)
6. 디자인 디렉션 문서 생성

### 핵심 규칙

- 인접 섹션은 반드시 다른 레이아웃 패턴
- 1페이지 최대 1 액센트 컬러
- 한국어 텍스트: Pretendard + break-keep-all
- CTA 버튼: 48px+ 높이, hover/active 상태 필수
- AI 클리셰 금지 ("혁신적인", "차세대")
- 구체적 숫자 사용 (47,200+ 스타일)

## 출력 템플릿

```markdown
# 랜딩페이지 디자인 디렉션: {제품명}

**클라이언트**: {client}
**날짜**: {YYYY-MM-DD}
**스타일 프리셋**: {preset}
**출력 형식**: {html / direction}

---

## 디자인 시스템

### 컬러 팔레트
| 역할 | 컬러 | 용도 |
|------|------|------|

### 타이포그래피
| 요소 | 폰트 | 크기 | 무게 |
|------|------|------|------|

### 모션 디렉션
- 강도: /10
- 이징: cubic-bezier(...)
- 주요 애니메이션:

---

## 섹션별 디자인 (13섹션)

### 섹션 01: Hero
- **레이아웃 변형**: {Split/Full-bleed/Minimal/Typewriter}
- **감정 목표**: "이건 나를 위한 거다"
- **카피 배치**: {위치 설명}
- **비주얼 방향**: {이미지/일러스트/패턴}

### 섹션 02: Pain
...

---

## 반응형 노트
- 모바일 변경 사항:
- 태블릿 변경 사항:
```

## 출력 경로

```
outputs/{client}/design/{YYYYMMDD}_landing-page-{product-slug}.md
```
